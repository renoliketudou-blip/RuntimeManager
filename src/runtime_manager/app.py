from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from contracts import ErrorResponse
from runtime_manager.api.routes import router
from runtime_manager.core.exceptions import RuntimeManagerError


def create_app() -> FastAPI:
    app = FastAPI(title="RuntimeManager", version="0.1.0")
    app.include_router(router)

    @app.exception_handler(RuntimeManagerError)
    def handle_runtime_manager_error(
        _: Request,
        exc: RuntimeManagerError,
    ) -> JSONResponse:
        payload = ErrorResponse(code=exc.code, message=exc.message)
        return JSONResponse(
            status_code=exc.status_code,
            content=payload.model_dump(by_alias=True),
        )

    return app


app = create_app()

