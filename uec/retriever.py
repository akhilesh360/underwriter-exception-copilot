"""Structured SQL retrieval. Returns only what exists - never invents evidence."""
from __future__ import annotations


def rows(conn, sql, *args):
    return [dict(r) for r in conn.execute(sql, args).fetchall()]


def get_submission(conn, submission_id: str) -> dict | None:
    r = rows(conn, "SELECT * FROM submissions WHERE submission_id=?", submission_id)
    return r[0] if r else None


def build_evidence_bundle(conn, submission_id: str) -> dict:
    sub = get_submission(conn, submission_id)
    if sub is None:
        raise KeyError(submission_id)
    loss = rows(conn, "SELECT * FROM loss_history WHERE submission_id=?", submission_id)
    claims = rows(conn, "SELECT * FROM claims_records WHERE physician_identifier=?", sub["synthetic_npi"])
    creds = rows(conn, "SELECT * FROM credentialing WHERE physician_id=?", sub["physician_id"])
    docs = rows(conn, "SELECT * FROM evidence_documents WHERE submission_id=? ORDER BY document_id", submission_id)
    passages = rows(conn, "SELECT p.* FROM evidence_passages p JOIN evidence_documents d USING(document_id) "
                          "WHERE d.submission_id=? ORDER BY p.passage_id", submission_id)
    return {"submission": sub, "loss_history": loss, "claims": claims, "credentials": creds,
            "documents": docs, "passages": passages}
