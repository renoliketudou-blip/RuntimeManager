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
from runtime_manager.core.exceptions import RuntimeNotFoundError
from runtime_manager.core.health import RuntimeHealthChecker
from runtime_manager.core.paths import RuntimePathManager
from runtime_manager.core.specs import RuntimeSpecFactory
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
        self._docker_client.ensure_network_exists(request.compat.network_name)
        paths = self._path_manager.prepare(request)
        gateway_token = self._path_manager.resolve_gateway_token(paths)
        spec = RuntimeSpecFactory.build(request=request, paths=paths, gateway_token=gateway_token)
        container = self._docker_client.get_runtime_container(
            runtime_id=request.runtime_id,
            user_id=request.user_id,
        )

        if container is None:
            self._docker_client.run_init_permissions(str(paths.config_dir), str(paths.workspace_dir))
            container = self._docker_client.create_container(spec)
            self._docker_client.start_container(container)
            state = self._health_checker.wait_for_state(
                container=container,
                network_name=spec.network_name,
                internal_endpoint=spec.internal_endpoint,
            )
            message = "creating" if state == ObservedState.CREATING else "running"
            return EnsureRunningResponse(
                runtime_id=request.runtime_id,
                observed_state=state,
                internal_endpoint=spec.internal_endpoint,
                message=message,
            )

        state = self._health_checker.observe(
            container=container,
            network_name=request.compat.network_name,
            internal_endpoint=spec.internal_endpoint,
        )
        if state == ObservedState.RUNNING:
            return EnsureRunningResponse(
                runtime_id=request.runtime_id,
                observed_state=ObservedState.RUNNING,
                internal_endpoint=spec.internal_endpoint,
                message="already running",
            )

        self._docker_client.run_init_permissions(str(paths.config_dir), str(paths.workspace_dir))
        self._docker_client.start_container(container)
        state = self._health_checker.wait_for_state(
            container=container,
            network_name=request.compat.network_name,
            internal_endpoint=spec.internal_endpoint,
        )
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
            internal_endpoint=self._internal_endpoint_for(container.name),
        )
        if state in {ObservedState.STOPPED, ObservedState.ERROR}:
            return StopResponse(runtime_id=request.runtime_id, message="already stopped")

        self._docker_client.stop_container(container, timeout=self._settings.stop_timeout_seconds)
        return StopResponse(runtime_id=request.runtime_id, message="stopped")

    def delete(self, request: DeleteRequest) -> DeleteResponse:
        container = self._docker_client.get_runtime_container(
            runtime_id=request.runtime_id,
            user_id=request.user_id,
        )
        labels = None
        if container is not None:
            labels = dict(container.labels)
            self._docker_client.remove_container(container)

        if request.retention_policy.value == "wipe_workspace":
            self._path_manager.wipe(request, labels)

        return DeleteResponse(runtime_id=request.runtime_id, message="deleted")

    def get_status(self, runtime_id: str) -> RuntimeStatusResponse:
        container = self._docker_client.get_runtime_container(runtime_id=runtime_id)
        if container is None:
            raise RuntimeNotFoundError("runtime not found")

        internal_endpoint = self._internal_endpoint_for(container.name)
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
    def _internal_endpoint_for(container_name: str) -> str:
        return f"http://{container_name}:18789"

