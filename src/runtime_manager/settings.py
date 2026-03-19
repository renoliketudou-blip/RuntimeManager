from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from runtime_manager.constants import INIT_PERMISSIONS_IMAGE, PROBE_IMAGE


class RuntimeManagerSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="RUNTIME_MANAGER_", case_sensitive=False)

    readiness_timeout_seconds: float = Field(default=20.0, gt=0)
    readiness_poll_interval_seconds: float = Field(default=2.0, gt=0)
    stop_timeout_seconds: int = Field(default=10, ge=1)
    init_permissions_image: str = Field(default=INIT_PERMISSIONS_IMAGE, min_length=1)
    probe_image: str = Field(default=PROBE_IMAGE, min_length=1)

