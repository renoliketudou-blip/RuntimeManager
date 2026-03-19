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
from runtime_manager.core.exceptions import RuntimeNotFoundError


class FakeRuntimeManagerService:
    def is_ready(self) -> bool:
        return True

    def ensure_running(self, request: EnsureRunningRequest) -> EnsureRunningResponse:
        return EnsureRunningResponse(
            runtime_id=request.runtime_id,
            observed_state=ObservedState.RUNNING,
            internal_endpoint="http://crewclaw-rt-u-001-rt-001:18789",
            message="already running",
        )

    def stop(self, request: StopRequest) -> StopResponse:
        return StopResponse(runtime_id=request.runtime_id, message="stopped")

    def delete(self, request: DeleteRequest) -> DeleteResponse:
        return DeleteResponse(runtime_id=request.runtime_id, message="deleted")

    def get_status(self, runtime_id: str) -> RuntimeStatusResponse:
        if runtime_id == "missing":
            raise RuntimeNotFoundError("runtime not found")
        return RuntimeStatusResponse(
            runtime_id=runtime_id,
            observed_state=ObservedState.RUNNING,
            internal_endpoint="http://crewclaw-rt-u-001-rt-001:18789",
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
            "imageRef": "ghcr.io/openclaw/openclaw@sha256:123",
            "volumeId": "vol_001",
            "routeHost": "u-001.crewclaw.example.com",
            "configMount": {
                "configFilePath": "/tmp/openclaw.json",
                "secretFilePath": "/tmp/gateway.token",
            },
            "retentionPolicy": "preserve_workspace",
            "compat": {
                "openclawConfigDir": "/tmp/config",
                "openclawWorkspaceDir": "/tmp/workspace",
                "networkName": "crewclaw_shared",
                "gatewayPort": 18789,
                "bridgePort": 18790,
            },
        },
    )

    body = response.json()
    assert response.status_code == 200
    assert body["runtimeId"] == "rt_001"
    assert body["internalEndpoint"] == "http://crewclaw-rt-u-001-rt-001:18789/"


def test_get_status_returns_not_found_error_payload() -> None:
    client = make_client()

    response = client.get("/internal/runtime-manager/containers/missing")

    assert response.status_code == 404
    assert response.json() == {
        "code": "RUNTIME_NOT_FOUND",
        "message": "runtime not found",
    }


def test_readyz_returns_ready() -> None:
    client = make_client()

    response = client.get("/readyz")

    assert response.status_code == 200
    assert response.json() == {"status": "ready"}
