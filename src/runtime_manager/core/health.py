from __future__ import annotations

import time

from contracts import ObservedState
from docker.models.containers import Container

from runtime_manager.core.docker_client import DockerRuntimeClient
from runtime_manager.settings import RuntimeManagerSettings


class RuntimeHealthChecker:
    def __init__(
        self,
        docker_client: DockerRuntimeClient,
        settings: RuntimeManagerSettings | None = None,
    ) -> None:
        self._docker_client = docker_client
        self._settings = settings or RuntimeManagerSettings()

    def wait_for_state(
        self,
        container: Container,
        network_name: str,
        internal_endpoint: str,
    ) -> ObservedState:
        deadline = time.monotonic() + self._settings.readiness_timeout_seconds
        while True:
            state = self.observe(container, network_name, internal_endpoint)
            if state in {ObservedState.RUNNING, ObservedState.STOPPED, ObservedState.ERROR}:
                return state

            if time.monotonic() >= deadline:
                return state

            time.sleep(self._settings.readiness_poll_interval_seconds)

    def observe(
        self,
        container: Container,
        network_name: str,
        internal_endpoint: str,
    ) -> ObservedState:
        container = self._docker_client.reload_container(container)
        status = container.status.lower()

        if status == "running":
            if self._docker_client.probe_tcp_endpoint(
                network_name=network_name,
                target_url=internal_endpoint,
                timeout_seconds=self._settings.readiness_poll_interval_seconds,
            ):
                return ObservedState.RUNNING
            return ObservedState.CREATING

        if status in {"created", "restarting"}:
            return ObservedState.CREATING

        if status in {"exited", "dead"}:
            exit_code = container.attrs["State"].get("ExitCode", 1)
            if exit_code == 0:
                return ObservedState.STOPPED
            return ObservedState.ERROR

        return ObservedState.ERROR

