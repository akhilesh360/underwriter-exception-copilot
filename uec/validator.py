"""Runtime validation of an LLM-generated brief (layers A schema, B citations, C factual support, D policy)."""
from __future__ import annotations
import json
import re
from typing import Any

from pydantic import ValidationError

from uec.models import LLMBrief, FINAL_ACTIONS

INJECTION_PATTERNS = [
    r"ignore (all )?(previous|prior|above) instructions",
    r"disregard (all )?(previous|prior|above) instructions",
    r"system prompt", r"you are now", r"developer mode",
]
PRICING_RE = re.compile(r"\b(premium|pric(e|ing)|discount|rate (increase|decrease|change|recommendation)|"
                        r"recommend(ed)? (a )?rate|surcharge)\b", re.I)
NUM_RE = re.compile(r"\$?\d[\d,]*(?:\.\d+)?")
CLAIM_RE = re.compile(r"\bCLM-[A-Z0-9-]*\d[A-Z0-9]*\b")
IDENTITY_WORDS = ["verified", "confirmed", "belongs to", "same person", "is the applicant", "matches the applicant"]


def _ws(s: str) -> str:
    return " ".join(s.split())


def _digits(tok: str) -> str:
    return tok.replace("$", "").replace(",", "").rstrip(".")


def _strip_fences(t: str) -> str:
    t = t.strip()
    m = re.match(r"^```(?:json)?\s*(.*?)\s*```$", t, re.S | re.I)
    return m.group(1) if m else t


def _texts(item: dict) -> list[str]:
    return [v for v in item.values() if isinstance(v, str)]


def _injection(text: str) -> bool:
    return any(re.search(p, text, re.I) for p in INJECTION_PATTERNS)


def _analyze(brief: dict, bundle: dict, permitted: set[str] | None):
    """Returns (issues, fact_support, drop_paths, metrics)."""
    docs = {d["document_id"]: d for d in bundle.get("documents", [])}
    passages = {p["passage_id"]: p for p in bundle.get("passages", [])}
    issues, support, drop = [], [], set()
    m = {"items": 0, "citation_errors": 0, "unsupported": 0, "policy_errors": 0}

    def issue(layer, path, code, msg):
        issues.append({"layer": layer, "path": path, "code": code, "message": msg})

    def check_citations(path, ids) -> tuple[bool, list[str]]:
        ok, texts = True, []
        for eid in ids:
            p = passages.get(eid)
            if p is None:
                issue("B", path, "UNKNOWN_EVIDENCE_ID", f"evidence_id {eid} not in bundle"); ok = False; continue
            d = docs.get(p["document_id"])
            if d is None:
                issue("B", path, "MISSING_DOCUMENT", f"{eid}: document {p['document_id']} not in bundle"); ok = False; continue
            if d["content"][p["start_offset"]:p["end_offset"]] != p["text"]:
                issue("B", path, "OFFSET_MISMATCH", f"{eid}: passage text does not match document offsets"); ok = False
            if str(p.get("document_version")) != str(d.get("version")):
                issue("B", path, "VERSION_MISMATCH", f"{eid}: passage version {p.get('document_version')} != document version {d.get('version')}"); ok = False
            texts.append(p["text"])
        return ok, texts

    for section in ("known", "conflicts", "missing", "next_steps"):
        for i, item in enumerate(brief.get(section, [])):
            path = f"{section}[{i}]"
            m["items"] += 1
            bad_cite = bad_policy = False
            texts: list[str] = []
            if section in ("known", "conflicts"):
                ok, texts = check_citations(path, item.get("evidence_ids", []))
                if ok and section == "known":
                    q = _ws(item.get("quote", ""))
                    if not q or not any(q in _ws(t) for t in texts):
                        issue("B", path, "QUOTE_NOT_FOUND", "quote is not a substring of any cited passage"); ok = False
                bad_cite = not ok
            # Layer D
            if section == "next_steps":
                act = item.get("action")
                if act in {a.value for a in FINAL_ACTIONS}:
                    issue("D", path, "FINAL_DECISION", f"LLM recommended final decision {act}; only humans decide"); bad_policy = True
                elif permitted is not None and act not in permitted:
                    issue("D", path, "ACTION_NOT_PERMITTED", f"action {act} not in permitted actions"); bad_policy = True
            joined = " ".join(_texts(item))
            if PRICING_RE.search(joined):
                issue("D", path, "PRICING_CONTENT", "pricing/premium/rate content is out of scope"); bad_policy = True
            if _injection(joined):
                issue("D", path, "INJECTION_ECHO", "text echoes a prompt-injection instruction"); bad_policy = True
            # Layer C
            if section == "known" and not bad_cite:
                fact, src = item.get("fact", ""), " ".join(texts)
                src_nums = {_digits(t) for t in NUM_RE.findall(src)}
                missing = [t for t in NUM_RE.findall(fact) if _digits(t) not in src_nums]
                missing += [c for c in CLAIM_RE.findall(fact) if c not in src]
                low_f, low_s = fact.lower(), src.lower()
                ident = [w for w in IDENTITY_WORDS if w in low_f and w not in low_s]
                if missing:
                    st, reason = "UNSUPPORTED", f"not found in cited passages: {', '.join(missing)}"
                    issue("C", path, "UNSUPPORTED_FACT", reason); m["unsupported"] += 1; drop.add(path)
                elif ident:
                    st, reason = "NEEDS_VERIFICATION", f"identity/verification assertion not in source: {', '.join(ident)}"
                    issue("C", path, "NEEDS_VERIFICATION", reason)
                else:
                    st, reason = "SUPPORTED", "numbers/IDs found in cited passages"
                support.append({"path": path, "status": st, "reason": reason})
            if bad_cite:
                m["citation_errors"] += 1; drop.add(path)
            if bad_policy:
                m["policy_errors"] += 1; drop.add(path)
    return issues, support, drop, m


def validate_brief(raw_text: str, bundle: dict, permitted_actions: set[str] | None = None) -> dict[str, Any]:
    zero = {"items": 0, "citation_errors": 0, "unsupported": 0, "policy_errors": 0}
    out: dict[str, Any] = {"status": "FAILED", "schema_ok": False, "schema_errors": [], "raw_brief": None,
                           "validated_brief": None, "issues": [], "fact_support": [],
                           "raw_metrics": dict(zero), "validated_metrics": dict(zero)}
    try:
        raw = json.loads(_strip_fences(raw_text or ""))
    except json.JSONDecodeError as e:
        out["schema_errors"] = [f"invalid JSON: {e}"]
        out["issues"].append({"layer": "A", "path": "", "code": "INVALID_JSON", "message": str(e)})
        return out
    out["raw_brief"] = raw if isinstance(raw, dict) else None
    try:
        brief = LLMBrief.model_validate(raw)
    except ValidationError as e:
        out["schema_errors"] = [f"{'.'.join(map(str, x['loc']))}: {x['msg']}" for x in e.errors()]
        out["issues"] += [{"layer": "A", "path": "", "code": "SCHEMA_ERROR", "message": s} for s in out["schema_errors"]]
        return out
    sid = bundle["submission"]["submission_id"]
    if brief.submission_id != sid:
        msg = f"submission_id {brief.submission_id} != {sid}"
        out["schema_errors"] = [msg]
        out["issues"].append({"layer": "A", "path": "submission_id", "code": "SUBMISSION_MISMATCH", "message": msg})
        return out
    out["schema_ok"] = True
    data = brief.model_dump(mode="json")
    issues, support, drop, m = _analyze(data, bundle, permitted_actions)
    out.update(issues=issues, fact_support=support, raw_metrics=m)

    vdata = dict(data)
    for section in ("known", "conflicts", "missing", "next_steps"):
        vdata[section] = [it for i, it in enumerate(data[section]) if f"{section}[{i}]" not in drop]
    vbrief = LLMBrief.model_validate(vdata).model_dump(mode="json")
    out["validated_brief"] = vbrief
    out["validated_metrics"] = _analyze(vbrief, bundle, permitted_actions)[3]

    codes = {i["code"] for i in issues}
    if m["citation_errors"] or "FINAL_DECISION" in codes:
        out["status"] = "FAILED"
    elif issues:
        out["status"] = "FLAGGED"
    else:
        out["status"] = "VALIDATED"
    return out
