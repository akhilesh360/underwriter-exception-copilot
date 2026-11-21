"""SQLite schema + seed loader. Audit events are append-only (enforced by triggers)."""
from __future__ import annotations
import json, os, sqlite3
from datetime import datetime, timezone
from . import data

DB_PATH = os.environ.get("UEC_DB_PATH", os.path.join(os.path.dirname(__file__), "..", "uec.db"))

SCHEMA = """
CREATE TABLE IF NOT EXISTS submissions(submission_id TEXT PRIMARY KEY, physician_id TEXT, synthetic_npi TEXT,
  physician_name TEXT, specialty TEXT, practice_location TEXT, submitted_at TEXT, status TEXT);
CREATE TABLE IF NOT EXISTS loss_history(id INTEGER PRIMARY KEY AUTOINCREMENT, submission_id TEXT, claim_reference TEXT,
  claim_year INTEGER, claim_amount REAL, description TEXT, source_doc_id TEXT);
CREATE TABLE IF NOT EXISTS claims_records(claim_id TEXT PRIMARY KEY, physician_identifier TEXT, claim_year INTEGER,
  claim_amount REAL, claim_status TEXT, source_doc_id TEXT, verification_status TEXT);
CREATE TABLE IF NOT EXISTS credentialing(credential_id TEXT PRIMARY KEY, physician_id TEXT, license_state TEXT,
  license_status TEXT, specialty TEXT, verified_at TEXT, source_doc_id TEXT);
CREATE TABLE IF NOT EXISTS evidence_documents(document_id TEXT PRIMARY KEY, submission_id TEXT, document_type TEXT,
  title TEXT, content TEXT, version INTEGER, created_at TEXT);
CREATE TABLE IF NOT EXISTS evidence_passages(passage_id TEXT PRIMARY KEY, document_id TEXT, document_version INTEGER,
  page INTEGER, start_offset INTEGER, end_offset INTEGER, text TEXT);
CREATE TABLE IF NOT EXISTS exceptions(exception_id TEXT PRIMARY KEY, submission_id TEXT, reason_code TEXT,
  severity TEXT, status TEXT, detail_json TEXT, detected_at TEXT);
CREATE TABLE IF NOT EXISTS exception_briefs(brief_id INTEGER PRIMARY KEY AUTOINCREMENT, submission_id TEXT,
  parent_brief_id INTEGER, kind TEXT, model_version TEXT, prompt_version TEXT, generation_mode TEXT,
  raw_output TEXT, known_json TEXT, conflicts_json TEXT, missing_json TEXT, next_steps_json TEXT,
  validation_status TEXT, validation_json TEXT, created_by TEXT, created_at TEXT);
CREATE TABLE IF NOT EXISTS decisions(decision_id INTEGER PRIMARY KEY AUTOINCREMENT, submission_id TEXT, brief_id INTEGER,
  reviewer_id TEXT, reviewer_role TEXT, action TEXT, rationale TEXT, rule_versions_json TEXT, model_version TEXT,
  prompt_version TEXT, created_at TEXT);
CREATE TABLE IF NOT EXISTS audit_events(event_id INTEGER PRIMARY KEY AUTOINCREMENT, submission_id TEXT, actor TEXT,
  event_type TEXT, before_json TEXT, after_json TEXT, reason TEXT, timestamp TEXT);
CREATE TRIGGER IF NOT EXISTS audit_no_update BEFORE UPDATE ON audit_events BEGIN SELECT RAISE(ABORT,'audit_events is append-only'); END;
CREATE TRIGGER IF NOT EXISTS audit_no_delete BEFORE DELETE ON audit_events BEGIN SELECT RAISE(ABORT,'audit_events is append-only'); END;
CREATE TABLE IF NOT EXISTS evaluation_runs(run_id INTEGER PRIMARY KEY AUTOINCREMENT, dataset_version TEXT, model_version TEXT,
  prompt_version TEXT, rule_version TEXT, started_at TEXT, completed_at TEXT, status TEXT);
CREATE TABLE IF NOT EXISTS evaluation_results(result_id INTEGER PRIMARY KEY AUTOINCREMENT, run_id INTEGER, eval_case_id TEXT,
  metric_name TEXT, observed_value REAL, threshold REAL, passed INTEGER, failure_reason TEXT, stage TEXT);
"""


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def connect(path: str | None = None) -> sqlite3.Connection:
    conn = sqlite3.connect(path or DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA)
    if conn.execute("SELECT COUNT(*) FROM submissions").fetchone()[0] == 0:
        seed(conn)


def seed(conn: sqlite3.Connection) -> None:
    for s in data.SUBMISSIONS:
        conn.execute("INSERT INTO submissions VALUES(:submission_id,:physician_id,:synthetic_npi,:physician_name,"
                     ":specialty,:practice_location,:submitted_at,:status)", s)
    for d in data.DOCUMENTS:
        content, offsets = "", []
        for pid, page, text in d["passages"]:
            if content:
                content += "\n"
            offsets.append((pid, page, len(content), len(content) + len(text), text))
            content += text
        conn.execute("INSERT INTO evidence_documents VALUES(?,?,?,?,?,?,?)",
                     (d["document_id"], d["submission_id"], d["document_type"], d["title"], content, d["version"], now()))
        for pid, page, start, end, text in offsets:
            conn.execute("INSERT INTO evidence_passages VALUES(?,?,?,?,?,?,?)",
                         (pid, d["document_id"], d["version"], page, start, end, text))
    for r in data.LOSS_HISTORY:
        conn.execute("INSERT INTO loss_history(submission_id,claim_reference,claim_year,claim_amount,description,source_doc_id)"
                     " VALUES(:submission_id,:claim_reference,:claim_year,:claim_amount,:description,:source_doc_id)", r)
    for r in data.CLAIMS_RECORDS:
        conn.execute("INSERT INTO claims_records VALUES(:claim_id,:physician_identifier,:claim_year,:claim_amount,"
                     ":claim_status,:source_doc_id,:verification_status)", r)
    for r in data.CREDENTIALING:
        conn.execute("INSERT INTO credentialing VALUES(:credential_id,:physician_id,:license_state,:license_status,"
                     ":specialty,:verified_at,:source_doc_id)", r)
    conn.commit()


def audit(conn, submission_id, actor, event_type, before=None, after=None, reason=None) -> None:
    conn.execute("INSERT INTO audit_events(submission_id,actor,event_type,before_json,after_json,reason,timestamp)"
                 " VALUES(?,?,?,?,?,?,?)", (submission_id, actor, event_type,
                 json.dumps(before) if before is not None else None,
                 json.dumps(after) if after is not None else None, reason, now()))
    conn.commit()
