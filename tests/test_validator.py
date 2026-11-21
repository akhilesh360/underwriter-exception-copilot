import json
from uec import service, validator


def bundle(tmp_path, sid="SUB-1042"):
    return service.detect(service.get_conn(str(tmp_path / "t.db")), sid)[0]


def brief(**kw):
    return json.dumps({"submission_id": "SUB-1042", "known": [], "conflicts": [], "missing": [], "next_steps": [], **kw})


def test_fabricated_citation_fails_and_is_dropped(tmp_path):
    v = validator.validate_brief(brief(known=[{"fact": "x", "evidence_ids": ["DOC-99-P1"], "quote": "x"}]), bundle(tmp_path))
    assert v["status"] == "FAILED"
    assert "UNKNOWN_EVIDENCE_ID" in {i["code"] for i in v["issues"]}
    assert v["validated_brief"]["known"] == []


def test_offsets_match_for_valid_citation(tmp_path):
    b = bundle(tmp_path)
    q = "Claim CLM-DEMO-7781: year 2021, indemnity paid $185,000, status CLOSED, defendant name A. Quill."
    v = validator.validate_brief(brief(known=[{"fact": "Claim CLM-DEMO-7781 paid $185,000.",
                                               "evidence_ids": ["DOC-02-P4"], "quote": q}]), b)
    assert v["status"] == "VALIDATED", v["issues"]
    p = next(p for p in b["passages"] if p["passage_id"] == "DOC-02-P4")
    d = next(d for d in b["documents"] if d["document_id"] == p["document_id"])
    assert d["content"][p["start_offset"]:p["end_offset"]] == p["text"]


def test_tampered_offsets_detected(tmp_path):
    b = bundle(tmp_path)
    for p in b["passages"]:
        if p["passage_id"] == "DOC-02-P4":
            p["start_offset"] += 1
    v = validator.validate_brief(brief(conflicts=[{"description": "d", "evidence_ids": ["DOC-02-P4"],
                                                   "verification_required": True}]), b)
    assert "OFFSET_MISMATCH" in {i["code"] for i in v["issues"]}


def test_unsupported_amount(tmp_path):
    v = validator.validate_brief(brief(known=[{"fact": "Paid $250,000.", "evidence_ids": ["DOC-02-P4"],
                                               "quote": "indemnity paid $185,000"}]), bundle(tmp_path))
    assert v["fact_support"][0]["status"] == "UNSUPPORTED"
    assert v["validated_brief"]["known"] == []


def test_final_decision_and_bad_json(tmp_path):
    b = bundle(tmp_path)
    v = validator.validate_brief(brief(next_steps=[{"action": "APPROVE", "reason": "ok"}]), b)
    assert v["status"] == "FAILED" and v["validated_brief"]["next_steps"] == []
    assert validator.validate_brief("not json", b)["schema_ok"] is False
