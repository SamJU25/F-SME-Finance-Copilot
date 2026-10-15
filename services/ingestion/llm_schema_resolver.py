"""Dynamic LLM Schema Resolver for ambiguous, foreign-language, or unstructured financial CSVs."""

from __future__ import annotations

import json
import re
from typing import Any, Sequence

from services.agent.llm_bridge import mask_pii, query_external_llm
from services.agent.schema import LLMConfig
from services.ingestion.dynamic_profiler import ProfiledSchema


SYSTEM_SCHEMA_DIRECTIVE = """You are an institutional financial ingestion engine.
Given sample CSV lines from a business financial statement, identify the zero-indexed column positions for standard banking fields.
You must return a valid, single JSON object only, with no markdown, no explanation, no backticks:
{
  "date_col": <integer>,
  "amount_col": <integer or null>,
  "debit_col": <integer or null>,
  "credit_col": <integer or null>,
  "balance_col": <integer or null>,
  "description_col": <integer or null>,
  "currency_col": <integer or null>
}
Rules:
1. date_col is mandatory (the column containing dates or timestamps).
2. If the statement has a single Net Amount column, amount_col must be populated and debit_col/credit_col should be null.
3. If the statement uses separate Debit and Credit columns, debit_col and credit_col must be populated and amount_col should be null.
4. description_col should point to the payee, merchant, or transaction narrative.
5. All column values must be integers or null.
"""


def resolve_schema_with_llm(
    sample_rows: Sequence[Sequence[str]],
    llm_config: LLMConfig | None = None,
) -> ProfiledSchema | None:
    """Uses LLM reasoning to map semantic column roles when statistical profiling is uncertain."""
    if not sample_rows or len(sample_rows) < 1:
        return None

    # Format 3 sample rows for the prompt
    sample_lines = []
    for idx, row in enumerate(sample_rows[:4]):
        cleaned_cells = [mask_pii(cell.strip()) for cell in row]
        sample_lines.append(f"Row {idx}: " + " | ".join(cleaned_cells))

    user_prompt = "Sample CSV rows:\n" + "\n".join(sample_lines)

    response_text = query_external_llm(
        prompt=user_prompt,
        system_instruction=SYSTEM_SCHEMA_DIRECTIVE,
        config=llm_config,
    )

    if not response_text:
        return None

    # Parse JSON from response
    try:
        # Strip potential markdown code fences
        cleaned = re.sub(r"^```(?:json)?", "", response_text.strip(), flags=re.MULTILINE)
        cleaned = re.sub(r"```$", "", cleaned.strip(), flags=re.MULTILINE).strip()
        data = json.loads(cleaned)

        date_col = data.get("date_col")
        amount_col = data.get("amount_col")
        debit_col = data.get("debit_col")
        credit_col = data.get("credit_col")
        balance_col = data.get("balance_col")
        description_col = data.get("description_col")
        currency_col = data.get("currency_col")

        if date_col is None or not isinstance(date_col, int):
            return None

        has_amount = isinstance(amount_col, int)
        has_debit_credit = isinstance(debit_col, int) or isinstance(credit_col, int)
        if not (has_amount or has_debit_credit):
            return None

        return ProfiledSchema(
            date_col=date_col,
            amount_col=amount_col if isinstance(amount_col, int) else None,
            debit_col=debit_col if isinstance(debit_col, int) else None,
            credit_col=credit_col if isinstance(credit_col, int) else None,
            balance_col=balance_col if isinstance(balance_col, int) else None,
            description_col=description_col if isinstance(description_col, int) else None,
            currency_col=currency_col if isinstance(currency_col, int) else None,
            confidence=0.95,
            detection_method="llm_semantic_resolution",
        )
    except Exception:
        return None
