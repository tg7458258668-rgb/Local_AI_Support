from __future__ import annotations

import os
import signal
import shutil
import socket
import subprocess
import sys
import time
from pathlib import Path


class SystemController:
    def __init__(self, base_dir: Path, host: str = "127.0.0.1", port: int = 8000):
        self.base_dir = base_dir
        self.host = host
        self.port = port
        self.runtime_dir = base_dir / "runtime"
        self.pid_path = self.runtime_dir / "support_app.pid"
        self.log_path = self.runtime_dir / "support_app.log"

    def status(self) -> dict:
        pid = self._read_pid()
        port_pid = self._pid_on_port()
        effective_pid = port_pid or pid
        running = self._is_running(pid) or bool(port_pid or self._port_is_open())
        if pid and not self._is_running(pid) and not port_pid:
            self.pid_path.unlink(missing_ok=True)
            pid = None
        return {
            "managed": bool(pid and self._is_running(pid)),
            "running": running,
            "pid": effective_pid,
            "base_dir": str(self.base_dir),
            "host": self.host,
            "port": self.port,
            "url": f"http://{self.host}:{self.port}",
            "log_path": str(self.log_path),
        }

    def start(self) -> dict:
        current = self.status()
        if current["running"]:
            return {**current, "ok": True, "message": "系统已在运行"}

        self.runtime_dir.mkdir(parents=True, exist_ok=True)
        log_file = open(self.log_path, "a", encoding="utf-8")
        python_bin = self._python_bin()
        process = subprocess.Popen(
            [
                python_bin,
                "-m",
                "uvicorn",
                "support_app.main:app",
                "--host",
                self.host,
                "--port",
                str(self.port),
            ],
            cwd=str(self.base_dir),
            stdout=log_file,
            stderr=log_file,
            start_new_session=True,
        )
        self.pid_path.write_text(str(process.pid), encoding="utf-8")
        return {**self.status(), "ok": True, "message": "系统启动中"}

    def stop(self) -> dict:
        stored_pid = self._read_pid()
        pid = stored_pid if self._is_running(stored_pid) else self._pid_on_port()
        if not pid:
            self.pid_path.unlink(missing_ok=True)
            return {**self.status(), "ok": True, "message": "没有启动器托管的系统进程"}
        if self._is_running(pid):
            os.kill(pid, signal.SIGTERM)
        self.pid_path.unlink(missing_ok=True)
        return {**self.status(), "ok": True, "message": "系统已发送停止指令"}

    def restart(self) -> dict:
        self.stop()
        self._wait_until_stopped()
        return self.start() | {"message": "系统重启中"}

    def _read_pid(self) -> int | None:
        try:
            return int(self.pid_path.read_text(encoding="utf-8").strip())
        except Exception:
            return None

    @staticmethod
    def _is_running(pid: int | None) -> bool:
        if not pid:
            return False
        try:
            os.kill(pid, 0)
            return True
        except OSError:
            return False

    def _python_bin(self) -> str:
        preferred = self.base_dir / ".venv" / "bin" / "python"
        if preferred.exists():
            return str(preferred)
        return sys.executable

    def _port_is_open(self) -> bool:
        try:
            with socket.create_connection((self.host, self.port), timeout=0.3):
                return True
        except OSError:
            return False

    def _pid_on_port(self) -> int | None:
        try:
            output = subprocess.check_output(
                ["lsof", "-tiTCP:%s" % self.port, "-sTCP:LISTEN"],
                stderr=subprocess.DEVNULL,
                text=True,
                timeout=1,
            )
        except Exception:
            return None
        for line in output.splitlines():
            try:
                return int(line.strip())
            except Exception:
                continue
        return None

    def _wait_until_stopped(self, timeout: float = 8.0) -> None:
        deadline = time.time() + timeout
        while time.time() < deadline:
            if not self._pid_on_port() and not self._port_is_open():
                return
            time.sleep(0.2)


class QdrantController:
    def __init__(self, base_dir: Path, host: str = "127.0.0.1", port: int = 6333):
        self.base_dir = base_dir
        self.host = host
        self.port = port
        self.runtime_dir = base_dir / "runtime"
        self.pid_path = self.runtime_dir / "qdrant.pid"
        self.log_path = self.runtime_dir / "qdrant.log"
        self.storage_dir = base_dir / "data" / "qdrant_storage"
        safe_name = "".join(ch if ch.isalnum() else "-" for ch in base_dir.name.lower()).strip("-")
        self.container_name = f"local-ai-support-qdrant-{safe_name or 'app'}"

    def status(self) -> dict:
        pid = self._read_pid()
        port_pid = self._pid_on_port()
        container = self._container_status()
        running = bool(port_pid or self._port_is_open() or container.get("running"))
        mode = "docker" if container.get("exists") else ("binary" if pid else "unknown")
        available, availability_message = self._availability()
        docker_path = self._docker_bin()
        docker_ready, docker_error = self._docker_state()
        return {
            "managed": bool(pid or container.get("exists")),
            "running": running,
            "pid": pid or port_pid,
            "base_dir": str(self.base_dir),
            "host": self.host,
            "port": self.port,
            "url": f"http://{self.host}:{self.port}",
            "log_path": str(self.log_path),
            "storage_dir": str(self.storage_dir),
            "mode": mode,
            "available": available,
            "availability_message": availability_message,
            "docker_path": docker_path or "",
            "docker_ready": docker_ready,
            "docker_error": docker_error,
            "container": container,
        }

    def start(self) -> dict:
        current = self.status()
        if current["running"]:
            return {**current, "ok": True, "message": "Qdrant 已在运行"}

        self.runtime_dir.mkdir(parents=True, exist_ok=True)
        self.storage_dir.mkdir(parents=True, exist_ok=True)

        qdrant_bin = self._qdrant_bin()
        if qdrant_bin:
            log_file = open(self.log_path, "a", encoding="utf-8")
            process = subprocess.Popen(
                [qdrant_bin, "--storage-dir", str(self.storage_dir)],
                cwd=str(self.base_dir),
                stdout=log_file,
                stderr=log_file,
                start_new_session=True,
            )
            self.pid_path.write_text(str(process.pid), encoding="utf-8")
            self._wait_for_port()
            return {**self.status(), "ok": True, "message": "Qdrant 启动中"}

        if self._docker_bin():
            result = self._start_with_docker()
            self._wait_for_port()
            return {**self.status(), **result}

        return {
            **self.status(),
            "ok": False,
            "message": "未找到 qdrant 命令或 Docker CLI，无法自动启动 Qdrant",
        }

    def stop(self) -> dict:
        container = self._container_status()
        if container.get("exists"):
            result = self._run([self._docker_bin() or "docker", "stop", self.container_name], timeout=15)
            return {
                **self.status(),
                "ok": result.returncode == 0,
                "message": "Qdrant 已发送停止指令" if result.returncode == 0 else self._stderr(result),
            }

        pid = self._read_pid() or self._pid_on_port()
        if not pid:
            return {**self.status(), "ok": True, "message": "Qdrant 未运行"}
        if self._is_running(pid):
            os.kill(pid, signal.SIGTERM)
        self.pid_path.unlink(missing_ok=True)
        return {**self.status(), "ok": True, "message": "Qdrant 已发送停止指令"}

    def restart(self) -> dict:
        self.stop()
        return self.start() | {"message": "Qdrant 重启中"}

    def _start_with_docker(self) -> dict:
        if not self._docker_ready():
            started = self._open_docker_desktop()
            if started and self._wait_for_docker():
                pass
            else:
                hint = "Docker Desktop 正在启动或未就绪，请稍后再点一次" if started else "Docker CLI 存在，但 Docker Desktop 未运行或无法打开"
                return {"ok": False, "message": hint}

        container = self._container_status()
        if container.get("exists"):
            result = self._run([self._docker_bin() or "docker", "start", self.container_name], timeout=20)
            return {
                "ok": result.returncode == 0,
                "message": "Qdrant Docker 容器启动中" if result.returncode == 0 else self._stderr(result),
            }

        result = self._run(
            [
                self._docker_bin() or "docker",
                "run",
                "-d",
                "--name",
                self.container_name,
                "-p",
                f"{self.port}:6333",
                "-v",
                f"{self.storage_dir}:/qdrant/storage",
                "qdrant/qdrant",
            ],
            timeout=120,
        )
        return {
            "ok": result.returncode == 0,
            "message": "Qdrant Docker 容器创建并启动中" if result.returncode == 0 else self._stderr(result),
        }

    def _availability(self) -> tuple[bool, str]:
        if self._qdrant_bin():
            return True, "已找到 qdrant 命令"
        docker_bin = self._docker_bin()
        if docker_bin:
            ready, error = self._docker_state()
            if ready:
                return True, "可通过 Docker 启动 Qdrant"
            if Path("/Applications/Docker.app").exists():
                return True, f"Docker CLI 已找到：{docker_bin}；Docker Desktop 未就绪，点击启动时会尝试自动打开"
            return False, f"Docker CLI 已找到：{docker_bin}；Docker daemon 未就绪：{error}"
        return False, "未找到 qdrant 命令或 Docker CLI"

    def _docker_ready(self) -> bool:
        ready, _error = self._docker_state()
        return ready

    def _docker_state(self) -> tuple[bool, str]:
        docker_bin = self._docker_bin()
        if not docker_bin:
            return False, "未找到 Docker CLI"
        result = self._run([docker_bin, "info"], timeout=5)
        return result.returncode == 0, self._stderr(result) if result.returncode != 0 else ""

    def _docker_bin(self) -> str:
        return self._command_path("docker", [
            "/usr/local/bin/docker",
            "/opt/homebrew/bin/docker",
            "/Applications/Docker.app/Contents/Resources/bin/docker",
        ])

    def _qdrant_bin(self) -> str:
        return self._command_path("qdrant", [
            "/usr/local/bin/qdrant",
            "/opt/homebrew/bin/qdrant",
        ])

    @staticmethod
    def _command_path(name: str, candidates: list[str]) -> str:
        found = shutil.which(name)
        if found:
            return found
        for candidate in candidates:
            if Path(candidate).exists():
                return candidate
        return ""

    def _open_docker_desktop(self) -> bool:
        if not Path("/Applications/Docker.app").exists():
            return False
        result = self._run(["open", "-a", "Docker"], timeout=5)
        return result.returncode == 0

    def _wait_for_docker(self, seconds: float = 75) -> bool:
        deadline = time.time() + seconds
        while time.time() < deadline:
            if self._docker_ready():
                return True
            time.sleep(2)
        return False

    def _container_status(self) -> dict:
        docker_bin = self._docker_bin()
        if not docker_bin:
            return {"exists": False, "running": False, "name": self.container_name}
        result = self._run(
            [docker_bin, "inspect", "-f", "{{.State.Running}}", self.container_name],
            timeout=5,
        )
        if result.returncode != 0:
            return {"exists": False, "running": False, "name": self.container_name}
        return {
            "exists": True,
            "running": result.stdout.strip().lower() == "true",
            "name": self.container_name,
        }

    def _wait_for_port(self, seconds: float = 6) -> None:
        deadline = time.time() + seconds
        while time.time() < deadline:
            if self._port_is_open():
                return
            time.sleep(0.3)

    def _read_pid(self) -> int | None:
        try:
            return int(self.pid_path.read_text(encoding="utf-8").strip())
        except Exception:
            return None

    @staticmethod
    def _is_running(pid: int | None) -> bool:
        if not pid:
            return False
        try:
            os.kill(pid, 0)
            return True
        except OSError:
            return False

    def _port_is_open(self) -> bool:
        try:
            with socket.create_connection((self.host, self.port), timeout=0.3):
                return True
        except OSError:
            return False

    def _pid_on_port(self) -> int | None:
        try:
            output = subprocess.check_output(
                ["lsof", "-tiTCP:%s" % self.port, "-sTCP:LISTEN"],
                stderr=subprocess.DEVNULL,
                text=True,
                timeout=1,
            )
        except Exception:
            return None
        for line in output.splitlines():
            try:
                return int(line.strip())
            except Exception:
                continue
        return None

    @staticmethod
    def _run(command: list[str], timeout: int = 10) -> subprocess.CompletedProcess:
        env = os.environ.copy()
        stable_path = "/usr/local/bin:/opt/homebrew/bin:/usr/bin:/bin:/usr/sbin:/sbin"
        env["PATH"] = f"{stable_path}:{env.get('PATH', '')}"
        try:
            return subprocess.run(
                command,
                capture_output=True,
                text=True,
                timeout=timeout,
                env=env,
            )
        except Exception as exc:
            return subprocess.CompletedProcess(command, 1, "", str(exc))

    @staticmethod
    def _stderr(result: subprocess.CompletedProcess) -> str:
        return (result.stderr or result.stdout or "操作失败").strip()


class LocalSupportSystem:
    def __init__(self, base_dir: Path):
        self.base_dir = base_dir
        self.app = SystemController(base_dir)
        self.qdrant = QdrantController(base_dir)

    def status(self) -> dict:
        app_status = self.app.status()
        qdrant_status = self.qdrant.status()
        return {
            **app_status,
            "base_dir": str(self.base_dir),
            "app": app_status,
            "qdrant": qdrant_status,
            "running": app_status["running"],
            "all_running": app_status["running"] and qdrant_status["running"],
        }

    def start_all(self) -> dict:
        qdrant_result = self.qdrant.start()
        app_result = self.app.start()
        status = self.status()
        ok = bool(qdrant_result.get("ok")) and bool(app_result.get("ok"))
        return {
            **status,
            "ok": ok,
            "message": self._join_messages(qdrant_result, app_result),
            "qdrant_result": qdrant_result,
            "app_result": app_result,
        }

    def stop_all(self) -> dict:
        app_result = self.app.stop()
        qdrant_result = self.qdrant.stop()
        return {
            **self.status(),
            "ok": bool(qdrant_result.get("ok")) and bool(app_result.get("ok")),
            "message": self._join_messages(app_result, qdrant_result),
            "qdrant_result": qdrant_result,
            "app_result": app_result,
        }

    def restart_all(self) -> dict:
        self.stop_all()
        return self.start_all() | {"message": "Qdrant 和业务服务重启中"}

    @staticmethod
    def _join_messages(*items: dict) -> str:
        return "；".join(str(item.get("message", "")).strip() for item in items if item.get("message"))
