from __future__ import annotations

import shutil
from pathlib import Path

from contracts import DeleteRequest, EnsureRunningRequest

from runtime_manager.core.exceptions import RuntimeValidationError
from runtime_manager.core.specs import RuntimePaths


class RuntimePathManager:
    def prepare(self, request: EnsureRunningRequest) -> RuntimePaths:
        config_dir = Path(request.compat.openclaw_config_dir)
        workspace_dir = Path(request.compat.openclaw_workspace_dir)
        config_file: Path | None = None
        secret_file: Path | None = None
        if request.config_mount is not None:
            config_file = Path(request.config_mount.config_file_path)
            secret_file = Path(request.config_mount.secret_file_path)

        config_dir.mkdir(parents=True, exist_ok=True)
        workspace_dir.mkdir(parents=True, exist_ok=True)
        (config_dir / "canvas").mkdir(parents=True, exist_ok=True)
        (config_dir / "cron").mkdir(parents=True, exist_ok=True)

        if config_file is not None and not config_file.is_file():
            raise RuntimeValidationError(f"config file not found: {config_file}")
        if secret_file is not None and not secret_file.is_file():
            raise RuntimeValidationError(f"secret file not found: {secret_file}")

        return RuntimePaths(
            config_dir=config_dir,
            workspace_dir=workspace_dir,
            config_file=config_file,
            secret_file=secret_file,
        )

    def wipe(self, request: DeleteRequest, labels: dict[str, str] | None) -> None:
        if labels is None:
            return

        config_dir = labels.get("clawloops.configDir")
        workspace_dir = labels.get("clawloops.workspaceDir")
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

