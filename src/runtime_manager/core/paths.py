from __future__ import annotations

import json
import shutil
from pathlib import Path

from contracts import DeleteRequest, EnsureRunningRequest

from runtime_manager.core.exceptions import RuntimeValidationError
from runtime_manager.core.specs import RuntimePaths


class RuntimePathManager:
    def prepare(self, request: EnsureRunningRequest) -> RuntimePaths:
        config_dir = Path(request.compat.openclaw_config_dir)
        workspace_dir = Path(request.compat.openclaw_workspace_dir)
        config_file = Path(request.config_mount.config_file_path)
        secret_file = Path(request.config_mount.secret_file_path)

        config_dir.mkdir(parents=True, exist_ok=True)
        workspace_dir.mkdir(parents=True, exist_ok=True)
        (config_dir / "canvas").mkdir(parents=True, exist_ok=True)
        (config_dir / "cron").mkdir(parents=True, exist_ok=True)

        if not config_file.is_file():
            raise RuntimeValidationError(f"config file not found: {config_file}")
        if not secret_file.is_file():
            raise RuntimeValidationError(f"secret file not found: {secret_file}")

        return RuntimePaths(
            config_dir=config_dir,
            workspace_dir=workspace_dir,
            config_file=config_file,
            secret_file=secret_file,
        )

    def resolve_gateway_token(self, paths: RuntimePaths) -> str:
        secret_value = paths.secret_file.read_text(encoding="utf-8").strip()
        if secret_value:
            return secret_value

        config_data = json.loads(paths.config_file.read_text(encoding="utf-8"))
        gateway_token = (
            config_data.get("gateway", {})
            .get("auth", {})
            .get("token")
        )
        if isinstance(gateway_token, str) and gateway_token.strip():
            return gateway_token.strip()

        raise RuntimeValidationError("missing gateway token in secret file and openclaw.json")

    def wipe(self, request: DeleteRequest, labels: dict[str, str] | None) -> None:
        if labels is None:
            return

        config_dir = labels.get("crewclaw.configDir")
        workspace_dir = labels.get("crewclaw.workspaceDir")
        to_delete = []
        if config_dir:
            to_delete.append(Path(config_dir))
        if workspace_dir:
            workspace_path = Path(workspace_dir)
            if all(path != workspace_path for path in to_delete):
                to_delete.append(workspace_path)

        for path in to_delete:
            if path.exists():
                shutil.rmtree(path, ignore_errors=True)

