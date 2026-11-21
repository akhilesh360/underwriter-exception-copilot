"""Deterministic exception detector. No LLM. Ambiguous matches are flagged for verification, never confirmed."""
from __future__ import annotations

LOOKBACK_YEARS = 10
CURRENT_YEAR = 2026
SEVERITY = {"CLAIM_MISMATCH": "HIGH", "MISSING_LOSS_HISTORY": "HIGH", "INCOMPLETE_PRACTICE_INFO": "MEDIUM",
            "CREDENTIAL_GAP": "HIGH", "MANDATORY_REVIEW": "HIGH"}
MANDATORY_REVIEW_CLAIM_AMOUNT = 1_000_000


def potential_unreported_claim(submission: dict, loss_history: list[dict], claim: dict) -> bool:
    """Rule: external claim is keyed to the applicant's synthetic NPI, within lookback, and its
    reference is not among the claims the applicant reported."""
    if claim["physician_identifier"] != submission["synthetic_npi"]:
        return False
    if claim["claim_year"] is None or claim["claim_year"] < CURRENT_YEAR - LOOKBACK_YEARS:
        return False
    reported = {r["claim_reference"] for r in loss_history if r.get("claim_reference")}
    return claim["claim_id"] not in reported


def detect_exceptions(submission: dict, loss_history: list[dict], claims: list[dict], credentials: list[dict]) -> list[dict]:
    reasons: list[dict] = []
    for claim in claims:
        if potential_unreported_claim(submission, loss_history, claim):
            reasons.append({"code": "CLAIM_MISMATCH", "claim_id": claim["claim_id"], "verification_required": True})
        if (claim.get("claim_amount") or 0) >= MANDATORY_REVIEW_CLAIM_AMOUNT:
            reasons.append({"code": "MANDATORY_REVIEW", "claim_id": claim["claim_id"]})
    if not loss_history:
        reasons.append({"code": "MISSING_LOSS_HISTORY", "field": "loss_history"})
    if not (submission.get("practice_location") or "").strip():
        reasons.append({"code": "INCOMPLETE_PRACTICE_INFO", "field": "practice_location"})
    if not credentials or any(c["license_status"] != "ACTIVE" or not c.get("verified_at") for c in credentials):
        reasons.append({"code": "CREDENTIAL_GAP", "field": "credential_verification"})
    for r in reasons:
        r["severity"] = SEVERITY[r["code"]]
    return reasons
