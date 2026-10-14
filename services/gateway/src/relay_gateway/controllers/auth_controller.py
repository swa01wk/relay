"""Browser and CLI sign-in: `relay login` (device-code flow), email confirmation, password reset."""

from __future__ import annotations

from urllib.parse import parse_qs

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field

from relay_gateway.core.container import account_email_service, device_login_service
from relay_gateway.core.errors import GatewayError
from relay_gateway.core.http import client_ip
from relay_gateway.views.account_pages import (
    email_confirmed,
    forgot_form,
    forgot_sent,
    link_problem,
    reset_done,
    reset_form,
)
from relay_gateway.views.device_login_page import login_done, login_form

router = APIRouter(prefix="/v1/auth", tags=["auth"])

_PAGE_HEADERS = {"Cache-Control": "no-store", "X-Frame-Options": "DENY", "Referrer-Policy": "no-referrer"}


class DeviceTokenRequest(BaseModel):
    device_code: str = Field(min_length=1, max_length=200)
    client_name: str = Field(default="", max_length=120, description="Labels this device in `relay sessions`")


def _html(body: str, status_code: int = 200, error: GatewayError | None = None) -> HTMLResponse:
    headers = dict(_PAGE_HEADERS)
    if error is not None and getattr(error, "retry_after", None):
        headers["Retry-After"] = str(error.retry_after)
    return HTMLResponse(body, status_code=status_code, headers=headers)


async def _form(request: Request) -> dict[str, str]:
    return {key: values[0] for key, values in parse_qs((await request.body()).decode()).items()}


# --- relay login ------------------------------------------------------------------------------


@router.post("/device")
async def start_device_login(request: Request) -> dict:
    return await device_login_service.start(base_url=str(request.base_url), ip=client_ip(request))


@router.post("/device/token")
async def poll_device_login(body: DeviceTokenRequest) -> dict:
    return await device_login_service.poll(body.device_code, client_name=body.client_name)


@router.get("/device/verify", response_class=HTMLResponse, include_in_schema=False)
async def verify_page(code: str = "") -> HTMLResponse:
    return _html(login_form(code=code))


@router.post("/device/verify", response_class=HTMLResponse, include_in_schema=False)
async def verify_submit(request: Request) -> HTMLResponse:
    form = await _form(request)
    code, email, create = form.get("code", ""), form.get("email", ""), form.get("create") == "1"
    try:
        outcome, signed_in_as = await device_login_service.approve(
            user_code=code, email=email, password=form.get("password", ""), create_account=create,
            ip=client_ip(request), base_url=str(request.base_url),
        )  # fmt: skip
    except GatewayError as error:
        return _html(login_form(code=code, email=email, create=create, error=error.detail), error.status_code, error)
    if outcome == "verify":
        info = f"Almost done: we sent a confirmation link to {signed_in_as}. Open it, then sign in here."
        return _html(login_form(code=code, email=signed_in_as, info=info))
    return _html(login_done(signed_in_as))


# --- email confirmation and password reset ----------------------------------------------------


@router.get("/verify-email", response_class=HTMLResponse, include_in_schema=False)
async def confirm_email(token: str = "") -> HTMLResponse:
    try:
        return _html(email_confirmed(await account_email_service.verify_email(token)))
    except GatewayError as error:
        return _html(link_problem(error.detail), error.status_code)


@router.get("/forgot-password", response_class=HTMLResponse, include_in_schema=False)
async def forgot_page() -> HTMLResponse:
    return _html(forgot_form())


@router.post("/forgot-password", response_class=HTMLResponse, include_in_schema=False)
async def forgot_submit(request: Request) -> HTMLResponse:
    email = (await _form(request)).get("email", "")
    try:
        await account_email_service.request_password_reset(
            email, base_url=str(request.base_url), ip=client_ip(request)
        )
    except GatewayError as error:
        return _html(forgot_form(email=email, error=error.detail), error.status_code, error)
    return _html(forgot_sent(email))


@router.get("/reset-password", response_class=HTMLResponse, include_in_schema=False)
async def reset_page(token: str = "") -> HTMLResponse:
    return _html(reset_form(token=token))


@router.post("/reset-password", response_class=HTMLResponse, include_in_schema=False)
async def reset_submit(request: Request) -> HTMLResponse:
    form = await _form(request)
    token = form.get("token", "")
    try:
        email = await account_email_service.reset_password(token, form.get("password", ""), ip=client_ip(request))
    except GatewayError as error:
        return _html(reset_form(token=token, error=error.detail), error.status_code, error)
    return _html(reset_done(email))
