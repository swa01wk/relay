"""FastAPI application factory."""

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from relay_gateway.controllers import (
    account_controller,
    activity_controller,
    admin_controller,
    agent_controller,
    auth_controller,
    health_controller,
    metrics_controller,
    realtime_controller,
    session_controller,
    stream_controller,
)
from relay_gateway.core.container import shutdown, startup
from relay_gateway.core.errors import GatewayError, ReauthRequired, TooManyRequests


def create_app() -> FastAPI:
    app = FastAPI(title="Relay Gateway", version="0.1.0")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    for controller in (
        health_controller,
        metrics_controller,
        admin_controller,
        auth_controller,
        account_controller,
        agent_controller,
        activity_controller,
        session_controller,
        realtime_controller,
        stream_controller,
    ):
        app.include_router(controller.router)

    @app.exception_handler(GatewayError)
    async def _gateway_error(_request: Request, error: GatewayError) -> JSONResponse:
        # Services raise GatewayError; this is the one place it becomes an HTTP response.
        headers: dict[str, str] = {}
        if isinstance(error, TooManyRequests):
            headers["Retry-After"] = str(error.retry_after)
        if isinstance(error, ReauthRequired):
            headers["X-Relay-Reauth"] = "required"
        return JSONResponse(status_code=error.status_code, content={"detail": error.detail}, headers=headers)

    @app.on_event("startup")
    async def _startup() -> None:
        await startup()

    @app.on_event("shutdown")
    async def _shutdown() -> None:
        await shutdown()

    return app
