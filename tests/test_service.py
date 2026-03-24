from pathlib import Path

from contracts import (
    DeleteRequest,
    EnsureRunningRequest,
    ObservedState,
    RetentionPolicy,
    StopRequest,
)
from runtime_manager.core.service import RuntimeManagerService
from runtime_manager.core.specs import RuntimePaths
from runtime_manager.settings import RuntimeManagerSettings


def make_request() -> EnsureRunningRequest:
    return EnsureRunningRequest.model_validate(
        {
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
            "env": {"OPENCLAW_GATEWAY_TOKEN": "token-123"},
        }
    )


class FakeContainer:
    def __init__(self, name: str, status: str, labels: dict[str, str] | None = None) -> None:
        self.name = name
        self.status = status
        self.labels = labels or {}
        self.attrs = {
            "Created": "2026-03-19T00:00:00Z",
            "HostConfig": {"NetworkMode": "crewclaw_shared"},
            "State": {"ExitCode": 0},
        }

    def reload(self) -> None:
        return None


class FakeDockerClient:
    def __init__(self, container: FakeContainer | None = None) -> None:
        self.container = container
        self.created_spec = None
        self.started = False
        self.stopped = False
        self.removed = False
        self.network_checked = None

    def ping(self) -> bool:
        return True

    def ensure_network_exists(self, network_name: str) -> None:
        self.network_checked = network_name

    def get_runtime_container(self, runtime_id: str, user_id: str | None = None) -> FakeContainer | None:
        return self.container

    def run_init_permissions(self, config_dir: str, workspace_dir: str) -> None:
        self.init_permissions = (config_dir, workspace_dir)

    def create_container(self, spec):
        self.created_spec = spec
        self.container = FakeContainer(name=spec.container_name, status="running", labels=spec.labels)
        return self.container

    def start_container(self, container: FakeContainer) -> None:
        self.started = True
        container.status = "running"

    def stop_container(self, container: FakeContainer, timeout: int) -> None:
        self.stopped = True
        container.status = "exited"

    def remove_container(self, container: FakeContainer) -> None:
        self.removed = True
        self.container = None


class FakePathManager:
    def __init__(self) -> None:
        self.wiped_with = None

    def prepare(self, request: EnsureRunningRequest) -> RuntimePaths:
        return RuntimePaths(
            config_dir=Path("/tmp/config"),
            workspace_dir=Path("/tmp/workspace"),
            config_file=Path("/tmp/openclaw.json"),
            secret_file=Path("/tmp/gateway.token"),
        )

    def resolve_gateway_token(self, paths: RuntimePaths) -> str:
        return "token-123"

    def wipe(self, request: DeleteRequest, labels: dict[str, str] | None) -> None:
        self.wiped_with = labels


class FakeHealthChecker:
    def __init__(self, state: ObservedState) -> None:
        self.state = state

    def wait_for_state(self, container, network_name: str, internal_endpoint: str) -> ObservedState:
        return self.state

    def observe(self, container, network_name: str, internal_endpoint: str) -> ObservedState:
        return self.state


def make_service(
    docker_client: FakeDockerClient,
    path_manager: FakePathManager,
    health_checker: FakeHealthChecker,
) -> RuntimeManagerService:
    return RuntimeManagerService(
        docker_client=docker_client,
        path_manager=path_manager,
        health_checker=health_checker,
        settings=RuntimeManagerSettings(readiness_timeout_seconds=0.1, readiness_poll_interval_seconds=0.1),
    )


def test_ensure_running_creates_container_when_missing() -> None:
    docker_client = FakeDockerClient()
    path_manager = FakePathManager()
    service = make_service(
        docker_client=docker_client,
        path_manager=path_manager,
        health_checker=FakeHealthChecker(ObservedState.RUNNING),
    )

    response = service.ensure_running(make_request())

    assert docker_client.created_spec is not None
    assert docker_client.started is True
    assert response.observed_state == ObservedState.RUNNING
    assert response.message == "running"


def test_ensure_running_is_idempotent_when_already_running() -> None:
    container = FakeContainer(
        name="rt-rt_001",
        status="running",
        labels={
            "clawloops.managed": "true",
            "clawloops.userId": "u_001",
            "clawloops.runtimeId": "rt_001",
            "clawloops.volumeId": "vol_001",
            "clawloops.routeHost": "u-001.clawloops.example.com",
            "clawloops.retentionPolicy": "preserve_workspace",
            "clawloops.configDir": "/tmp/config",
            "clawloops.workspaceDir": "/tmp/workspace",
        },
    )
    container.attrs["Config"] = {"Cmd": ["node", "dist/index.js", "gateway", "--bind", "lan", "--port", "18789"]}
    container.attrs["HostConfig"] = {"NetworkMode": "clawloops_shared"}
    docker_client = FakeDockerClient(container=container)
    service = make_service(
        docker_client=docker_client,
        path_manager=FakePathManager(),
        health_checker=FakeHealthChecker(ObservedState.RUNNING),
    )

    response = service.ensure_running(make_request())

    assert docker_client.created_spec is None
    assert response.message == "already running"
    assert response.observed_state == ObservedState.RUNNING


def test_stop_returns_already_stopped_when_container_missing() -> None:
    service = make_service(
        docker_client=FakeDockerClient(),
        path_manager=FakePathManager(),
        health_checker=FakeHealthChecker(ObservedState.STOPPED),
    )

    response = service.stop(StopRequest(user_id="u_001", runtime_id="rt_001"))

    assert response.message == "already stopped"


def test_delete_wipes_workspace_when_requested() -> None:
    labels = {
        "clawloops.configDir": "/tmp/config",
        "clawloops.workspaceDir": "/tmp/workspace",
    }
    container = FakeContainer(name="rt-rt_001", status="exited", labels=labels)
    docker_client = FakeDockerClient(container=container)
    path_manager = FakePathManager()
    service = make_service(
        docker_client=docker_client,
        path_manager=path_manager,
        health_checker=FakeHealthChecker(ObservedState.STOPPED),
    )

    response = service.delete(
        DeleteRequest(
            user_id="u_001",
            runtime_id="rt_001",
            retention_policy=RetentionPolicy.WIPE_WORKSPACE,
        )
    )

    assert docker_client.removed is True
    assert path_manager.wiped_with == labels
    assert response.observed_state == ObservedState.DELETED
