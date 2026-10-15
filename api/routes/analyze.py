"""Bank statement CSV analysis endpoint; processes transactions in-memory without persistent writes."""

from __future__ import annotations

import json
import os
from datetime import date
from decimal import Decimal
from typing import Literal, Optional

from fastapi import APIRouter, File, Form, Header, UploadFile
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict

from services.agent.schema import LLMConfig
from services.calculations.cash_analysis import calculate_cash_analysis
from services.calculations.runway import calculate_cash_conversion_cycle
from services.ingestion.csv_parser import CSVIngestionError, parse_bank_csv, parse_multiple_bank_csv

router = APIRouter(prefix="/api/v1", tags=["Cash analysis"])
MAX_UPLOAD_BYTES = int(os.getenv("MAX_ANALYSIS_UPLOAD_BYTES", "1048576"))


class RejectedRowResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    row_number: int
    reason_code: str


class CashAnalysisResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    currency: str
    accepted_count: int
    rejected_rows: list[RejectedRowResponse]
    current_balance: str
    net_period_change: str
    period_days: int
    average_daily_burn: str
    runway_days: int | None
    alert_threshold_days: int
    cash_status: Literal["CASH_NONPOSITIVE", "LOW_RUNWAY", "WATCH", "NO_BURN"]
    gross_inflows: str | None = None
    gross_outflows: str | None = None
    cash_conversion_cycle_days: int | None = None
    working_capital_status: Literal["WORKING_CAPITAL_TRAP", "BALANCED", "CASH_GENERATIVE"] | None = None
    working_capital_rationale: str | None = None
    start_date: str | None = None
    end_date: str | None = None
    statement_age_days: int = 0
    analysis_mode: Literal["LIVE_OPERATING", "HISTORICAL_AUDIT"] = "LIVE_OPERATING"
    projected_depletion_date: str | None = None
    alert_boundary_date: str | None = None


@router.post("/analyze", response_model=CashAnalysisResponse)
async def analyze_csv(
    file: UploadFile | None = File(None),
    files: list[UploadFile] | None = File(None),
    alert_threshold_days: int = Form(30, gt=0),
    dso_days: int | None = Form(None, ge=0),
    dpo_days: int | None = Form(None, ge=0),
    dio_days: int | None = Form(0, ge=0),
    as_of_date: date | None = Form(None),
    x_llm_config: Optional[str] = Header(default=None, alias="X-LLM-Config"),
) -> CashAnalysisResponse | JSONResponse:
    if MAX_UPLOAD_BYTES <= 0:
        raise RuntimeError("MAX_ANALYSIS_UPLOAD_BYTES must be a positive integer")

    effective_llm_config: LLMConfig | None = None
    if x_llm_config:
        try:
            parsed = json.loads(x_llm_config)
            effective_llm_config = LLMConfig(**parsed)
        except Exception:
            pass

    upload_list: list[UploadFile] = []
    if files:
        upload_list.extend(files)
    if file:
        upload_list.append(file)

    if not upload_list:
        return JSONResponse(
            status_code=422,
            content={"error": {"code": "INVALID_HEADER", "message": "CSV upload is required."}},
        )

    file_contents: list[tuple[str, bytes]] = []
    total_bytes = 0
    for upload in upload_list:
        content = await upload.read(MAX_UPLOAD_BYTES + 1)
        total_bytes += len(content)
        if total_bytes > MAX_UPLOAD_BYTES or len(content) > MAX_UPLOAD_BYTES:
            return JSONResponse(
                status_code=413,
                content={"error": {"code": "UPLOAD_TOO_LARGE", "message": "CSV upload exceeds the configured size limit."}},
            )
        file_contents.append((upload.filename or "statement.csv", content))

    try:
        if len(file_contents) == 1:
            ingestion = parse_bank_csv(file_contents[0][1], llm_config=effective_llm_config)
        else:
            ingestion = parse_multiple_bank_csv(file_contents, llm_config=effective_llm_config)
    except CSVIngestionError as exc:
        return JSONResponse(status_code=422, content={"error": {"code": exc.code, "message": str(exc)}})

    result = calculate_cash_analysis(
        ingestion.accepted_rows,
        ingestion.rejected_rows,
        alert_threshold_days,
        as_of_date=as_of_date,
    )

    ccc_days, wc_status, wc_rationale = None, None, None
    if dso_days is not None and dpo_days is not None:
        ccc_days, wc_status, wc_rationale = calculate_cash_conversion_cycle(
            dso_days=dso_days,
            dpo_days=dpo_days,
            dio_days=dio_days or 0,
        )

    return CashAnalysisResponse(
        currency=result.currency,
        accepted_count=result.accepted_count,
        rejected_rows=[RejectedRowResponse(row_number=r.row_number, reason_code=r.reason_code) for r in result.rejected_rows],
        current_balance=_format_money(result.current_balance),
        net_period_change=_format_money(result.net_period_change),
        period_days=result.period_days,
        average_daily_burn=_format_money(result.average_daily_burn),
        runway_days=result.runway_days,
        alert_threshold_days=result.alert_threshold_days,
        cash_status=result.cash_status,
        gross_inflows=_format_money(result.gross_inflows),
        gross_outflows=_format_money(result.gross_outflows),
        cash_conversion_cycle_days=ccc_days,
        working_capital_status=wc_status,
        working_capital_rationale=wc_rationale,
        start_date=result.start_date,
        end_date=result.end_date,
        statement_age_days=result.statement_age_days,
        analysis_mode=result.analysis_mode,  # type: ignore[arg-type]
        projected_depletion_date=result.projected_depletion_date,
        alert_boundary_date=result.alert_boundary_date,
    )


def _format_money(value: Decimal) -> str:
    return format(value.quantize(Decimal("0.01")), "f")
