import pytest
from pydantic import ValidationError

from contracts import EnsureRunningRequest, ObservedState, RetentionPolicy, RuntimeStatusResponse


def test_ensure_running_request_schema_v2() -> None:
    req = EnsureRunningRequest(
        user_id="u_001",
        runtime_id="rt_001",
        volume_id="vol_001",
        route_host="u-001.clawloops.example.com",
        retention_policy=RetentionPolicy.PRESERVE_WORKSPACE,
        compat={
            "openclaw_config_dir": "/var/lib/clawloops/users/u_001/config",
            "openclaw_workspace_dir": "/var/lib/clawloops/users/u_001/workspace",
        },
        env={"OPENCLAW_GATEWAY_TOKEN": "token"},
    )
    assert req.runtime_id == "rt_001"


def test_ensure_running_request_rejects_removed_fields() -> None:
    with pytest.raises(ValidationError):
        EnsureRunningRequest.model_validate(
            {
                "userId": "u_001",
                "runtimeId": "rt_001",
                "imageRef": "ghcr.io/openclaw/openclaw@sha256:123",
                "volumeId": "vol_001",
                "routeHost": "u-001.clawloops.example.com",
                "retentionPolicy": "preserve_workspace",
                "compat": {
                    "openclawConfigDir": "/var/lib/clawloops/users/u_001/config",
                    "openclawWorkspaceDir": "/var/lib/clawloops/users/u_001/workspace",
                },
            }
        )


def test_ensure_running_request_accepts_camel_case_payload() -> None:
    req = EnsureRunningRequest.model_validate(
        {
            "userId": "u_001",
            "runtimeId": "rt_001",
            "volumeId": "vol_001",
            "routeHost": "u-001.clawloops.example.com",
            "configMount": {
                "configFilePath": "/var/lib/clawloops/runtime-configs/u_001/openclaw.json",
                "secretFilePath": "/var/lib/clawloops/runtime-secrets/u_001/gateway.token",
            },
            "retentionPolicy": "preserve_workspace",
            "compat": {
                "openclawConfigDir": "/var/lib/clawloops/users/u_001/config",
                "openclawWorkspaceDir": "/var/lib/clawloops/users/u_001/workspace",
            },
            "envOverrides": {"OPENCLAW_ALLOW_INSECURE_PRIVATE_WS": "true"},
        }
    )

    payload = req.model_dump(by_alias=True)
    assert payload["userId"] == "u_001"
    assert payload["configMount"]["configFilePath"].endswith("openclaw.json")
    assert payload["compat"]["openclawConfigDir"].endswith("/config")


def test_runtime_status_response_allows_null_endpoint_for_deleted() -> None:
    payload = RuntimeStatusResponse(
        runtime_id="rt_001",
        observed_state=ObservedState.DELETED,
        internal_endpoint=None,
        message="not found as container fact",
    ).model_dump(by_alias=True)
    assert payload["internalEndpoint"] is None

