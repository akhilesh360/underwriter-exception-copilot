from uec import detector, service


def codes(conn, sid):
    return [e["reason_code"] for e in service.detect(conn, sid)[1]]


def test_claim_mismatch_detected(tmp_path):
    conn = service.get_conn(str(tmp_path / "t.db"))
    _, exc = service.detect(conn, "SUB-1042")
    assert [e["reason_code"] for e in exc] == ["CLAIM_MISMATCH"]
    assert exc[0]["claim_id"] == "CLM-DEMO-7781" and exc[0]["verification_required"]


def test_clean_submission_has_no_exceptions(tmp_path):
    assert codes(service.get_conn(str(tmp_path / "t.db")), "SUB-1043") == []


def test_missing_loss_history(tmp_path):
    assert set(codes(service.get_conn(str(tmp_path / "t.db")), "SUB-1044")) == {
        "MISSING_LOSS_HISTORY", "INCOMPLETE_PRACTICE_INFO", "CREDENTIAL_GAP"}


def test_reported_claim_is_not_a_mismatch():
    sub = {"synthetic_npi": "N1", "practice_location": "X"}
    claim = {"claim_id": "C1", "physician_identifier": "N1", "claim_year": 2020, "claim_amount": 10}
    cred = [{"license_status": "ACTIVE", "verified_at": "2026-01-01"}]
    assert detector.detect_exceptions(sub, [{"claim_reference": "C1"}], [claim], cred) == []
    out = detector.detect_exceptions(sub, [{"claim_reference": "OTHER"}], [claim], cred)
    assert [r["code"] for r in out] == ["CLAIM_MISMATCH"]
