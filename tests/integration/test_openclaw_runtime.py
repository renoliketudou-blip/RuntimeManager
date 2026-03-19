import json
import time
from pathlib import Path

import docker
import pytest
from docker.errors import DockerException, NotFound

from contracts import DeleteRequest, EnsureRunningRequest, ObservedState, RetentionPolicy, StopRequest
from runtime_manager.core.service import RuntimeManagerService
from runtime_manager.settings import RuntimeManagerSettings


def require_docker() -> docker.DockerClient:
    try:
        client = docker.from_env()
        client.ping()
        return client
    except DockerException as exc:
        pytest.skip(f"Docker unavailable: {exc}")


def require_shared_network(client: docker.DockerClient) -> None:
    try:
        network = client.networks.get("crewclaw_shared")
    except NotFound:
        pytest.skip("Docker network crewclaw_shared is unavailable")

    containers = network.attrs.get("Containers") or {}
    if not containers:
        pytest.skip("Docker network crewclaw_shared has no attached containers")


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


@pytest.mark.integration
def test_runtime_manager_real_openclaw_lifecycle(tmp_path: Path) -> None:
    client = require_docker()
    require_shared_network(client)

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
    service = RuntimeManagerService(
        settings=RuntimeManagerSettings(
            readiness_timeout_seconds=60.0,
            readiness_poll_interval_seconds=3.0,
        )
    )

    request = EnsureRunningRequest.model_validate(
        {
            "userId": "u_integration",
            "runtimeId": runtime_id,
            "imageRef": "ghcr.io/openclaw/openclaw@sha256:a5a4c83b773aca85a8ba99cf155f09afa33946c0aa5cc6a9ccb6162738b5da02",
            "volumeId": "vol_integration",
            "routeHost": "u-integration.crewclaw.example.com",
            "configMount": {
                "configFilePath": str(config_path),
                "secretFilePath": str(secret_path),
            },
            "retentionPolicy": "preserve_workspace",
            "compat": {
                "openclawConfigDir": str(config_dir),
                "openclawWorkspaceDir": str(workspace_dir),
                "networkName": "crewclaw_shared",
                "gatewayPort": 28789,
                "bridgePort": 28790,
            },
        }
    )

    try:
        ensure_response = service.ensure_running(request)
        assert ensure_response.internal_endpoint

        final_state = ensure_response.observed_state
        if final_state != ObservedState.RUNNING:
            for _ in range(20):
                time.sleep(3)
                status_response = service.get_status(runtime_id)
                final_state = status_response.observed_state
                if final_state == ObservedState.RUNNING:
                    break

        assert final_state == ObservedState.RUNNING

        stop_response = service.stop(StopRequest(user_id="u_integration", runtime_id=runtime_id))
        assert stop_response.observed_state == ObservedState.STOPPED

        restart_response = service.ensure_running(request)
        assert restart_response.observed_state in {ObservedState.CREATING, ObservedState.RUNNING}
    finally:
        service.delete(
            DeleteRequest(
                user_id="u_integration",
                runtime_id=runtime_id,
                retention_policy=RetentionPolicy.PRESERVE_WORKSPACE,
            )
        )
