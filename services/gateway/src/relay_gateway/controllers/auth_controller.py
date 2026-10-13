"""`relay login` (device-code flow): start, the browser approval page, and the CLI's poll."""

from __future__ import annotations

from urllib.parse import parse_qs

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field

from relay_gateway.core.container import device_login_service
from relay_gateway.core.errors import GatewayError
from relay_gateway.views.device_login_page import login_done, login_form

router = APIRouter(prefix="/v1/auth/device", tags=["auth"])

_PAGE_HEADERS = {"Cache-Control": "no-store", "X-Frame-Options": "DENY", "Referrer-Policy": "no-referrer"}


class DeviceTokenRequest(BaseModel):
    device_code: str = Field(min_length=1)


@router.post("")
async def start_device_login(request: Request) -> dict:
    return await device_login_service.start(base_url=str(request.base_url))


@router.post("/token")
async def poll_device_login(body: DeviceTokenRequest) -> dict:
    return await device_login_service.poll(body.device_code)


@router.get("/verify", response_class=HTMLResponse, include_in_schema=False)
async def verify_page(code: str = "") -> HTMLResponse:
    return HTMLResponse(login_form(code=code), headers=_PAGE_HEADERS)


@router.post("/verify", response_class=HTMLResponse, include_in_schema=False)
async def verify_submit(request: Request) -> HTMLResponse:
    form = {key: values[0] for key, values in parse_qs((await request.body()).decode()).items()}
    code, email, create = form.get("code", ""), form.get("email", ""), form.get("create") == "1"
    try:
        signed_in_as = await device_login_service.approve(
            user_code=code, email=email, password=form.get("password", ""), create_account=create
        )
    except GatewayError as error:
        page = login_form(code=code, email=email, create=create, error=error.detail)
        return HTMLResponse(page, status_code=error.status_code, headers=_PAGE_HEADERS)
    return HTMLResponse(login_done(signed_in_as), headers=_PAGE_HEADERS)
