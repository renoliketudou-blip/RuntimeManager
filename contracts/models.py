from pydantic import BaseModel, ConfigDict, Field, HttpUrl, field_validator

from contracts.enums import ObservedState, RetentionPolicy

DEFAULT_GATEWAY_PORT = 18789
DEFAULT_BRIDGE_PORT = 18790


def to_camel(value: str) -> str:
    parts = value.split("_")
    return parts[0] + "".join(part.capitalize() for part in parts[1:])


class ContractModel(BaseModel):
    model_config = ConfigDict(populate_by_name=True, alias_generator=to_camel)


class ConfigMount(ContractModel):
    config_file_path: str = Field(..., min_length=1)
    secret_file_path: str = Field(..., min_length=1)


class CompatConfig(ContractModel):
    openclaw_config_dir: str = Field(..., min_length=1)
    openclaw_workspace_dir: str = Field(..., min_length=1)
    network_name: str = Field(..., min_length=1)
    gateway_port: int = Field(default=DEFAULT_GATEWAY_PORT)
    bridge_port: int = Field(default=DEFAULT_BRIDGE_PORT)

    @field_validator("gateway_port", "bridge_port")
    @classmethod
    def validate_port(cls, value: int) -> int:
        if value < 1 or value > 65535:
            raise ValueError("port must be in range 1-65535")
        return value


class EnsureRunningRequest(ContractModel):
    user_id: str = Field(..., min_length=1)
    runtime_id: str = Field(..., min_length=1)
    image_ref: str = Field(..., min_length=1)
    volume_id: str = Field(..., min_length=1)
    route_host: str = Field(..., min_length=1)
    config_mount: ConfigMount
    retention_policy: RetentionPolicy
    compat: CompatConfig


class EnsureRunningResponse(ContractModel):
    runtime_id: str = Field(..., min_length=1)
    observed_state: ObservedState
    internal_endpoint: HttpUrl
    message: str = Field(..., min_length=1)


class StopRequest(ContractModel):
    user_id: str = Field(..., min_length=1)
    runtime_id: str = Field(..., min_length=1)


class StopResponse(ContractModel):
    runtime_id: str = Field(..., min_length=1)
    observed_state: ObservedState = Field(default=ObservedState.STOPPED)
    message: str = Field(..., min_length=1)


class DeleteRequest(ContractModel):
    user_id: str = Field(..., min_length=1)
    runtime_id: str = Field(..., min_length=1)
    retention_policy: RetentionPolicy


class DeleteResponse(ContractModel):
    runtime_id: str = Field(..., min_length=1)
    observed_state: ObservedState = Field(default=ObservedState.DELETED)
    message: str = Field(..., min_length=1)


class RuntimeStatusResponse(ContractModel):
    runtime_id: str = Field(..., min_length=1)
    observed_state: ObservedState
    internal_endpoint: HttpUrl | None = None
    message: str = Field(..., min_length=1)


class ErrorResponse(ContractModel):
    code: str = Field(..., min_length=1)
    message: str = Field(..., min_length=1)
