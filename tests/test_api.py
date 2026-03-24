from fastapi.testclient import TestClient

from contracts import (
    DeleteRequest,
    DeleteResponse,
    EnsureRunningRequest,
    EnsureRunningResponse,
    ObservedState,
    RuntimeStatusResponse,
    StopRequest,
    StopResponse,
)
from runtime_manager.api.dependencies import get_runtime_manager_service
from runtime_manager.app import create_app
class FakeRuntimeManagerService:
    def is_ready(self) -> bool:
        return True

    def ensure_running(self, request: EnsureRunningRequest) -> EnsureRunningResponse:
        return EnsureRunningResponse(
            runtime_id=request.runtime_id,
            observed_state=ObservedState.RUNNING,
            internal_endpoint="http://rt-rt_001:18789",
            message="already running",
        )

    def stop(self, request: StopRequest) -> StopResponse:
        return StopResponse(runtime_id=request.runtime_id, message="stopped")

    def delete(self, request: DeleteRequest) -> DeleteResponse:
        return DeleteResponse(runtime_id=request.runtime_id, message="deleted")

    def get_status(self, runtime_id: str) -> RuntimeStatusResponse:
        if runtime_id == "missing":
            return RuntimeStatusResponse(
                runtime_id=runtime_id,
                observed_state=ObservedState.DELETED,
                internal_endpoint=None,
                message="not found as container fact",
            )
        return RuntimeStatusResponse(
            runtime_id=runtime_id,
            observed_state=ObservedState.RUNNING,
            internal_endpoint="http://rt-rt_001:18789",
            message="ok",
        )


def make_client() -> TestClient:
    app = create_app()
    app.dependency_overrides[get_runtime_manager_service] = FakeRuntimeManagerService
    return TestClient(app)


def test_ensure_running_endpoint_uses_camel_case() -> None:
    client = make_client()

    response = client.post(
        "/internal/runtime-manager/containers/ensure-running",
        json={
            "userId": "u_001",
            "runtimeId": "rt_001",
            "volumeId": "vol_001",
            "routeHost": "u-001.clawloops.example.com",
            "configMount": {
                "configFilePath": "/tmp/openclaw.json",
                "secretFilePath": "/tmp/gateway.token",
            },
            "retentionPolicy": "preserve_workspace",
            "compat": {
                "openclawConfigDir": "/tmp/config",
                "openclawWorkspaceDir": "/tmp/workspace",
            },
        },
    )

    body = response.json()
    assert response.status_code == 200
    assert body["runtimeId"] == "rt_001"
    assert body["internalEndpoint"] == "http://rt-rt_001:18789"


def test_get_status_returns_deleted_payload_when_missing() -> None:
    client = make_client()

    response = client.get("/internal/runtime-manager/containers/missing")

    assert response.status_code == 200
    assert response.json() == {
        "runtimeId": "missing",
        "observedState": "deleted",
        "internalEndpoint": None,
        "message": "not found as container fact",
    }


def test_readyz_returns_ready() -> None:
    client = make_client()

    response = client.get("/readyz")

    assert response.status_code == 200
    assert response.json() == {"status": "ready"}
