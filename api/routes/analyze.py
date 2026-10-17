"""Bank statement CSV analysis endpoint; processes transactions in-memory without persistent writes."""

from __future__ import annotations

import json
import os
from datetime import date
from decimal import Decimal
from typing import Literal, Optional

from fastapi import APIRouter, File, Form, Header, Request, UploadFile
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict

from services.agent.schema import LLMConfig
from services.agent.session_store import session_store
from services.calculations.cash_analysis import calculate_cash_analysis
from services.calculations.runway import calculate_cash_conversion_cycle
from services.ingestion.csv_parser import CSVIngestionError, parse_bank_csv, parse_multiple_bank_csv
from services.ingestion.pdf_parser import parse_pdf_statement
from services.ingestion.pdf_validator import PDFValidationError

router = APIRouter(prefix="/api/v1", tags=["Cash analysis"])
MAX_UPLOAD_BYTES = int(os.getenv("MAX_ANALYSIS_UPLOAD_BYTES", "1048576"))



class RejectedRowResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    row_number: int
    reason_code: str


class AccountSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")
    file_name: str
    account_id: str
    start_date: str
    end_date: str
    closing_balance: str
    transaction_count: int


class ContraTransferSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")
    outflow_tx_id: str
    inflow_tx_id: str
    amount: str
    outflow_account: str
    inflow_account: str
    transfer_date: str


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
    accounts_breakdown: list[AccountSummary] | None = None
    internal_transfers_excluded: str | None = None
    internal_transfers: list[ContraTransferSummary] | None = None
    calendar_gaps: list[str] | None = None
    has_overlaps_deduped: bool | None = None
    operational_inflows: str | None = None
    operational_outflows: str | None = None
    document_format: Literal["CSV", "PDF", "HYBRID"] | None = None
    page_count: int | None = None
    normalized_csv: str | None = None


@router.post("/analyze", response_model=CashAnalysisResponse)
async def analyze_csv(
    request: Request,
    file: UploadFile | None = File(None),
    files: list[UploadFile] | None = File(None),
    alert_threshold_days: int = Form(30, gt=0),
    dso_days: int | None = Form(None, ge=0),
    dpo_days: int | None = Form(None, ge=0),
    dio_days: int | None = Form(0, ge=0),
    as_of_date: date | None = Form(None),
    x_llm_config: Optional[str] = Header(default=None, alias="X-LLM-Config"),
    x_session_id: Optional[str] = Header(default=None, alias="X-Session-ID"),
    x_tenant_id: Optional[str] = Header(default=None, alias="X-Tenant-ID"),
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
    try:
        form = await request.form()
        raw_items = form.getlist("files")
        if not raw_items:
            raw_items = form.getlist("file")
        for item in raw_items:
            if hasattr(item, "filename") and hasattr(item, "read"):
                upload_list.append(item)
    except Exception:
        pass

    if not upload_list:
        if files:
            upload_list.extend(files)
        elif file:
            upload_list.append(file)

    seen_names: set[str] = set()
    deduped_uploads: list[UploadFile] = []
    for u in upload_list:
        name = u.filename or "statement.csv"
        if name not in seen_names:
            seen_names.add(name)
            deduped_uploads.append(u)
    upload_list = deduped_uploads

    if not upload_list:
        return JSONResponse(
            status_code=422,
            content={"error": {"code": "INVALID_HEADER", "message": "Statement upload is required."}},
        )

    file_contents: list[tuple[str, bytes]] = []
    total_bytes = 0
    pdf_pages_total = 0
    has_pdf = False
    has_csv = False
    normalized_csv_parts: list[str] = []

    for upload in upload_list:
        content = await upload.read(MAX_UPLOAD_BYTES + 1)
        total_bytes += len(content)
        if total_bytes > MAX_UPLOAD_BYTES or len(content) > MAX_UPLOAD_BYTES:
            return JSONResponse(
                status_code=413,
                content={"error": {"code": "UPLOAD_TOO_LARGE", "message": "Statement upload exceeds the configured size limit."}},
            )
        filename = upload.filename or "statement.csv"
        is_pdf = filename.lower().endswith(".pdf") or content.startswith(b"%PDF")
        if is_pdf:
            has_pdf = True
            try:
                pdf_res = parse_pdf_statement(content, tenant_id=x_tenant_id or "SME-DEFAULT")
                pdf_pages_total += pdf_res.page_count
                csv_bytes = pdf_res.csv_text.encode("utf-8")
                normalized_csv_parts.append(pdf_res.csv_text)
                file_contents.append((filename, csv_bytes))
            except PDFValidationError as exc:
                return JSONResponse(status_code=422, content={"error": {"code": exc.code, "message": str(exc)}})
        else:
            has_csv = True
            try:
                normalized_csv_parts.append(content.decode("utf-8", errors="replace"))
            except Exception:
                pass
            file_contents.append((filename, content))

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

    acc_breakdown: list[AccountSummary] | None = None
    contra_excluded: str | None = None
    contra_summaries: list[ContraTransferSummary] | None = None
    cal_gaps: list[str] | None = None
    has_deduped: bool | None = None
    op_inflows: str | None = None
    op_outflows: str | None = None

    if ingestion.treasury is not None:
        t = ingestion.treasury
        acc_breakdown = [
            AccountSummary(
                file_name=a.file_name,
                account_id=a.account_id,
                start_date=a.start_date.isoformat(),
                end_date=a.end_date.isoformat(),
                closing_balance=_format_money(a.closing_balance),
                transaction_count=a.transaction_count,
            )
            for a in t.accounts
        ]
        if t.internal_transfer_volume > Decimal("0.00"):
            contra_excluded = _format_money(t.internal_transfer_volume)
        if t.internal_transfers:
            contra_summaries = [
                ContraTransferSummary(
                    outflow_tx_id=cp.outflow_tx_id,
                    inflow_tx_id=cp.inflow_tx_id,
                    amount=_format_money(cp.amount),
                    outflow_account=cp.outflow_account,
                    inflow_account=cp.inflow_account,
                    transfer_date=cp.transfer_date.isoformat(),
                )
                for cp in t.internal_transfers
            ]
        if t.calendar_gaps:
            cal_gaps = t.calendar_gaps
        has_deduped = t.has_overlaps_deduped
        op_inflows = _format_money(t.operational_inflows)
        op_outflows = _format_money(t.operational_outflows)

    doc_format: Literal["CSV", "PDF", "HYBRID"] = "CSV"
    if has_pdf and has_csv:
        doc_format = "HYBRID"
    elif has_pdf:
        doc_format = "PDF"

    combined_csv = "\n".join(normalized_csv_parts) if normalized_csv_parts else None
    if combined_csv and x_session_id:
        try:
            session_store.update_statement(
                session_id=x_session_id,
                csv_content=combined_csv,
                tenant_id=x_tenant_id or "SME-DEFAULT",
            )
        except Exception:
            pass

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
        accounts_breakdown=acc_breakdown,
        internal_transfers_excluded=contra_excluded,
        internal_transfers=contra_summaries,
        calendar_gaps=cal_gaps,
        has_overlaps_deduped=has_deduped,
        operational_inflows=op_inflows,
        operational_outflows=op_outflows,
        document_format=doc_format,
        page_count=pdf_pages_total if has_pdf else None,
        normalized_csv=combined_csv if has_pdf else None,
    )


def _format_money(value: Decimal) -> str:
    return format(value.quantize(Decimal("0.01")), "f")
