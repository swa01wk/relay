"""FastAPI for CRM tools (POST /tools/{name}) and the frontend dashboard (GET /dashboard)."""

from __future__ import annotations

import os
from typing import Any

from fastapi import Body, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from crm_tools_api import logic
from crm_tools_api.tools import TOOL_SPECS, call_tool, tool_manifest

app = FastAPI(title="Sales CRM tools API", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=os.environ.get("CRM_CORS_ORIGINS", "http://localhost:3002").split(","),
    allow_methods=["GET"],
    allow_headers=["*"],
)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/tools")
async def list_tools() -> dict[str, Any]:
    """Tool discovery for Relay agent manifests."""
    return {"tools": tool_manifest()}


@app.get("/dashboard")
async def dashboard() -> dict[str, Any]:
    return logic.get_dashboard()


@app.post("/tools/{name}")
async def run_tool(name: str, arguments: dict[str, Any] = Body(default_factory=dict)) -> dict[str, Any]:
    if name not in TOOL_SPECS:
        raise HTTPException(status_code=404, detail=f"unknown tool {name}")
    try:
        result = call_tool(name, arguments)
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if str(result.get("error", "")).startswith("missing_arguments"):
        raise HTTPException(status_code=400, detail=result["error"])
    return result


def run() -> None:
    import uvicorn

    uvicorn.run(
        "crm_tools_api.main:app",
        host="0.0.0.0",
        port=int(os.environ.get("CRM_TOOLS_PORT", "8091")),
    )
