"""
FastAPI router for Digital Transactional Underwriting and Financing Options Matching.
Processes bank transaction records and outputs objective credit dossiers with transparent APR disclosures.
"""

from __future__ import annotations

import os
from decimal import Decimal
from typing import Optional

from fastapi import APIRouter, File, Form, UploadFile
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict

from services.ingestion.csv_parser import CSVIngestionError, parse_bank_csv
from services.matcher.liquidity_matcher import (
    RiskTier,
    ProductType,
    underwrite_sme_transactions,
    match_financing_options,
)

router = APIRouter(prefix="/api/v1", tags=["Digital Underwriting"])
MAX_UPLOAD_BYTES = int(os.getenv("MAX_ANALYSIS_UPLOAD_BYTES", "1048576"))


class UnderwritingDossierResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    currency: str
    daily_average_balance: str
    transaction_count: int
    nsf_count: int
    risk_tier: RiskTier
    max_qualified_limit: str
    recommended_product_types: list[ProductType]


class FinancingOptionResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    provider: str
    product_type: ProductType
    facility_name: str
    max_amount: str
    term_days: int
    apr_percent: str
    is_predatory: bool
    suitability_score: int
    requires_tier_3_hitl: bool


class UnderwriteApiResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    dossier: UnderwritingDossierResponse
    matched_options: list[FinancingOptionResponse]


def _format_money(val: Decimal) -> str:
    return format(val.quantize(Decimal("0.01")), "f")


@router.post("/underwrite", response_model=UnderwriteApiResponse)
async def underwrite_statement(
    file: UploadFile = File(...),
    nsf_count: int = Form(0, ge=0),
) -> UnderwriteApiResponse | JSONResponse:
    """Performs digital underwriting on transaction CSV and matches credit options."""
    content = await file.read(MAX_UPLOAD_BYTES + 1)
    if len(content) > MAX_UPLOAD_BYTES:
        return JSONResponse(
            status_code=413,
            content={"error": {"code": "UPLOAD_TOO_LARGE", "message": "CSV upload exceeds the configured size limit."}},
        )

    try:
        ingestion = parse_bank_csv(content)
    except CSVIngestionError as exc:
        return JSONResponse(status_code=422, content={"error": {"code": exc.code, "message": str(exc)}})

    dossier = underwrite_sme_transactions(ingestion.accepted_rows, nsf_count=nsf_count)
    matched_options = match_financing_options(dossier)

    return UnderwriteApiResponse(
        dossier=UnderwritingDossierResponse(
            currency=dossier.currency,
            daily_average_balance=_format_money(dossier.daily_average_balance),
            transaction_count=dossier.transaction_count,
            nsf_count=dossier.nsf_count,
            risk_tier=dossier.risk_tier,
            max_qualified_limit=_format_money(dossier.max_qualified_limit),
            recommended_product_types=dossier.recommended_product_types,
        ),
        matched_options=[
            FinancingOptionResponse(
                provider=opt.provider,
                product_type=opt.product_type,
                facility_name=opt.facility_name,
                max_amount=_format_money(opt.max_amount),
                term_days=opt.term_days,
                apr_percent=_format_money(opt.apr_percent),
                is_predatory=opt.is_predatory,
                suitability_score=opt.suitability_score,
                requires_tier_3_hitl=opt.requires_tier_3_hitl,
            )
            for opt in matched_options
        ],
    )
