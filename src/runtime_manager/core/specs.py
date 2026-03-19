from dataclasses import dataclass
from pathlib import Path
import re

from contracts import EnsureRunningRequest
from runtime_manager.constants import (
    CONTAINER_BRIDGE_PORT,
    CONTAINER_GATEWAY_PORT,
    OPENCLAW_CONFIG_PATH,
    OPENCLAW_HOME_DIR,
    OPENCLAW_SECRET_PATH,
    OPENCLAW_WORKSPACE_DIR,
    START_COMMAND,
)

MANAGED_LABEL_VALUE = "true"
NAME_SANITIZE_PATTERN = re.compile(r"[^a-zA-Z0-9-]+")


@dataclass(frozen=True)
class RuntimePaths:
    config_dir: Path
    workspace_dir: Path
    config_file: Path
    secret_file: Path


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


def sanitize_name(value: str) -> str:
    normalized = NAME_SANITIZE_PATTERN.sub("-", value.strip().lower()).strip("-")
    return normalized or "runtime"


class RuntimeLabels:
    @staticmethod
    def build(request: EnsureRunningRequest, paths: RuntimePaths) -> dict[str, str]:
        return {
            "crewclaw.managed": MANAGED_LABEL_VALUE,
            "crewclaw.userId": request.user_id,
            "crewclaw.runtimeId": request.runtime_id,
            "crewclaw.volumeId": request.volume_id,
            "crewclaw.routeHost": request.route_host,
            "crewclaw.retentionPolicy": request.retention_policy.value,
            "crewclaw.configDir": str(paths.config_dir),
            "crewclaw.workspaceDir": str(paths.workspace_dir),
        }

    @staticmethod
    def filters(runtime_id: str, user_id: str | None = None) -> dict[str, str]:
        filters = {
            "crewclaw.managed": MANAGED_LABEL_VALUE,
            "crewclaw.runtimeId": runtime_id,
        }
        if user_id is not None:
            filters["crewclaw.userId"] = user_id
        return filters


class RuntimeSpecFactory:
    @staticmethod
    def build(request: EnsureRunningRequest, paths: RuntimePaths, gateway_token: str) -> RuntimeContainerSpec:
        container_name = (
            f"crewclaw-rt-{sanitize_name(request.user_id)}-{sanitize_name(request.runtime_id)}"
        )
        internal_endpoint = f"http://{container_name}:{CONTAINER_GATEWAY_PORT}"

        environment = {
            "HOME": "/home/node",
            "TERM": "xterm-256color",
            "TZ": "UTC",
            "OPENAI_BASE_URL": "http://litellm:4000",
            "OPENCLAW_GATEWAY_TOKEN": gateway_token,
        }

        volumes = {
            str(paths.config_dir): {"bind": OPENCLAW_HOME_DIR, "mode": "rw"},
            str(paths.workspace_dir): {"bind": OPENCLAW_WORKSPACE_DIR, "mode": "rw"},
            str(paths.config_file): {"bind": OPENCLAW_CONFIG_PATH, "mode": "ro"},
            str(paths.secret_file): {"bind": OPENCLAW_SECRET_PATH, "mode": "ro"},
        }

        ports = {
            f"{CONTAINER_GATEWAY_PORT}/tcp": request.compat.gateway_port,
            f"{CONTAINER_BRIDGE_PORT}/tcp": request.compat.bridge_port,
        }

        return RuntimeContainerSpec(
            container_name=container_name,
            image_ref=request.image_ref,
            command=START_COMMAND,
            environment=environment,
            labels=RuntimeLabels.build(request, paths),
            volumes=volumes,
            ports=ports,
            network_name=request.compat.network_name,
            internal_endpoint=internal_endpoint,
        )

