import pytest
from uec import policy, service


def test_backend_blocks_approve_on_claim_mismatch(tmp_path):
    conn = service.get_conn(str(tmp_path / "t.db"))
    with pytest.raises(policy.PolicyViolation):
        service.record_decision(conn, "SUB-1042", "APPROVE", "looks fine", "uw-1")
    events = [e["event_type"] for e in service.get_audit(conn, "SUB-1042")]
    assert "ACTION_BLOCKED" in events
    assert conn.execute("SELECT COUNT(*) FROM decisions").fetchone()[0] == 0


def test_stale_rule_version_rejected(tmp_path):
    conn = service.get_conn(str(tmp_path / "t.db"))
    with pytest.raises(policy.PolicyViolation, match="Stale rule version"):
        service.record_decision(conn, "SUB-1042", "REQUEST_INFORMATION", "need docs", "uw-1",
                                presented_rule_versions={"MPL-DEMO-002": "0.9"})
    assert service.record_decision(conn, "SUB-1042", "REQUEST_INFORMATION", "need docs", "uw-1",
                                   presented_rule_versions={"MPL-DEMO-002": "1.0"})


def test_rationale_required(tmp_path):
    conn = service.get_conn(str(tmp_path / "t.db"))
    with pytest.raises(ValueError):
        service.record_decision(conn, "SUB-1042", "REFER", "  ", "uw-1")
