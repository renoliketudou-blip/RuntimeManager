from dataclasses import dataclass
from pathlib import Path

from contracts import EnsureRunningRequest
from runtime_manager.constants import (
    DEFAULT_IMAGE_REF,
    DEFAULT_NETWORK_NAME,
    CONTAINER_BRIDGE_PORT,
    CONTAINER_GATEWAY_PORT,
    OPENCLAW_CONFIG_PATH,
    OPENCLAW_HOME_DIR,
    OPENCLAW_SECRET_PATH,
    OPENCLAW_WORKSPACE_DIR,
    START_COMMAND,
)

MANAGED_LABEL_VALUE = "true"


@dataclass(frozen=True)
class RuntimePaths:
    config_dir: Path
    workspace_dir: Path
    config_file: Path | None
    secret_file: Path | None


@dataclass(frozen=True)
class RuntimeContainerSpec:
    container_name: str
    image_ref: str
    command: tuple[str, ...]
    environment: dict[str, str]
    labels: dict[str, str]
    volumes: dict[str, dict[str, str]]
    ports: dict[str, int]
    network_name: str
    internal_endpoint: str


class RuntimeLabels:
    @staticmethod
    def build(request: EnsureRunningRequest, paths: RuntimePaths) -> dict[str, str]:
        return {
            "clawloops.managed": MANAGED_LABEL_VALUE,
            "clawloops.userId": request.user_id,
            "clawloops.runtimeId": request.runtime_id,
            "clawloops.volumeId": request.volume_id,
            "clawloops.routeHost": request.route_host,
            "clawloops.retentionPolicy": request.retention_policy.value,
            "clawloops.configDir": str(paths.config_dir),
            "clawloops.workspaceDir": str(paths.workspace_dir),
        }

    @staticmethod
    def filters(runtime_id: str, user_id: str | None = None) -> dict[str, str]:
        filters = {
            "clawloops.managed": MANAGED_LABEL_VALUE,
            "clawloops.runtimeId": runtime_id,
        }
        if user_id is not None:
            filters["clawloops.userId"] = user_id
        return filters


class RuntimeSpecFactory:
    @staticmethod
    def build(request: EnsureRunningRequest, paths: RuntimePaths) -> RuntimeContainerSpec:
        container_name = f"rt-{request.runtime_id}"
        internal_endpoint = f"http://rt-{request.runtime_id}:{CONTAINER_GATEWAY_PORT}"

        environment = {
            "HOME": "/home/node",
            "TERM": "xterm-256color",
            "TZ": "UTC",
            "OPENAI_BASE_URL": "http://litellm:4000",
        }
        if request.env:
            environment.update(request.env)
        if request.env_overrides:
            environment.update(request.env_overrides)
        environment["OPENAI_BASE_URL"] = "http://litellm:4000"

        volumes = {
            str(paths.config_dir): {"bind": OPENCLAW_HOME_DIR, "mode": "rw"},
            str(paths.workspace_dir): {"bind": OPENCLAW_WORKSPACE_DIR, "mode": "rw"},
        }
        if paths.config_file:
            volumes[str(paths.config_file)] = {"bind": OPENCLAW_CONFIG_PATH, "mode": "ro"}
        if paths.secret_file:
            volumes[str(paths.secret_file)] = {"bind": OPENCLAW_SECRET_PATH, "mode": "ro"}

        ports = {
            f"{CONTAINER_GATEWAY_PORT}/tcp": CONTAINER_GATEWAY_PORT,
            f"{CONTAINER_BRIDGE_PORT}/tcp": CONTAINER_BRIDGE_PORT,
        }

        return RuntimeContainerSpec(
            container_name=container_name,
            image_ref=DEFAULT_IMAGE_REF,
            command=START_COMMAND,
            environment=environment,
            labels=RuntimeLabels.build(request, paths),
            volumes=volumes,
            ports=ports,
            network_name=DEFAULT_NETWORK_NAME,
            internal_endpoint=internal_endpoint,
        )

