import sqlite3
import pytest
from uec import service


def test_decision_persists_across_reconnect(tmp_path):
    path = str(tmp_path / "t.db")
    conn = service.get_conn(path)
    did = service.record_decision(conn, "SUB-1042", "REQUEST_INFORMATION", "need claim docs", "uw-1")
    conn.close()
    conn2 = service.get_conn(path)
    row = conn2.execute("SELECT * FROM decisions WHERE decision_id=?", (did,)).fetchone()
    assert row["action"] == "REQUEST_INFORMATION" and row["reviewer_id"] == "uw-1"
    assert "DECISION_RECORDED" in [e["event_type"] for e in service.get_audit(conn2, "SUB-1042")]


def test_edit_is_new_row_and_original_unchanged(tmp_path):
    conn = service.get_conn(str(tmp_path / "t.db"))
    gen = service.generate_brief(conn, "SUB-1042", mode="cached")
    new_id = service.save_edit(conn, "SUB-1042", gen["brief_id"], {"missing": [{"field": "x", "reason": "y"}]},
                               "uw-1", reason="clarify")
    assert new_id != gen["brief_id"]
    orig, edit = service.latest_briefs(conn, "SUB-1042")
    assert orig["brief_id"] == gen["brief_id"] and orig["missing"] == gen["missing"]
    assert orig["raw_output"] == gen["raw_output"]
    assert edit["parent_brief_id"] == gen["brief_id"] and edit["missing"] == [{"field": "x", "reason": "y"}]


@pytest.mark.parametrize("sql", ["UPDATE audit_events SET reason='x'", "DELETE FROM audit_events"])
def test_audit_events_append_only(tmp_path, sql):
    conn = service.get_conn(str(tmp_path / "t.db"))
    service.detect(conn, "SUB-1042")
    with pytest.raises(sqlite3.DatabaseError):
        conn.execute(sql)
