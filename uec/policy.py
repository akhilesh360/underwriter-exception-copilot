"""Deterministic policy gate over the synthetic playbook. Backend-enforced; never trusts the UI."""
from __future__ import annotations
import json
from pathlib import Path
from uec.models import Action, FINAL_ACTIONS

PLAYBOOK_PATH = Path(__file__).with_name("playbook.json")
ALL_ACTIONS = [a.value for a in Action]
FINAL = {a.value for a in FINAL_ACTIONS}
_BLOCK_WHY = {
    "MISSING_LOSS_HISTORY": "while loss history documentation is outstanding",
    "CLAIM_MISMATCH": "while claim identity verification is outstanding",
    "INCOMPLETE_PRACTICE_INFO": "while practice information is incomplete",
    "CREDENTIAL_GAP": "while credential review is outstanding",
    "MANDATORY_REVIEW": "pending mandatory senior review",
}


class PolicyViolation(Exception):
    def __init__(self, reason: str):
        super().__init__(reason)
        self.reason = reason


def load_playbook(path=None) -> dict:
    with open(path or PLAYBOOK_PATH) as f:
        return json.load(f)


def applicable_rules(reason_codes: list[str], playbook=None) -> list[dict]:
    pb = playbook or load_playbook()
    codes = set(reason_codes)
    seen, out = set(), []
    for r in pb["rules"]:
        if r["trigger"] in codes and r["rule_id"] not in seen:
            seen.add(r["rule_id"]); out.append(r)
    return out


def rule_versions(rules) -> dict[str, str]:
    return {r["rule_id"]: r["version"] for r in rules}


def _tag(r):
    return f"{r['rule_id']} v{r['version']}"


def permitted_actions(rules, reviewer_role="underwriter", unresolved_verification=False) -> dict[str, dict]:
    if not rules:
        return {a: {"allowed": True, "reason": "No exception rules triggered", "rule_ids": []} for a in ALL_ACTIONS}
    ids = [r["rule_id"] for r in rules]
    result = {}
    for a in ALL_ACTIONS:
        if a == Action.ESCALATE.value:
            result[a] = {"allowed": True, "reason": "Escalation is always available when exception rules apply", "rule_ids": ids}
            continue
        blockers = [r for r in rules if a not in r["permitted_actions"]]
        reasons = []
        if a in FINAL:
            verb = "approval" if a == "APPROVE" else "decline"
            for r in rules:
                if not r.get("final_decision_allowed", False):
                    reasons.append(f"{_tag(r)}: final {verb} blocked {_BLOCK_WHY.get(r['trigger'], 'by rule')}")
            if unresolved_verification and not reasons:
                reasons.append(f"Final {verb} blocked while verification is unresolved")
        else:
            reasons += [f"{_tag(r)}: {a} not a permitted action ({', '.join(r['permitted_actions'])})" for r in blockers]
        for r in rules:
            role = r.get("required_role")
            if role and role != reviewer_role and a in FINAL:
                reasons.append(f"{_tag(r)}: requires role '{role}' (reviewer is '{reviewer_role}')")
        if a in FINAL and unresolved_verification and reasons and not any("verification" in x for x in reasons):
            reasons.append("Verification is unresolved")
        rid = sorted({r["rule_id"] for r in rules if any(x.startswith(_tag(r)) for x in reasons)}) or ids
        if reasons:
            result[a] = {"allowed": False, "reason": "; ".join(reasons), "rule_ids": rid}
        else:
            result[a] = {"allowed": True, "reason": f"Permitted by {', '.join(_tag(r) for r in rules)}", "rule_ids": ids}
    return result


def check_action(action: str, rules, reviewer_role="underwriter", unresolved_verification=False,
                 presented_rule_versions: dict | None = None, playbook=None) -> None:
    if action not in ALL_ACTIONS:
        raise PolicyViolation(f"Unknown action: {action!r}")
    if presented_rule_versions is not None:
        pb = playbook or load_playbook()
        current = rule_versions(applicable_rules([r["trigger"] for r in rules], pb))
        if dict(presented_rule_versions) != current:
            raise PolicyViolation(f"Stale rule version: presented {presented_rule_versions}, current {current}")
    p = permitted_actions(rules, reviewer_role, unresolved_verification)[action]
    if not p["allowed"]:
        raise PolicyViolation(p["reason"])


def has_unresolved_verification(exceptions) -> bool:
    return any(e.get("verification_required") for e in exceptions)


def compute_completeness(bundle: dict, exceptions: list[dict]) -> dict:
    docs = bundle.get("documents") or []
    def doc(t):
        return next((d["document_id"] for d in docs if d.get("document_type") == t), None)
    items = []
    def add(name, present, source):
        items.append({"item": name, "present": bool(present), "source": source if present else None})
    app = doc("broker_application"); add("submitted_application", app, app)
    lh = bundle.get("loss_history") or []; add("submitted_loss_history", lh, "loss_history")
    ext = doc("external_claims_record"); add("external_claims_check", ext, ext)
    creds = bundle.get("credentials") or []
    ok = bool(creds) and all(c.get("license_status") == "ACTIVE" and c.get("verified_at") for c in creds)
    add("credential_verified", ok, ",".join(c["credential_id"] for c in creds) or None)
    flagged = {e.get("claim_id") for e in exceptions if e.get("code") == "CLAIM_MISMATCH"}
    claims = {c["claim_id"]: c for c in bundle.get("claims") or []}
    idv = all(claims.get(cid, {}).get("verification_status") == "VERIFIED" for cid in flagged)
    add("identity_verification", idv, "claims_records")
    add("claim_resolution_documentation", not flagged, "no_claim_mismatch")
    return {"present": sum(i["present"] for i in items), "required": len(items), "items": items}
