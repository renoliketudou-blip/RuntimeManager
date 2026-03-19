from functools import lru_cache

from runtime_manager.core.docker_client import DockerRuntimeClient
from runtime_manager.core.health import RuntimeHealthChecker
from runtime_manager.core.paths import RuntimePathManager
from runtime_manager.core.service import RuntimeManagerService
from runtime_manager.settings import RuntimeManagerSettings


@lru_cache
def get_settings() -> RuntimeManagerSettings:
    return RuntimeManagerSettings()


@lru_cache
def get_docker_runtime_client() -> DockerRuntimeClient:
    settings = get_settings()
    return DockerRuntimeClient(settings=settings)


@lru_cache
def get_runtime_manager_service() -> RuntimeManagerService:
    settings = get_settings()
    docker_client = get_docker_runtime_client()
    return RuntimeManagerService(
        docker_client=docker_client,
        path_manager=RuntimePathManager(),
        health_checker=RuntimeHealthChecker(docker_client=docker_client, settings=settings),
        settings=settings,
    )

