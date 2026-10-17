"""Declarative policy configuration loader for Decision Engine contracts.

Loads pattern regexes, defaults, and semantic prototypes from contracts/decision_tables/
to prevent hardcoding in adapters, routers, or agent services.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
import re
from typing import Any, Dict, Tuple

logger = logging.getLogger(__name__)

DECISION_TABLES_DIR = Path(__file__).resolve().parent.parent.parent / "contracts" / "decision_tables"


def load_security_policy_config(tables_dir: Path | None = None) -> Tuple[re.Pattern, re.Pattern, Dict[str, Any]]:
    """Loads prompt injection patterns, credential patterns, and staging defaults dynamically from security_gate_policy.json."""
    base_dir = tables_dir or DECISION_TABLES_DIR
    sec_file = base_dir / "security_gate_policy.json"
    inj_pat: re.Pattern | None = None
    cred_pat: re.Pattern | None = None
    defaults: Dict[str, Any] = {
        "default_action_type": "DRAW_CREDIT_LINE",
        "default_amount_cents": 2500000,
        "default_target_identifier": "SME-LIQUIDITY-FACILITY",
    }
    if sec_file.exists():
        try:
            with open(sec_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            patterns = data.get("prompt_security_patterns", {})
            if patterns.get("injection_regex"):
                inj_pat = re.compile(patterns["injection_regex"], re.IGNORECASE)
            if patterns.get("credential_regex"):
                cred_pat = re.compile(patterns["credential_regex"], re.IGNORECASE)
            if data.get("staging_defaults"):
                defaults.update(data["staging_defaults"])
        except Exception as exc:
            logger.warning("Could not load security policy configuration from %s: %s", sec_file, exc)

    if inj_pat is None:
        inj_pat = re.compile(
            r"(ignore|disregard|forget|override)\s+(all\s+)?(?:previous\s+)?(?:instructions|prompts|rules|guidelines|security)"
            r"|system\s+override"
            r"|you\s+are\s+now\s+(?:an?\s+)?unrestricted"
            r"|bypass\s+(?:2fa|biometric|security|hitl|tier)"
            r"|admin\s+mode\s+enabled",
            re.IGNORECASE,
        )
    if cred_pat is None:
        cred_pat = re.compile(
            r"\b(?:sk-ant-[a-zA-Z0-9_\-]{20,}|sk-[a-zA-Z0-9_\-]{20,}|AIzaSy[a-zA-Z0-9_\-]{30,}|gsk_[a-zA-Z0-9_\-]{20,})\b"
            r"|(?:api[_-]?key|secret[_-]?token|bearer[_-]?token|password|pin|routing[_-]?number)\s*[:=]\s*['\"]?([a-zA-Z0-9_\-]{4,})['\"]?",
            re.IGNORECASE,
        )
    return inj_pat, cred_pat, defaults


def load_semantic_prototypes(tables_dir: Path | None = None) -> Tuple[Dict[str, str], Dict[str, str], str]:
    """Loads semantic intent and sub-intent vector prototypes dynamically from semantic_intent_prototypes.json."""
    base_dir = tables_dir or DECISION_TABLES_DIR
    proto_file = base_dir / "semantic_intent_prototypes.json"
    if proto_file.exists():
        try:
            with open(proto_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            return (
                data.get("intent_prototypes", {}),
                data.get("sub_intent_prototypes", {}),
                data.get("disclaimer_prototype", ""),
            )
        except Exception as exc:
            logger.warning("Failed to load semantic prototypes from %s: %s", proto_file, exc)
    return {}, {}, ""
