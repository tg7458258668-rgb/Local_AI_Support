from fastapi import APIRouter

from support_app.services.system_control import LocalSupportSystem
from support_app.settings import settings

router = APIRouter(prefix="/api/system", tags=["system"])
system = LocalSupportSystem(settings.base_dir)


@router.get("/status")
def status():
    return system.status()


@router.post("/start")
def start():
    return system.start_all()


@router.post("/stop")
def stop():
    return system.stop_all()


@router.post("/restart")
def restart():
    return system.restart_all()


@router.post("/start-all")
def start_all():
    return system.start_all()


@router.post("/stop-all")
def stop_all():
    return system.stop_all()


@router.post("/restart-all")
def restart_all():
    return system.restart_all()


@router.post("/app/start")
def start_app():
    return system.app.start()


@router.post("/app/stop")
def stop_app():
    return system.app.stop()


@router.post("/app/restart")
def restart_app():
    return system.app.restart()


@router.post("/qdrant/start")
def start_qdrant():
    return system.qdrant.start()


@router.post("/qdrant/stop")
def stop_qdrant():
    return system.qdrant.stop()


@router.post("/qdrant/restart")
def restart_qdrant():
    return system.qdrant.restart()
