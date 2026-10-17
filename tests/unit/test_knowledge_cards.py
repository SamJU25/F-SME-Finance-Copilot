"""
Structural and policy-consistency checks for the retrieval concept cards in knowledge/cards/.

Cards are retrieved into model prompts, so a threshold that drifts from the decision tables
would make the model contradict the engine. The parity cases pin key thresholds to the JSON
policies they describe.
"""

import json
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
CARDS_DIR = ROOT / "knowledge" / "cards"
POLICY_DIR = ROOT / "contracts" / "decision_tables"
SECTIONS = ("**What it is:**", "**Why it matters:**", "**Healthy vs warning:**", "**What to do:**", "**In the app:**")
# "leverage" is omitted: in these cards it is the finance noun for debt load, which the
# policy tables themselves use (MODERATE_LEVERAGE), not the banned verb.
BANNED_WORDS = (
    "delve", "foster", "utilize", "facilitate", "empower", "streamline", "robust",
    "cutting-edge", "paradigm shift", "supercharge", "harness", "elevate", "transformative",
)
META_PATTERN = re.compile(r"<!--\s*(?:tools:\s*(?P<tools>[\w, ]+?))?\s*(?:\|\s*)?(?:policy:\s*(?P<policy>[\w, ]+?))?\s*-->")


def _load_cards() -> list[dict]:
    cards = []
    for path in sorted(CARDS_DIR.glob("*.md")):
        for block in re.split(r"^## ", path.read_text(encoding="utf-8"), flags=re.MULTILINE)[1:]:
            title, _, body = block.partition("\n")
            cards.append({"file": path.name, "title": title.strip(), "body": body.strip()})
    return cards


CARDS = _load_cards()
TOOL_NAMES = set(re.findall(r"^def (tool_\w+)", (ROOT / "services/agent/tools.py").read_text(encoding="utf-8"), re.MULTILINE))
POLICY_NAMES = {p.stem for p in POLICY_DIR.glob("*.json")}


def _card(title: str) -> str:
    return next(c["body"] for c in CARDS if c["title"] == title)


def test_card_count_and_unique_titles():
    titles = [c["title"] for c in CARDS]
    assert len(CARDS) >= 90
    assert len(titles) == len(set(titles))


@pytest.mark.parametrize("card", CARDS, ids=lambda c: c["title"])
def test_card_structure(card):
    body = card["body"]
    meta = META_PATTERN.match(body)
    assert meta, "card must start with a <!-- tools: ... | policy: ... --> line"

    positions = [body.find(s) for s in SECTIONS]
    assert all(p >= 0 for p in positions), f"missing section in {card['title']}"
    assert positions == sorted(positions), f"sections out of order in {card['title']}"

    words = len(re.sub(r"<!--.*?-->", "", body).split())
    assert 60 <= words <= 200, f"{card['title']} has {words} words"

    lowered = body.lower()
    for word in BANNED_WORDS:
        assert not re.search(rf"\b{re.escape(word)}\b", lowered), f"banned word '{word}' in {card['title']}"


@pytest.mark.parametrize("card", CARDS, ids=lambda c: c["title"])
def test_card_references_exist(card):
    meta = META_PATTERN.match(card["body"])
    for tool in filter(None, (t.strip() for t in (meta.group("tools") or "").split(","))):
        assert tool in TOOL_NAMES, f"unknown tool {tool} in {card['title']}"
    for policy in filter(None, (p.strip() for p in (meta.group("policy") or "").split(","))):
        assert policy in POLICY_NAMES, f"unknown policy {policy} in {card['title']}"


# (card title, policy file, threshold strings that must appear in both the card and the policy)
POLICY_PARITY = [
    ("Debt Service Coverage Ratio (DSCR)", "debt_covenant_policy", ["1.35", "1.25"]),
    ("Fixed Charge Coverage Ratio (FCCR)", "debt_covenant_policy", ["1.25", "1.15"]),
    ("Interest Coverage Ratio", "debt_covenant_policy", ["3.0", "1.5"]),
    ("Net Debt to EBITDA", "debt_covenant_policy", ["2.0", "3.5", "4.5"]),
    ("Altman Z'-Score (Distress Risk)", "debt_covenant_policy", ["2.90", "1.23"]),
    ("Predatory Lending Flag (36% APR)", "usury_policy", ["36.00"]),
    ("Defensive Interval Ratio (DIR)", "working_capital_policy", ["90", "30", "15"]),
    ("Days Sales Outstanding (DSO)", "working_capital_policy", ["30", "60"]),
    ("Days Payables Outstanding (DPO)", "working_capital_policy", ["30", "90"]),
    ("Early-Payment Discounts (Trade Credit APR)", "working_capital_policy", ["25", "15"]),
    ("Revenue Volatility (Coefficient of Variation)", "revenue_volatility_policy", ["0.35", "0.75"]),
    ("Customer Concentration (HHI)", "concentration_policy", ["50", "25", "2,500", "1,500"]),
    ("Risk Tiers (Prime, Near-Prime, High-Risk)", "underwriting_policy", ["10,000", "3,000"]),
    ("Maximum Qualified Limit", "underwriting_policy", ["3.0", "1.5", "0.5"]),
    ("LTV to CAC Ratio", "unit_economics_policy", ["4.0", "3.0", "1.5"]),
    ("CAC Payback Period", "unit_economics_policy", ["12", "18", "24"]),
    ("Net Revenue Retention (NRR)", "unit_economics_policy", ["120", "105", "95"]),
    ("Break-Even and Margin of Safety", "unit_economics_policy", ["30", "15"]),
]


@pytest.mark.parametrize("title,policy,thresholds", POLICY_PARITY, ids=[p[0] for p in POLICY_PARITY])
def test_card_thresholds_match_policy(title, policy, thresholds):
    card = _card(title)
    policy_text = (POLICY_DIR / f"{policy}.json").read_text(encoding="utf-8").replace(",", "")
    for value in thresholds:
        assert value in card, f"{title} card does not state {value}"
        assert value.replace(",", "") in policy_text, f"{value} not found in {policy}.json"
