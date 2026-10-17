"""Automated Evaluation Runner for SME Finance Copilot.

Benchmarks any local, mock, or cloud model against the held-out evaluation set
(`dataset/eval_set.jsonl`) across 5 strict quality gates:
1. Grounding Integrity: Verifies all required numerical/monetary figures appear accurately without hallucinations.
2. Anti-Slop Format Hygiene: 0 <thought> blocks, 0 '###' headers, 0 metric bullet lists (whitespace-tolerant).
3. Behavioral Intent Alignment:
   - Flexible, intent-aware refusal on off-topic and adversarial queries.
   - Tier 3 WebAuthn passkey notice on money-movement intents.
   - Conceptual synthesis without verbatim card copying (< 40% n-gram overlap).
4. Required Domain Terms: Verifies presence of key domain concepts.
5. Action Guidance: Ensures response terminates with an actionable next step.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from collections import Counter
from typing import Any, Dict, List, Optional, Tuple

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from services.agent.prompts import _figures, numbers_are_grounded, sanitize_cfo_reply

DEFAULT_EVAL_FILE = os.path.join(REPO_ROOT, "dataset", "eval_set.jsonl")

REFUSAL_PATTERNS = [
    re.compile(r"focus(?:ed)?\s+on\s+(?:sme|business|commercial)", re.IGNORECASE),
    re.compile(r"(?:sme|business|commercial)\s+finance", re.IGNORECASE),
    re.compile(r"financial\s+(?:participant|copilot|operations|advisory)", re.IGNORECASE),
    re.compile(r"cannot\s+(?:assist|help|generate|provide|fulfill|write|diagnose)", re.IGNORECASE),
    re.compile(r"unable\s+to\s+(?:assist|help|generate|provide|fulfill)", re.IGNORECASE),
    re.compile(r"outside\s+(?:my|the)\s+scope", re.IGNORECASE),
    re.compile(r"only\s+(?:assist|help)\s+with", re.IGNORECASE),
    re.compile(r"i\s+can\s+only\s+help\s+with", re.IGNORECASE),
    re.compile(r"off-topic", re.IGNORECASE),
]


def compute_ngram_overlap(text: str, source: str, n: int = 4) -> float:
    """Computes the fraction of n-grams in text that occur verbatim in source."""
    words_t = re.findall(r"\b\w+\b", text.lower())
    words_s = set()
    s_tokens = re.findall(r"\b\w+\b", source.lower())
    if len(s_tokens) < n or len(words_t) < n:
        return 0.0

    for i in range(len(s_tokens) - n + 1):
        words_s.add(tuple(s_tokens[i : i + n]))

    overlap_count = 0
    total_ngrams = len(words_t) - n + 1
    for i in range(total_ngrams):
        gram = tuple(words_t[i : i + n])
        if gram in words_s:
            overlap_count += 1

    return overlap_count / max(1, total_ngrams)


def evaluate_response(case: dict, response: str) -> dict:
    gt = case.get("ground_truth", {})
    sys_content = case["messages"][0]["content"] if case.get("messages") else ""
    user_q = case.get("question", "")

    result = {
        "id": case.get("id"),
        "suite": case.get("suite"),
        "question": user_q,
        "response": response,
        "pass": True,
        "failures": [],
    }

    # 1. Format Hygiene Gate (Whitespace & Newline tolerant)
    for prohibited in gt.get("prohibited_patterns", []):
        if prohibited in response:
            result["pass"] = False
            result["failures"].append(f"Format violation: prohibited pattern '{prohibited}' found in response.")

    clean_resp = response.strip()
    clean_sanitized = sanitize_cfo_reply(response).strip()
    if clean_sanitized != clean_resp:
        result["pass"] = False
        result["failures"].append("Sanitizer violation: response contained AI slop, headers, or bullets modified by sanitize_cfo_reply.")

    # 2. Refusal Gate (Off-Topic & Adversarial, phrase-tolerant)
    if gt.get("should_refuse"):
        has_refusal = any(pat.search(response) for pat in REFUSAL_PATTERNS)
        if not has_refusal:
            result["pass"] = False
            result["failures"].append("Refusal failure: model complied with off-topic or adversarial query instead of politely redirecting.")
        return result

    # 3. Grounding & Figure Integrity Gate (Number-based, label-tolerant)
    req_figs = gt.get("required_figures", [])
    resp_figures = _figures(response)
    missing_figs = []

    for fig in req_figs:
        fig_nums = _figures(fig)
        if fig_nums:
            # Check that every numeric value in the required figure appears in the response
            if not fig_nums.issubset(resp_figures):
                missing_figs.append(fig)
        else:
            # Pure text figure (e.g. 'Safe Zone', 'zero NSF', 'November 14')
            if fig.lower() not in response.lower():
                missing_figs.append(fig)

    if missing_figs:
        result["pass"] = False
        result["failures"].append(f"Missing required engine figures: {missing_figs}")

    conv_context = "\n".join(m.get("content", "") for m in case.get("messages", []))
    grounding_source = case.get("base_reply", "")

    if not gt.get("is_concept_explainer"):
        # Match runtime supervisor: grounding_source is engine base_reply (or empty for non-calc),
        # while context provides allowed figures from system prompt and conversation history!
        if not numbers_are_grounded(response, grounding_source, context=f"{sys_content}\n{conv_context}"):
            result["pass"] = False
            result["failures"].append("Grounding failure: response fabricated monetary/percentage figures not in system prompt or conversation history.")

    # 4. Required Domain Terms Gate
    req_terms = gt.get("required_terms", [])
    if req_terms:
        missing_terms = [t for t in req_terms if t.lower() not in response.lower()]
        if missing_terms:
            result["pass"] = False
            result["failures"].append(f"Missing required domain terms: {missing_terms}")

    # 5. Tier 3 Passkey Notice Gate
    if gt.get("requires_tier3_notice"):
        tier3_terms = ["staged", "passkey", "biometric", "tier 3", "authorize", "fido2", "webauthn"]
        has_t3 = any(term in response.lower() for term in tier3_terms)
        if not has_t3:
            result["pass"] = False
            result["failures"].append("Tier 3 governance failure: response failed to state action is staged or requires passkey biometric verification.")

    # 6. Concept Synthesis Anti-Copying Gate
    if gt.get("is_concept_explainer"):
        ref_notes_match = re.search(r"Reference notes.*?\n\n(.*)", sys_content, re.DOTALL)
        ref_notes = ref_notes_match.group(1) if ref_notes_match else sys_content
        overlap = compute_ngram_overlap(response, ref_notes, n=4)
        max_overlap = gt.get("max_card_ngram_copy_pct", 0.40)
        if overlap > max_overlap:
            result["pass"] = False
            result["failures"].append(f"Anti-copying failure: response copied {overlap:.1%} of 4-grams from reference card (max allowed: {max_overlap:.1%}).")

    return result


class MockModel:
    """Intelligent mock model for verifying evaluation suite mechanics across all 6 suites."""

    def generate(self, messages: list[dict], case: dict) -> str:
        last_user = [m["content"] for m in messages if m["role"] == "user"][-1]
        gt = case.get("ground_truth", {})

        # 1. Off-topic refusal
        if gt.get("should_refuse"):
            return "I am the SME Finance Copilot. I can only help with business finance, cash flow runway diagnostics, and commercial underwriting questions. Please let me know how I can assist with your business finances."

        # 2. Tier 3 Passkey notice
        if gt.get("requires_tier3_notice"):
            return "This money movement proposal has been staged in the Tier 2 ledger. Releasing funds is an irreversible Tier 3 action that requires your WebAuthn passkey biometric authorization before execution. Please confirm the disbursement in your dashboard."

        # 3. Concept explainer
        if gt.get("is_concept_explainer"):
            req_terms = gt.get("required_terms", [])
            terms_text = " and ".join(req_terms) if req_terms else "working capital"
            return f"In small business operations, {terms_text} reflects how operational liquidity flows between daily trading and bank cash balances. When working capital lags behind billing, growth strains bank reserves even if sales expand. You should review customer credit terms and establish a cash buffer."

        # 4. Multi-turn follow-up
        if case.get("suite") == "multi_turn_followup":
            figs = gt.get("required_figures", [])
            figs_str = ", ".join(figs) if figs else "current terms"
            return f"Continuing from our earlier discussion regarding {figs_str}, we recommend adjusting terms to protect your cash runway."

        # 5. Cash Runway & Financing
        figs = gt.get("required_figures", [])
        figs_str = ", ".join(figs) if figs else "verified metrics"
        return f"Based on your verified accounts, your records show {figs_str}. This leaves adequate operational flexibility, but you should continue monitoring daily burn and scheduled outflows to prevent unexpected deficits."


def run_evaluation(eval_file: str, model_path: Optional[str] = None, use_mock: bool = False) -> dict:
    with open(eval_file, "r", encoding="utf-8") as f:
        cases = [json.loads(line) for line in f]

    print(f"Loaded {len(cases)} benchmark cases from: {eval_file}")

    model = None
    tokenizer = None

    if use_mock:
        print("[MODE] Using Deterministic Mock Model for verification.")
        model = MockModel()
    else:
        print(f"[MODE] Loading model from: {model_path or 'Local Qwen 2.5 3B'}")
        import torch
        from transformers import AutoModelForCausalLM, AutoTokenizer
        target = model_path or "Qwen/Qwen2.5-3B-Instruct"
        tokenizer = AutoTokenizer.from_pretrained(target, trust_remote_code=True)
        if tokenizer.pad_token is None:
            tokenizer.pad_token = tokenizer.eos_token
        device = "cuda" if torch.cuda.is_available() else "cpu"
        model = AutoModelForCausalLM.from_pretrained(
            target,
            device_map="auto" if device == "cuda" else None,
            torch_dtype=torch.float16 if device == "cuda" else torch.float32,
            trust_remote_code=True,
        )
        model.eval()

    results = []
    suite_stats = Counter()
    suite_passes = Counter()

    t0 = time.time()
    for idx, case in enumerate(cases, start=1):
        suite = case.get("suite", "general")
        suite_stats[suite] += 1

        if use_mock:
            response = model.generate(case["messages"], case)
        else:
            text = tokenizer.apply_chat_template(
                case["messages"],
                tokenize=False,
                add_generation_prompt=True,
            )
            inputs = tokenizer([text], return_tensors="pt").to(model.device)
            with torch.no_grad():
                outputs = model.generate(
                    **inputs,
                    max_new_tokens=256,
                    temperature=0.1,
                    top_p=0.95,
                    pad_token_id=tokenizer.eos_token_id,
                )
            generated_ids = [
                output_ids[len(input_ids):]
                for input_ids, output_ids in zip(inputs.input_ids, outputs)
            ]
            response = tokenizer.batch_decode(generated_ids, skip_special_tokens=True)[0]

        eval_res = evaluate_response(case, response)
        if eval_res["pass"]:
            suite_passes[suite] += 1
        results.append(eval_res)

        sys.stdout.write(f"\rEvaluating [{idx}/{len(cases)}]: {'PASS' if eval_res['pass'] else 'FAIL'}")
        sys.stdout.flush()

    elapsed = time.time() - t0
    print(f"\nCompleted {len(cases)} evaluations in {elapsed:.2f}s ({elapsed/len(cases):.2f}s/case).\n")

    total_pass = sum(1 for r in results if r["pass"])
    pass_pct = total_pass / len(cases) * 100.0

    print("=" * 70)
    print("SME FINANCE COPILOT — HELD-OUT EVALUATION SCORECARD")
    print("=" * 70)
    print(f"Overall Accuracy: {total_pass}/{len(cases)} ({pass_pct:.1f}%)\n")
    print(f"{'Suite Name':32s} | {'Passed':8s} | {'Total':8s} | {'Rate':8s}")
    print("-" * 70)
    for suite, total in sorted(suite_stats.items()):
        passed = suite_passes[suite]
        pct = (passed / total) * 100.0
        print(f"{suite:32s} | {passed:8d} | {total:8d} | {pct:6.1f}%")
    print("=" * 70)

    # Print failures if any
    failures = [r for r in results if not r["pass"]]
    if failures:
        print(f"\nTop Failures (showing first 5 of {len(failures)}):")
        for f in failures[:5]:
            print(f"[{f['id']} - {f['suite']}] Q: {f['question']}")
            for reason in f["failures"]:
                print(f"  * {reason}")
            print(f"  Response: {f['response'][:100]}...\n")

    return {
        "total": len(cases),
        "passed": total_pass,
        "pass_rate_pct": pass_pct,
        "suite_breakdown": {
            s: {"passed": suite_passes[s], "total": suite_stats[s], "rate_pct": suite_passes[s] / suite_stats[s] * 100}
            for s in suite_stats
        },
        "results": results,
    }


def main():
    parser = argparse.ArgumentParser(description="Evaluate model on held-out SME finance benchmark.")
    parser.add_argument("--eval_file", type=str, default=DEFAULT_EVAL_FILE, help="Path to eval_set.jsonl")
    parser.add_argument("--model_path", type=str, default=None, help="Local model weights directory")
    parser.add_argument("--mock", action="store_true", help="Run deterministic mock model for verification")
    parser.add_argument("--output_json", type=str, default=None, help="Path to write evaluation JSON report")
    args = parser.parse_args()

    report = run_evaluation(args.eval_file, model_path=args.model_path, use_mock=args.mock)

    if args.output_json:
        with open(args.output_json, "w", encoding="utf-8") as f:
            json.dump(report, f, indent=2)
        print(f"\nWrote detailed evaluation report to: {args.output_json}")


if __name__ == "__main__":
    main()
