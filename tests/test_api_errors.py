"""Regression: API error paths return clean 4xx/503, not 500. Calls endpoint functions directly (no httpx)."""
import pytest
from fastapi import HTTPException
from uec import db, llm, service
from web import api


@pytest.fixture(autouse=True)
def _db(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", str(tmp_path / "api.db"))
    monkeypatch.setattr(api, "_conn", None)  # API keeps one shared connection; isolate per test


def _status(fn, *a):
    with pytest.raises(HTTPException) as ei:
        fn(*a)
    return ei.value.status_code


def test_brief_unknown_submission_404():
    assert _status(api.brief, "SUB-9999", api.BriefReq(mode="cached")) == 404


def test_decision_unknown_submission_404():
    req = api.DecisionReq(action="ESCALATE", rationale="x", reviewer_id="r")
    assert _status(api.decision, "SUB-9999", req) == 404


def test_edit_unknown_brief_404():
    assert _status(api.edit, "SUB-1042", 99999, api.EditReq(edited={}, reviewer_id="r")) == 404


def test_edit_brief_of_other_submission_404():
    b = api.brief("SUB-1042", api.BriefReq(mode="cached"))
    assert _status(api.edit, "SUB-1043", b["brief_id"], api.EditReq(edited={}, reviewer_id="r")) == 404


def test_live_api_failure_is_503(monkeypatch):
    monkeypatch.setenv("LLM_API_KEY", "k")
    def boom(_):
        raise ConnectionError("down")
    monkeypatch.setattr(llm, "_call_live", boom)
    assert _status(api.brief, "SUB-1042", api.BriefReq(mode="live")) == 503
    out = api.brief("SUB-1042", api.BriefReq(mode="auto"))
    assert out["generation_mode"] == "cached"
    assert "Live API call failed" in out["validation"]["note"]


def test_unknown_role_rejected():
    req = api.DecisionReq(action="APPROVE", rationale="x", reviewer_id="uw", reviewer_role="admin")
    assert _status(api.decision, "SUB-1043", req) == 422
