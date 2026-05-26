from __future__ import annotations

import argparse
import json
import plistlib
import re
import shutil
import subprocess
import time
from pathlib import Path


def clean_text(value: str) -> str:
    value = re.sub(r"[\u200b\u200c\u200d\ufeff]", "", value or "")
    return re.sub(r"\s+", " ", value).strip()


def strip_duration(value: str) -> str:
    return clean_text(re.sub(r"\b\d{2}:\d{2}\b", "", value))


def safe_name(value: str, max_len: int = 80) -> str:
    value = strip_duration(value)
    value = re.sub(r"[\\/:*?\"<>|#%&{}$!'@+`=]", "_", value)
    value = re.sub(r"\s+", "_", value).strip("._ ")
    return (value or "video")[:max_len].strip("._ ")


def norm(value: str) -> str:
    value = strip_duration(value).lower()
    value = re.sub(r"\.(mp4|mov|m4v)\b", "", value)
    value = re.sub(r"[\[\]【】（）()《》〈〉：:，,。.\-—_+/\s]", "", value)
    return value


def prepare_records(items: list[dict]) -> list[dict]:
    seen = set()
    records = []
    for item in items:
        title = strip_duration(item.get("cellText", ""))
        url = item.get("src", "")
        if not title or not url:
            continue
        key = (norm(title), url.split("?")[0])
        if key in seen:
            continue
        seen.add(key)
        idx = len(records) + 1
        duration = item.get("duration", "")
        base = f"{idx:03d}_{safe_name(title)}"
        records.append(
            {
                "index": idx,
                "title": title,
                "duration": duration,
                "url": url,
                "mp4": f"{base}.mp4",
                "webloc": f"{base}.webloc",
            }
        )
    return records


def load_webloc_url(path: Path) -> str | None:
    try:
        with path.open("rb") as f:
            data = plistlib.load(f)
        url = data.get("URL")
        return url if isinstance(url, str) else None
    except Exception:
        return None


def downloads_snapshot(downloads_dir: Path) -> set[Path]:
    return {p for p in downloads_dir.glob("*.mp4") if p.is_file()}


def wait_for_new_mp4(downloads_dir: Path, before: set[Path], started_at: float, timeout: int) -> Path:
    deadline = time.time() + timeout
    last_candidate: Path | None = None
    last_size = -1
    stable_count = 0
    while time.time() < deadline:
        candidates = [
            p
            for p in downloads_dir.glob("*.mp4")
            if p.is_file() and p not in before and p.stat().st_mtime >= started_at - 2
        ]
        candidates.sort(key=lambda p: p.stat().st_mtime, reverse=True)
        if candidates:
            candidate = candidates[0]
            size = candidate.stat().st_size
            if candidate == last_candidate and size == last_size and size > 1024:
                stable_count += 1
            else:
                stable_count = 0
            last_candidate = candidate
            last_size = size
            if stable_count >= 2:
                return candidate
        time.sleep(0.8)
    raise TimeoutError("No completed mp4 appeared in Downloads")


def open_url_in_chrome(url: str) -> None:
    subprocess.run(["open", "-g", "-a", "Google Chrome", url], check=False)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--videos-json", type=Path, required=True)
    parser.add_argument("--videos-dir", type=Path, required=True)
    parser.add_argument("--downloads-dir", type=Path, default=Path.home() / "Downloads")
    parser.add_argument("--start", type=int, default=1)
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--timeout", type=int, default=180)
    parser.add_argument("--sleep-between", type=float, default=1.2)
    args = parser.parse_args()

    args.videos_dir.mkdir(parents=True, exist_ok=True)
    records = prepare_records(json.loads(args.videos_json.read_text(encoding="utf-8")))
    if args.limit > 0:
        records = records[args.start - 1 : args.start - 1 + args.limit]
    else:
        records = records[args.start - 1 :]

    status_path = args.videos_dir / "download_status.json"
    failures = []
    downloaded = []
    skipped = []

    for rec in records:
        target = args.videos_dir / rec["mp4"]
        if target.exists() and target.stat().st_size > 1024:
            skipped.append(rec["index"])
            continue

        url = rec["url"]
        webloc_path = args.videos_dir / rec["webloc"]
        if webloc_path.exists():
            url = load_webloc_url(webloc_path) or url

        before = downloads_snapshot(args.downloads_dir)
        started = time.time()
        print(f"[{rec['index']:03d}] downloading {rec['title']}", flush=True)
        open_url_in_chrome(url)
        try:
            source = wait_for_new_mp4(args.downloads_dir, before, started, args.timeout)
            tmp_target = target.with_suffix(".mp4.part")
            if tmp_target.exists():
                tmp_target.unlink()
            shutil.move(str(source), str(tmp_target))
            tmp_target.rename(target)
            downloaded.append({"index": rec["index"], "file": str(target), "bytes": target.stat().st_size})
            print(f"[{rec['index']:03d}] saved {target.name} ({target.stat().st_size} bytes)", flush=True)
        except Exception as exc:
            failures.append({"index": rec["index"], "title": rec["title"], "error": str(exc), "url": url})
            print(f"[{rec['index']:03d}] FAILED {exc}", flush=True)
        status_path.write_text(
            json.dumps(
                {"downloaded": downloaded, "skipped": skipped, "failures": failures},
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        time.sleep(args.sleep_between)

    print(
        json.dumps(
            {"downloaded": len(downloaded), "skipped": len(skipped), "failures": len(failures), "status": str(status_path)},
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
