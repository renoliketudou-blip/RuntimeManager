from fastapi import APIRouter, Depends, status
from fastapi.responses import JSONResponse

from contracts import (
    DeleteRequest,
    DeleteResponse,
    EnsureRunningRequest,
    EnsureRunningResponse,
    RuntimeStatusResponse,
    StopRequest,
    StopResponse,
)
from runtime_manager.api.dependencies import get_runtime_manager_service
from runtime_manager.core.service import RuntimeManagerService

router = APIRouter()


@router.post(
    "/internal/runtime-manager/containers/ensure-running",
    response_model=EnsureRunningResponse,
)
def ensure_running(
    request: EnsureRunningRequest,
    service: RuntimeManagerService = Depends(get_runtime_manager_service),
) -> EnsureRunningResponse:
    return service.ensure_running(request)


@router.post(
    "/internal/runtime-manager/containers/stop",
    response_model=StopResponse,
)
def stop_container(
    request: StopRequest,
    service: RuntimeManagerService = Depends(get_runtime_manager_service),
) -> StopResponse:
    return service.stop(request)


@router.post(
    "/internal/runtime-manager/containers/delete",
    response_model=DeleteResponse,
)
def delete_container(
    request: DeleteRequest,
    service: RuntimeManagerService = Depends(get_runtime_manager_service),
) -> DeleteResponse:
    return service.delete(request)


@router.get(
    "/internal/runtime-manager/containers/{runtime_id}",
    response_model=RuntimeStatusResponse,
)
def get_runtime_status(
    runtime_id: str,
    service: RuntimeManagerService = Depends(get_runtime_manager_service),
) -> RuntimeStatusResponse:
    return service.get_status(runtime_id)


@router.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/readyz")
def readyz(
    service: RuntimeManagerService = Depends(get_runtime_manager_service),
) -> dict[str, str]:
    if service.is_ready():
        return {"status": "ready"}
    return JSONResponse(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        content={"status": "not-ready"},
    )

