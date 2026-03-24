from __future__ import annotations

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

from runtime_manager.core.docker_client import DockerRuntimeClient
from runtime_manager.core.exceptions import (
    DockerRuntimeError,
    RuntimeContractDriftError,
    RuntimeDeleteFailedError,
    RuntimeStartFailedError,
    RuntimeStopFailedError,
)
from runtime_manager.core.health import RuntimeHealthChecker
from runtime_manager.core.paths import RuntimePathManager
from runtime_manager.core.specs import RuntimeSpecFactory
from runtime_manager.constants import DEFAULT_NETWORK_NAME
from runtime_manager.settings import RuntimeManagerSettings


class RuntimeManagerService:
    def __init__(
        self,
        docker_client: DockerRuntimeClient | None = None,
        path_manager: RuntimePathManager | None = None,
        health_checker: RuntimeHealthChecker | None = None,
        settings: RuntimeManagerSettings | None = None,
    ) -> None:
        self._settings = settings or RuntimeManagerSettings()
        self._docker_client = docker_client or DockerRuntimeClient(settings=self._settings)
        self._path_manager = path_manager or RuntimePathManager()
        self._health_checker = health_checker or RuntimeHealthChecker(
            docker_client=self._docker_client,
            settings=self._settings,
        )

    def is_ready(self) -> bool:
        return self._docker_client.ping()

    def ensure_running(self, request: EnsureRunningRequest) -> EnsureRunningResponse:
        self._docker_client.ensure_network_exists(DEFAULT_NETWORK_NAME)
        paths = self._path_manager.prepare(request)
        spec = RuntimeSpecFactory.build(request=request, paths=paths)
        container = self._docker_client.get_runtime_container(
            runtime_id=request.runtime_id,
            user_id=request.user_id,
        )

        if container is None:
            try:
                self._docker_client.run_init_permissions(str(paths.config_dir), str(paths.workspace_dir))
                container = self._docker_client.create_container(spec)
                self._docker_client.start_container(container)
                state = self._health_checker.wait_for_state(
                    container=container,
                    network_name=spec.network_name,
                    internal_endpoint=spec.internal_endpoint,
                )
            except DockerRuntimeError as exc:
                raise RuntimeStartFailedError(str(exc)) from exc
            message = "creating" if state == ObservedState.CREATING else "running"
            return EnsureRunningResponse(
                runtime_id=request.runtime_id,
                observed_state=state,
                internal_endpoint=spec.internal_endpoint,
                message=message,
            )

        state = self._health_checker.observe(
            container=container,
            network_name=DEFAULT_NETWORK_NAME,
            internal_endpoint=spec.internal_endpoint,
        )
        self._assert_no_contract_drift(container=container, request=request, spec=spec)
        if state == ObservedState.RUNNING:
            return EnsureRunningResponse(
                runtime_id=request.runtime_id,
                observed_state=ObservedState.RUNNING,
                internal_endpoint=spec.internal_endpoint,
                message="already running",
            )

        try:
            self._docker_client.run_init_permissions(str(paths.config_dir), str(paths.workspace_dir))
            self._docker_client.start_container(container)
            state = self._health_checker.wait_for_state(
                container=container,
                network_name=DEFAULT_NETWORK_NAME,
                internal_endpoint=spec.internal_endpoint,
            )
        except DockerRuntimeError as exc:
            raise RuntimeStartFailedError(str(exc)) from exc
        message = "creating" if state == ObservedState.CREATING else "running"
        return EnsureRunningResponse(
            runtime_id=request.runtime_id,
            observed_state=state,
            internal_endpoint=spec.internal_endpoint,
            message=message,
        )

    def stop(self, request: StopRequest) -> StopResponse:
        container = self._docker_client.get_runtime_container(
            runtime_id=request.runtime_id,
            user_id=request.user_id,
        )
        if container is None:
            return StopResponse(runtime_id=request.runtime_id, message="already stopped")

        network_name = container.attrs["HostConfig"]["NetworkMode"]
        state = self._health_checker.observe(
            container=container,
            network_name=network_name,
            internal_endpoint=self._internal_endpoint_for(request.runtime_id),
        )
        if state in {ObservedState.STOPPED, ObservedState.ERROR}:
            return StopResponse(runtime_id=request.runtime_id, message="already stopped")

        try:
            self._docker_client.stop_container(container, timeout=self._settings.stop_timeout_seconds)
        except DockerRuntimeError as exc:
            raise RuntimeStopFailedError(str(exc)) from exc
        return StopResponse(runtime_id=request.runtime_id, message="stopped")

    def delete(self, request: DeleteRequest) -> DeleteResponse:
        container = self._docker_client.get_runtime_container(
            runtime_id=request.runtime_id,
            user_id=request.user_id,
        )
        labels = None
        if container is not None:
            labels = dict(container.labels)
            try:
                self._docker_client.remove_container(container)
            except DockerRuntimeError as exc:
                raise RuntimeDeleteFailedError(str(exc)) from exc

        if request.retention_policy.value == "wipe_workspace":
            try:
                self._path_manager.wipe(request, labels)
            except OSError as exc:
                raise RuntimeDeleteFailedError(str(exc)) from exc

        return DeleteResponse(runtime_id=request.runtime_id, message="deleted")

    def get_status(self, runtime_id: str) -> RuntimeStatusResponse:
        container = self._docker_client.get_runtime_container(runtime_id=runtime_id)
        if container is None:
            return RuntimeStatusResponse(
                runtime_id=runtime_id,
                observed_state=ObservedState.DELETED,
                internal_endpoint=None,
                message="not found as container fact",
            )

        internal_endpoint = self._internal_endpoint_for(runtime_id)
        network_name = container.attrs["HostConfig"]["NetworkMode"]
        state = self._health_checker.observe(
            container=container,
            network_name=network_name,
            internal_endpoint=internal_endpoint,
        )
        return RuntimeStatusResponse(
            runtime_id=runtime_id,
            observed_state=state,
            internal_endpoint=internal_endpoint,
            message="ok",
        )

    @staticmethod
    def _internal_endpoint_for(runtime_id: str) -> str:
        return f"http://rt-{runtime_id}:18789"

    @staticmethod
    def _assert_no_contract_drift(container, request: EnsureRunningRequest, spec) -> None:
        labels = container.labels or {}
        expected_labels = spec.labels
        for key in (
            "clawloops.managed",
            "clawloops.userId",
            "clawloops.runtimeId",
            "clawloops.volumeId",
            "clawloops.retentionPolicy",
            "clawloops.configDir",
            "clawloops.workspaceDir",
        ):
            if labels.get(key) != expected_labels.get(key):
                raise RuntimeContractDriftError("existing container contract drift detected")

        network_mode = (container.attrs.get("HostConfig") or {}).get("NetworkMode")
        if network_mode != spec.network_name:
            raise RuntimeContractDriftError("existing container contract drift detected")

        command = (container.attrs.get("Config") or {}).get("Cmd") or []
        if tuple(command) != spec.command:
            raise RuntimeContractDriftError("existing container contract drift detected")

