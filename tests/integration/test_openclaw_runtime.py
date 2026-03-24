import json
import socket
import time
from pathlib import Path

import docker
import httpx
import pytest
from docker.errors import DockerException, ImageNotFound, NotFound

from contracts import DeleteRequest, EnsureRunningRequest, ObservedState, RetentionPolicy, StopRequest
from runtime_manager.core.service import RuntimeManagerService
from runtime_manager.settings import RuntimeManagerSettings

OPENCLAW_IMAGE_REF = (
    "ghcr.io/openclaw/openclaw@sha256:a5a4c83b773aca85a8ba99cf155f09afa33946c0aa5cc6a9ccb6162738b5da02"
)


def require_docker() -> docker.DockerClient:
    try:
        client = docker.from_env()
        client.ping()
        return client
    except DockerException as exc:
        pytest.skip(f"Docker unavailable: {exc}")


def require_shared_network(client: docker.DockerClient) -> None:
    try:
        network = client.networks.get("clawloops_shared")
    except NotFound:
        pytest.skip("Docker network clawloops_shared is unavailable")

    containers = network.attrs.get("Containers") or {}
    if not containers:
        pytest.skip("Docker network clawloops_shared has no attached containers")


def reserve_host_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def require_openclaw_image(client: docker.DockerClient, image_ref: str) -> None:
    try:
        client.images.get(image_ref)
        return
    except ImageNotFound:
        pass
    except DockerException as exc:
        pytest.skip(f"Unable to inspect image {image_ref}: {exc}")

    try:
        repository, digest = image_ref.rsplit("@", 1)
        client.images.pull(repository=repository, tag=digest)
    except DockerException as exc:
        pytest.skip(f"Unable to pull image {image_ref}: {exc}")


def write_openclaw_config(config_path: Path, token: str) -> None:
    config = {
        "gateway": {
            "mode": "local",
            "port": 18789,
            "bind": "lan",
            "auth": {
                "mode": "token",
                "token": token,
            },
        },
        "agents": {
            "defaults": {
                "workspace": "~/.openclaw/workspace",
                "model": {
                    "primary": "litellm/gpt-4o",
                },
            },
        },
        "models": {
            "providers": {
                "litellm": {
                    "baseUrl": "http://litellm:4000",
                    "apiKey": "placeholder",
                    "api": "openai-completions",
                    "models": [
                        {
                            "id": "gpt-4o",
                            "name": "GPT-4o",
                            "reasoning": False,
                            "input": ["text", "image"],
                            "contextWindow": 128000,
                            "maxTokens": 8192,
                        }
                    ],
                }
            }
        },
    }
    config_path.write_text(json.dumps(config), encoding="utf-8")


def wait_runtime_running(service: RuntimeManagerService, runtime_id: str, timeout_seconds: float = 90.0) -> None:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        status = service.get_status(runtime_id)
        if status.observed_state == ObservedState.RUNNING:
            return
        time.sleep(2)
    pytest.fail(f"runtime {runtime_id} did not reach running state in {timeout_seconds}s")


def wait_gateway_http_ready(base_url: str, token: str, timeout_seconds: float = 90.0) -> httpx.Response:
    headers = {
        "Authorization": f"Bearer {token}",
        "X-OpenClaw-Gateway-Token": token,
    }
    deadline = time.monotonic() + timeout_seconds
    last_exception: Exception | None = None
    with httpx.Client(timeout=3.0, follow_redirects=True) as client:
        while time.monotonic() < deadline:
            try:
                response = client.get(f"{base_url}/", headers=headers)
                if response.status_code in {200, 401, 403}:
                    return response
            except httpx.HTTPError as exc:
                last_exception = exc
            time.sleep(2)

    if last_exception is not None:
        pytest.fail(f"openclaw gateway is not reachable at {base_url}: {last_exception}")
    pytest.fail(f"openclaw gateway is not ready at {base_url}")


def get_runtime_container(client: docker.DockerClient, runtime_id: str) -> docker.models.containers.Container:
    containers = client.containers.list(
        all=True,
        filters={"label": [f"clawloops.runtimeId={runtime_id}", "clawloops.managed=true"]},
    )
    assert containers, f"runtime container not found for runtimeId={runtime_id}"
    return containers[-1]


@pytest.mark.integration
def test_runtime_manager_real_openclaw_lifecycle(tmp_path: Path) -> None:
    client = require_docker()
    require_shared_network(client)
    require_openclaw_image(client, OPENCLAW_IMAGE_REF)

    config_dir = tmp_path / "config"
    workspace_dir = tmp_path / "workspace"
    config_dir.mkdir(parents=True, exist_ok=True)
    workspace_dir.mkdir(parents=True, exist_ok=True)

    token = "gateway-token"
    config_path = tmp_path / "openclaw.json"
    secret_path = tmp_path / "gateway.token"
    write_openclaw_config(config_path, token)
    secret_path.write_text(token, encoding="utf-8")

    runtime_id = f"rt-{int(time.time())}"
    gateway_port = 18789
    service = RuntimeManagerService(
        settings=RuntimeManagerSettings(
            readiness_timeout_seconds=90.0,
            readiness_poll_interval_seconds=2.0,
        )
    )

    request = EnsureRunningRequest.model_validate(
        {
            "userId": "u_integration",
            "runtimeId": runtime_id,
            "volumeId": "vol_integration",
            "routeHost": "u-integration.clawloops.example.com",
            "configMount": {
                "configFilePath": str(config_path),
                "secretFilePath": str(secret_path),
            },
            "retentionPolicy": "preserve_workspace",
            "compat": {
                "openclawConfigDir": str(config_dir),
                "openclawWorkspaceDir": str(workspace_dir),
            },
            "env": {"OPENCLAW_GATEWAY_TOKEN": token},
        }
    )

    try:
        ensure_response = service.ensure_running(request)
        assert ensure_response.internal_endpoint

        if ensure_response.observed_state != ObservedState.RUNNING:
            wait_runtime_running(service, runtime_id)

        container = get_runtime_container(client, runtime_id)
        assert container.status in {"running", "created", "restarting"}
        assert container.labels["clawloops.runtimeId"] == runtime_id
        assert container.labels["clawloops.userId"] == "u_integration"

        command = container.attrs["Config"]["Cmd"]
        assert command == ["node", "dist/index.js", "gateway", "--bind", "lan", "--port", "18789"]

        env = container.attrs["Config"]["Env"]
        assert any(item == "HOME=/home/node" for item in env)
        assert any(item == "TERM=xterm-256color" for item in env)
        assert any(item == "TZ=UTC" for item in env)
        assert any(item == "OPENAI_BASE_URL=http://litellm:4000" for item in env)

        # 目录初始化契约：在容器内校验 OpenClaw 基础目录结构。
        dir_check = container.exec_run(
            [
                "sh",
                "-lc",
                (
                    "test -d /home/node/.openclaw "
                    "&& test -d /home/node/.openclaw/workspace "
                    "&& test -d /home/node/.openclaw/canvas "
                    "&& test -d /home/node/.openclaw/cron"
                ),
            ]
        )
        assert dir_check.exit_code == 0

        gateway_response = wait_gateway_http_ready(
            base_url=f"http://127.0.0.1:{gateway_port}",
            token=token,
        )
        assert gateway_response.status_code in {200, 401, 403}
        assert gateway_response.text != ""

        stop_response = service.stop(StopRequest(user_id="u_integration", runtime_id=runtime_id))
        assert stop_response.observed_state == ObservedState.STOPPED
    finally:
        service.delete(
            DeleteRequest(
                user_id="u_integration",
                runtime_id=runtime_id,
                retention_policy=RetentionPolicy.PRESERVE_WORKSPACE,
            )
        )
