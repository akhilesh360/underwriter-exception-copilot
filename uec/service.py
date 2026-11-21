"""Orchestration: detect -> retrieve -> synthesize -> validate -> govern -> decide -> audit.
The UI and evals call only this module."""
from __future__ import annotations
import json
from . import db, detector, retriever, policy, llm, validator

MAX_SCHEMA_RETRIES = 2


def get_conn(path=None):
    conn = db.connect(path)
    db.init_db(conn)
    return conn


def detect(conn, sid):
    """Run deterministic detection; persist exceptions (idempotent)."""
    b = retriever.build_evidence_bundle(conn, sid)
    found = detector.detect_exceptions(b["submission"], b["loss_history"], b["claims"], b["credentials"])
    exceptions = []
    for i, e in enumerate(found):
        eid = f"EXC-{sid}-{e['code']}-{i}"
        exceptions.append({**e, "exception_id": eid, "reason_code": e["code"], "severity": e["severity"],
                           "verification_required": e.get("verification_required", False), "detail": e})
        if not conn.execute("SELECT 1 FROM exceptions WHERE exception_id=?", (eid,)).fetchone():
            conn.execute("INSERT INTO exceptions VALUES(?,?,?,?,?,?,?)",
                         (eid, sid, e["code"], e["severity"], "OPEN", json.dumps(e), db.now()))
            db.audit(conn, sid, "system:detector", "EXCEPTION_DETECTED", after=e)
    conn.commit()
    return b, exceptions


def _brief_row(r):
    if r is None:
        return None
    d = dict(r)
    for k in ("known_json", "conflicts_json", "missing_json", "next_steps_json", "validation_json"):
        d[k.replace("_json", "")] = json.loads(d.pop(k) or "null")
    return d


def latest_briefs(conn, sid):
    gen = conn.execute("SELECT * FROM exception_briefs WHERE submission_id=? AND kind='GENERATED' "
                       "ORDER BY brief_id DESC LIMIT 1", (sid,)).fetchone()
    edit = conn.execute("SELECT * FROM exception_briefs WHERE submission_id=? AND kind='EDITED' "
                        "ORDER BY brief_id DESC LIMIT 1", (sid,)).fetchone()
    return _brief_row(gen), _brief_row(edit)


def open_case(conn, sid, reviewer_role="underwriter"):
    b, exceptions = detect(conn, sid)
    rules = policy.applicable_rules([e["reason_code"] for e in exceptions])
    unresolved = policy.has_unresolved_verification(exceptions)
    gen, edit = latest_briefs(conn, sid)
    return {
        "bundle": b, "exceptions": exceptions, "rules": rules,
        "rule_versions": policy.rule_versions(rules),
        "playbook_version": policy.load_playbook().get("playbook_version"),
        "completeness": policy.compute_completeness(b, exceptions),
        "actions": policy.permitted_actions(rules, reviewer_role, unresolved),
        "generated_brief": gen, "edited_brief": edit,
        "decisions": [dict(r) for r in conn.execute(
            "SELECT * FROM decisions WHERE submission_id=? ORDER BY decision_id", (sid,))],
        "audit": get_audit(conn, sid),
    }


def generate_brief(conn, sid, mode="auto", actor="system:llm"):
    """Generate + runtime-validate. Retries only on schema failure. Never hides the case on failure."""
    b, exceptions = detect(conn, sid)
    rules = policy.applicable_rules([e["reason_code"] for e in exceptions])
    perms = policy.permitted_actions(rules, "underwriter", policy.has_unresolved_verification(exceptions))
    allowed = {a for a, v in perms.items() if v["allowed"]}
    feedback, attempts = None, []
    for attempt in range(MAX_SCHEMA_RETRIES + 1):
        gen = llm.generate(b, exceptions, rules, mode=mode, feedback=feedback)
        val = validator.validate_brief(gen["raw_text"], b, allowed)
        attempts.append({"attempt": attempt + 1, "mode": gen["mode"], "schema_ok": val["schema_ok"]})
        if val["schema_ok"] or gen["mode"] == "cached":
            break
        feedback = "; ".join(val["schema_errors"])[:1500]
    vb = val["validated_brief"] or {}
    validation = {k: val[k] for k in ("status", "schema_ok", "schema_errors", "issues", "fact_support",
                                      "raw_metrics", "validated_metrics")}
    validation.update(attempts=attempts, raw_brief=val["raw_brief"], note=gen.get("note"),
                      cached_at=gen.get("cached_at"), generated_at=gen.get("generated_at"))
    cur = conn.execute(
        "INSERT INTO exception_briefs(submission_id,parent_brief_id,kind,model_version,prompt_version,generation_mode,"
        "raw_output,known_json,conflicts_json,missing_json,next_steps_json,validation_status,validation_json,created_by,created_at)"
        " VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (sid, None, "GENERATED", gen["model_version"], gen["prompt_version"], gen["mode"], gen["raw_text"],
         json.dumps(vb.get("known", [])), json.dumps(vb.get("conflicts", [])), json.dumps(vb.get("missing", [])),
         json.dumps(vb.get("next_steps", [])), val["status"], json.dumps(validation), actor, db.now()))
    conn.commit()
    db.audit(conn, sid, actor, "BRIEF_GENERATED", after={"brief_id": cur.lastrowid, "mode": gen["mode"],
             "model_version": gen["model_version"], "prompt_version": gen["prompt_version"],
             "validation_status": val["status"]})
    if val["status"] != "VALIDATED":
        db.audit(conn, sid, "system:validator", "VALIDATION_" + val["status"],
                 after={"brief_id": cur.lastrowid, "issues": val["issues"]})
    return latest_briefs(conn, sid)[0]


def save_edit(conn, sid, brief_id, edited: dict, reviewer_id, reason=""):
    """Edits are stored as a NEW row; the generated original is never modified."""
    parent = _brief_row(conn.execute("SELECT * FROM exception_briefs WHERE brief_id=? AND submission_id=?", (brief_id, sid)).fetchone())
    if parent is None:
        raise KeyError(brief_id)
    before = {k: parent[k] for k in ("known", "conflicts", "missing", "next_steps")}
    after = {k: edited.get(k, before[k]) for k in before}
    cur = conn.execute(
        "INSERT INTO exception_briefs(submission_id,parent_brief_id,kind,model_version,prompt_version,generation_mode,"
        "raw_output,known_json,conflicts_json,missing_json,next_steps_json,validation_status,validation_json,created_by,created_at)"
        " VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (sid, brief_id, "EDITED", parent["model_version"], parent["prompt_version"], "human_edit", None,
         json.dumps(after["known"]), json.dumps(after["conflicts"]), json.dumps(after["missing"]),
         json.dumps(after["next_steps"]), "HUMAN_EDITED", json.dumps(parent["validation"]), reviewer_id, db.now()))
    conn.commit()
    db.audit(conn, sid, reviewer_id, "BRIEF_EDITED", before=before, after=after, reason=reason)
    return cur.lastrowid


def record_decision(conn, sid, action, rationale, reviewer_id, reviewer_role="underwriter",
                    presented_rule_versions=None, brief_id=None):
    """Backend policy gate. Blocked attempts are audited and raise PolicyViolation."""
    if not (rationale or "").strip():
        raise ValueError("Rationale is required")
    if not (reviewer_id or "").strip():
        raise ValueError("Reviewer identity is required")
    b, exceptions = detect(conn, sid)
    rules = policy.applicable_rules([e["reason_code"] for e in exceptions])
    try:
        policy.check_action(action, rules, reviewer_role, policy.has_unresolved_verification(exceptions),
                            presented_rule_versions)
    except policy.PolicyViolation as e:
        db.audit(conn, sid, reviewer_id, "ACTION_BLOCKED", after={"action": action}, reason=e.reason)
        raise
    gen, edit = latest_briefs(conn, sid)
    ref = edit or gen
    cur = conn.execute(
        "INSERT INTO decisions(submission_id,brief_id,reviewer_id,reviewer_role,action,rationale,rule_versions_json,"
        "model_version,prompt_version,created_at) VALUES(?,?,?,?,?,?,?,?,?,?)",
        (sid, brief_id or (ref and ref["brief_id"]), reviewer_id, reviewer_role, action, rationale,
         json.dumps(policy.rule_versions(rules)), ref and ref["model_version"], ref and ref["prompt_version"], db.now()))
    conn.execute("UPDATE submissions SET status=? WHERE submission_id=?", (f"DECIDED:{action}", sid))
    conn.commit()
    db.audit(conn, sid, reviewer_id, "DECISION_RECORDED",
             after={"decision_id": cur.lastrowid, "action": action, "rule_versions": policy.rule_versions(rules)},
             reason=rationale)
    return cur.lastrowid


def get_audit(conn, sid):
    out = []
    for r in conn.execute("SELECT * FROM audit_events WHERE submission_id=? ORDER BY event_id", (sid,)):
        d = dict(r)
        d["before"] = json.loads(d.pop("before_json") or "null")
        d["after"] = json.loads(d.pop("after_json") or "null")
        out.append(d)
    return out


def list_queue(conn):
    out = []
    for s in conn.execute("SELECT * FROM submissions ORDER BY submission_id").fetchall():
        b, exc = detect(conn, s["submission_id"])
        c = policy.compute_completeness(b, exc)
        sev = "HIGH" if any(e["severity"] == "HIGH" for e in exc) else ("MEDIUM" if exc else "NONE")
        out.append({"submission_id": s["submission_id"], "specialty": s["specialty"],
                    "exceptions": [e["reason_code"] for e in exc], "priority": sev,
                    "status": s["status"], "completeness": f"{c['present']}/{c['required']}"})
    return out
