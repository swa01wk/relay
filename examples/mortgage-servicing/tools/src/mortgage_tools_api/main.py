"""FastAPI read tools for mortgage POC (external to Relay runtime)."""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from mortgage_tools_api import logic

app = FastAPI(title="Mortgage tools API", version="0.1.0")


class SearchCustomerRequest(BaseModel):
    query: str = Field(min_length=1)


class GetMortgageRequest(BaseModel):
    mortgage_id: str = Field(min_length=1)


class GetPaymentsRequest(BaseModel):
    mortgage_id: str = Field(min_length=1)
    months: int = Field(default=3, ge=1, le=24)


class GetRateHistoryRequest(BaseModel):
    mortgage_id: str = Field(min_length=1)


class GetAuditHistoryRequest(BaseModel):
    mortgage_id: str = Field(min_length=1)
    limit: int = Field(default=10, ge=1, le=100)


class CalculateAdjustmentRequest(BaseModel):
    mortgage_id: str = Field(min_length=1)
    new_rate: float = Field(ge=0, le=30)


class PrepareCorrectionRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    mortgage_id: str = Field(min_length=1)
    proposed_rate: float | None = Field(default=None, ge=0, le=30)
    effective_date: str | None = Field(default=None, min_length=1)
    slow_ms: int = Field(default=0, ge=0, le=30_000, alias="_slow_ms")


class RecalculateCorrectionDraftRequest(BaseModel):
    mortgage_id: str = Field(min_length=1)
    effective_date: str = Field(min_length=1)
    proposed_rate: float | None = Field(default=None, ge=0, le=30)


class CommitCorrectionRequest(BaseModel):
    mortgage_id: str = Field(min_length=1)
    effective_date: str = Field(min_length=1)
    proposed_rate: float = Field(ge=0, le=30)


class VerifyCorrectionRequest(BaseModel):
    mortgage_id: str = Field(min_length=1)
    commit_id: str | None = Field(default=None, min_length=1)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/tools/search_customer")
async def search_customer(body: SearchCustomerRequest) -> dict[str, Any]:
    return logic.search_customer(body.query)


@app.post("/tools/get_mortgage")
async def get_mortgage(body: GetMortgageRequest) -> dict[str, Any]:
    result = logic.get_mortgage(body.mortgage_id)
    if result.get("error") == "not_found":
        raise HTTPException(status_code=404, detail="mortgage not found")
    return result


@app.post("/tools/get_payments")
async def get_payments(body: GetPaymentsRequest) -> dict[str, Any]:
    return logic.get_payments(body.mortgage_id, months=body.months)


@app.post("/tools/get_rate_history")
async def get_rate_history(body: GetRateHistoryRequest) -> dict[str, Any]:
    return logic.get_rate_history(body.mortgage_id)


@app.post("/tools/get_audit_history")
async def get_audit_history(body: GetAuditHistoryRequest) -> dict[str, Any]:
    return logic.get_audit_history(body.mortgage_id, limit=body.limit)


@app.post("/tools/calculate_adjustment")
async def calculate_adjustment(body: CalculateAdjustmentRequest) -> dict[str, Any]:
    result = logic.calculate_adjustment(body.mortgage_id, new_rate=body.new_rate)
    if result.get("error") == "not_found":
        raise HTTPException(status_code=404, detail="mortgage not found")
    return result


@app.post("/tools/prepare_correction")
async def prepare_correction(body: PrepareCorrectionRequest) -> dict[str, Any]:
    result = logic.prepare_correction(
        body.mortgage_id,
        proposed_rate=body.proposed_rate,
        effective_date=body.effective_date,
        slow_ms=body.slow_ms,
    )
    if result.get("error") == "not_found":
        raise HTTPException(status_code=404, detail="mortgage not found")
    return result


@app.post("/tools/recalculate_correction_draft")
async def recalculate_correction_draft(body: RecalculateCorrectionDraftRequest) -> dict[str, Any]:
    result = logic.recalculate_correction_draft(
        body.mortgage_id,
        effective_date=body.effective_date,
        proposed_rate=body.proposed_rate,
    )
    if result.get("error") == "not_found":
        raise HTTPException(status_code=404, detail="mortgage not found")
    return result


@app.post("/tools/commit_correction")
async def commit_correction(
    body: CommitCorrectionRequest,
    x_mortgage_commit_token: str | None = Header(default=None),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
) -> dict[str, Any]:
    result = logic.commit_correction(
        body.mortgage_id,
        effective_date=body.effective_date,
        proposed_rate=body.proposed_rate,
        auth_token=x_mortgage_commit_token,
        idempotency_key=idempotency_key,
    )
    if result.get("error") == "unauthorized":
        raise HTTPException(status_code=401, detail="unauthorized")
    if result.get("error") == "not_found":
        raise HTTPException(status_code=404, detail="mortgage not found")
    return result


@app.post("/tools/verify_correction")
async def verify_correction(body: VerifyCorrectionRequest) -> dict[str, Any]:
    result = logic.verify_correction(body.mortgage_id, commit_id=body.commit_id)
    if result.get("error") == "not_found":
        raise HTTPException(status_code=404, detail="mortgage not found")
    if result.get("error") == "commit_not_found":
        raise HTTPException(status_code=404, detail="commit not found")
    return result


def run() -> None:
    import uvicorn

    uvicorn.run(
        "mortgage_tools_api.main:app",
        host="0.0.0.0",
        port=int(__import__("os").environ.get("MORTGAGE_TOOLS_PORT", "8090")),
    )


if __name__ == "__main__":
    run()
