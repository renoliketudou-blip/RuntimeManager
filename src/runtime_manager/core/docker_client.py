from __future__ import annotations

from urllib.parse import urlparse

import docker
from docker.errors import APIError, ContainerError, DockerException, ImageNotFound, NotFound
from docker.models.containers import Container

from runtime_manager.core.exceptions import DockerRuntimeError, RuntimeEnvironmentError
from runtime_manager.core.specs import RuntimeContainerSpec
from runtime_manager.settings import RuntimeManagerSettings


class DockerRuntimeClient:
    def __init__(
        self,
        client: docker.DockerClient | None = None,
        settings: RuntimeManagerSettings | None = None,
    ) -> None:
        self._client = client or docker.from_env()
        self._settings = settings or RuntimeManagerSettings()

    def ping(self) -> bool:
        try:
            return bool(self._client.ping())
        except DockerException as exc:
            raise RuntimeEnvironmentError("docker daemon is unavailable") from exc

    def ensure_network_exists(self, network_name: str) -> None:
        try:
            self._client.networks.get(network_name)
        except NotFound as exc:
            raise RuntimeEnvironmentError(f"docker network not found: {network_name}") from exc
        except DockerException as exc:
            raise DockerRuntimeError(f"failed to inspect docker network: {network_name}") from exc

    def get_runtime_container(self, runtime_id: str, user_id: str | None = None) -> Container | None:
        filters = {"label": self._build_label_filters(runtime_id, user_id)}
        try:
            containers = self._client.containers.list(all=True, filters=filters)
        except DockerException as exc:
            raise DockerRuntimeError("failed to list runtime containers") from exc

        if not containers:
            return None

        containers.sort(key=lambda container: container.attrs["Created"])
        return containers[-1]

    def pull_image(self, image_ref: str) -> None:
        repository, tag = self._split_image_ref(image_ref)
        try:
            if tag is None:
                self._client.images.pull(repository)
            else:
                self._client.images.pull(repository, tag=tag)
        except DockerException as exc:
            raise DockerRuntimeError(f"failed to pull image: {image_ref}") from exc

    def run_init_permissions(self, config_dir: str, workspace_dir: str) -> None:
        self.pull_image(self._settings.init_permissions_image)
        command = [
            "sh",
            "-lc",
            (
                "mkdir -p /home/node/.openclaw /home/node/.openclaw/workspace "
                "/home/node/.openclaw/canvas /home/node/.openclaw/cron "
                "&& chown -R 1000:1000 /home/node/.openclaw "
                "&& chmod -R u+rwX,g+rwX /home/node/.openclaw"
            ),
        ]
        volumes = {
            config_dir: {"bind": "/home/node/.openclaw", "mode": "rw"},
            workspace_dir: {"bind": "/home/node/.openclaw/workspace", "mode": "rw"},
        }

        try:
            self._client.containers.run(
                self._settings.init_permissions_image,
                command=command,
                user="0:0",
                volumes=volumes,
                remove=True,
            )
        except DockerException as exc:
            raise DockerRuntimeError("failed to initialize runtime directory permissions") from exc

    def create_container(self, spec: RuntimeContainerSpec) -> Container:
        self.pull_image(spec.image_ref)
        try:
            return self._client.containers.create(
                image=spec.image_ref,
                name=spec.container_name,
                command=list(spec.command),
                environment=spec.environment,
                labels=spec.labels,
                volumes=spec.volumes,
                ports=spec.ports,
                network=spec.network_name,
                init=True,
                detach=True,
                restart_policy={"Name": "unless-stopped"},
            )
        except ImageNotFound as exc:
            raise DockerRuntimeError(f"image not found: {spec.image_ref}") from exc
        except APIError as exc:
            raise DockerRuntimeError(f"failed to create container: {spec.container_name}") from exc
        except DockerException as exc:
            raise DockerRuntimeError(f"failed to create container: {spec.container_name}") from exc

    def start_container(self, container: Container) -> None:
        try:
            container.start()
        except DockerException as exc:
            raise DockerRuntimeError(f"failed to start container: {container.name}") from exc

    def stop_container(self, container: Container, timeout: int) -> None:
        try:
            container.stop(timeout=timeout)
        except DockerException as exc:
            raise DockerRuntimeError(f"failed to stop container: {container.name}") from exc

    def remove_container(self, container: Container) -> None:
        try:
            container.remove(force=True)
        except DockerException as exc:
            raise DockerRuntimeError(f"failed to remove container: {container.name}") from exc

    def reload_container(self, container: Container) -> Container:
        try:
            container.reload()
            return container
        except DockerException as exc:
            raise DockerRuntimeError(f"failed to inspect container: {container.name}") from exc

    def probe_tcp_endpoint(self, network_name: str, target_url: str, timeout_seconds: float) -> bool:
        self.pull_image(self._settings.probe_image)
        timeout_value = max(int(timeout_seconds), 1)
        parsed = urlparse(target_url)
        host = parsed.hostname
        port = parsed.port
        if not host or not port:
            raise DockerRuntimeError(f"invalid runtime endpoint: {target_url}")
        command = [
            "sh",
            "-lc",
            f"nc -z -w {timeout_value} {host} {port}",
        ]

        try:
            self._client.containers.run(
                self._settings.probe_image,
                command=command,
                network=network_name,
                remove=True,
            )
            return True
        except ContainerError:
            return False
        except DockerException as exc:
            raise DockerRuntimeError(f"failed to probe runtime endpoint: {target_url}") from exc

    @staticmethod
    def _build_label_filters(runtime_id: str, user_id: str | None) -> list[str]:
        filters = [
            "crewclaw.managed=true",
            f"crewclaw.runtimeId={runtime_id}",
        ]
        if user_id is not None:
            filters.append(f"crewclaw.userId={user_id}")
        return filters

    @staticmethod
    def _split_image_ref(image_ref: str) -> tuple[str, str | None]:
        if "@" in image_ref:
            repository, digest = image_ref.rsplit("@", 1)
            return repository, digest

        image_name = image_ref.rsplit("/", 1)[-1]
        if ":" in image_name:
            repository, tag = image_ref.rsplit(":", 1)
            return repository, tag

        return image_ref, None

