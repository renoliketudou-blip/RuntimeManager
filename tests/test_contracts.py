import pytest
from pydantic import ValidationError

from contracts import CompatConfig, EnsureRunningRequest, RetentionPolicy


def test_compat_config_rejects_invalid_port() -> None:
    with pytest.raises(ValidationError):
        CompatConfig(
            openclaw_config_dir="/var/lib/crewclaw/users/u_001/config",
            openclaw_workspace_dir="/var/lib/crewclaw/users/u_001/workspace",
            network_name="crewclaw_shared",
            gateway_port=0,
            bridge_port=18790,
        )


def test_ensure_running_request_schema() -> None:
    req = EnsureRunningRequest(
        user_id="u_001",
        runtime_id="rt_001",
        image_ref="ghcr.io/openclaw/openclaw@sha256:123",
        volume_id="vol_001",
        route_host="u-001.crewclaw.example.com",
        config_mount={
            "config_file_path": "/var/lib/crewclaw/runtime-configs/u_001/openclaw.json",
            "secret_file_path": "/var/lib/crewclaw/runtime-secrets/u_001/gateway.token",
        },
        retention_policy=RetentionPolicy.PRESERVE_WORKSPACE,
        compat={
            "openclaw_config_dir": "/var/lib/crewclaw/users/u_001/config",
            "openclaw_workspace_dir": "/var/lib/crewclaw/users/u_001/workspace",
            "network_name": "crewclaw_shared",
            "gateway_port": 18789,
            "bridge_port": 18790,
        },
    )
    assert req.runtime_id == "rt_001"

