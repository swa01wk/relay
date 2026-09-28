"""FastAPI application factory."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from relay_gateway.deps import shutdown, startup
from relay_gateway.routes import health, sessions, webrtc, ws


def create_app() -> FastAPI:
    app = FastAPI(title="Relay Gateway", version="0.1.0")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(health.router)
    app.include_router(sessions.router)
    app.include_router(webrtc.router)
    app.include_router(ws.router)

    @app.on_event("startup")
    async def _startup() -> None:
        await startup()

    @app.on_event("shutdown")
    async def _shutdown() -> None:
        await shutdown()

    return app
