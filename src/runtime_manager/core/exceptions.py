class RuntimeManagerError(Exception):
    code = "RUNTIME_MANAGER_ERROR"
    status_code = 500

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class RuntimeNotFoundError(RuntimeManagerError):
    code = "RUNTIME_NOT_FOUND"
    status_code = 404


class RuntimeValidationError(RuntimeManagerError):
    code = "RUNTIME_MANAGER_VALIDATION_ERROR"
    status_code = 400


class DockerRuntimeError(RuntimeManagerError):
    code = "RUNTIME_MANAGER_ERROR"
    status_code = 500


class RuntimeEnvironmentError(RuntimeManagerError):
    code = "RUNTIME_MANAGER_ENVIRONMENT_ERROR"
    status_code = 503

