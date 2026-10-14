---
name: e2e-testing
description: "End-to-end testing patterns and test authoring for SME Finance Copilot. Use when designing user flow tests, browser journey automation, CSV upload verification, row-level error provenance assertions, and security staging gates."
---

# End-to-End (E2E) Testing for SME Finance Copilot

Methodology for validating the end-to-end user journey across the full stack (API Gateway, Ingestion Parser, Calculation Engine, Security Gate, and Dashboard UI).

## 1. Core User Flow Coverage

Every release must satisfy tests across four integrated stages:

1. **Upload & Ingestion Stage**:
   - Submitting valid synthetic bank CSV files and verifying HTTP 200 responses.
   - Submitting malformed CSV files (bad shape, invalid date, negative burn) and verifying row-level provenance badges.
2. **Deterministic Calculation Stage**:
   - Asserting exact decimal strings for cash balance, net period change, and daily burn rate.
   - Verifying status pill shifts (`CASH_NONPOSITIVE`, `LOW_RUNWAY`, `WATCH`, `NO_BURN`).
3. **Underwriting Match Stage**:
   - Calling `/api/v1/underwrite` with Daily Average Balance (DAB) and NSF counts to verify pre-qualified loan options and True APR disclosure.
4. **Three-Tier Security Gate Stage**:
   - Staging a Tier 2 proposal via `/api/v1/actions/stage` and verifying it queues without moving funds.
   - Verifying that execution via `/api/v1/actions/execute` rejects unverified calls with HTTP 403 and succeeds only with biometric validation (`DEMO_FIDO2_PASSKEY_VALIDATED`).

## 2. Testing Invariants

- **Zero Real Bank Credentials**: E2E suites must use synthetic fixtures only; never hit external payment rails or live banking APIs.
- **Strict Decimal Verification**: Assert string values (e.g. `"9500.00"`) instead of converting to floating-point numbers in assertions.
- **Provenance Verification**: Validate that every rejected row displays the exact 1-indexed row number and stable reason code.
