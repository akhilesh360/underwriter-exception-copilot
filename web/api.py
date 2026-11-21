"""FastAPI layer over uec.service. The policy gate lives in the backend: the API returns 403 on violations."""
from __future__ import annotations
import json, os, sqlite3, threading
from pathlib import Path
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from uec import db, service, policy, llm

STATIC = Path(__file__).parent / "static"
app = FastAPI(title="Underwriter Exception Copilot", version="1.0")
_lock = threading.Lock()


_conn = None
ROLES = {"underwriter", "senior_underwriter"}


def conn():
    """One shared connection, always used under _lock (no per-request connection leak)."""
    global _conn
    if _conn is None:
        _conn = sqlite3.connect(db.DB_PATH, check_same_thread=False)
        _conn.row_factory = sqlite3.Row
        db.init_db(_conn)
    return _conn


AI_LABEL = "Copilot AI"


def _neutral(obj):
    """Vendor-neutral responses: the configured model id is stored for audit but shown as a product label."""
    text = json.dumps(obj, default=str)
    for name in {llm.model_name()} | {m for m in os.environ.get("LLM_MODEL_ALIASES", "").split(",") if m}:
        text = text.replace(name, AI_LABEL)
    return json.loads(text)


def _check_role(role):
    if role not in ROLES:
        raise HTTPException(422, f"Unknown reviewer role; expected one of {sorted(ROLES)}")


class BriefReq(BaseModel):
    mode: str = "auto"

class EditReq(BaseModel):
    edited: dict
    reviewer_id: str
    reason: str = ""

class DecisionReq(BaseModel):
    action: str
    rationale: str
    reviewer_id: str
    reviewer_role: str = "underwriter"
    presented_rule_versions: dict | None = None

class EvalReq(BaseModel):
    mode: str = "cached"


@app.get("/api/status")
def status():
    pb = policy.load_playbook()
    return {"llm_available": llm.llm_available(), "model": "Copilot AI",
            "prompt_version": llm.PROMPT_VERSION, "playbook_version": pb.get("playbook_version"),
            "playbook_label": pb.get("label"), "data": "100% synthetic"}


@app.get("/api/queue")
def queue():
    with _lock:
        return service.list_queue(conn())


@app.get("/api/cases/{sid}")
def case(sid: str, role: str = "underwriter"):
    _check_role(role)
    with _lock:
        try:
            return _neutral(service.open_case(conn(), sid, role))
        except KeyError:
            raise HTTPException(404, f"Unknown submission {sid}")


@app.post("/api/cases/{sid}/brief")
def brief(sid: str, req: BriefReq):
    if req.mode not in ("auto", "live", "cached"):
        raise HTTPException(422, "mode must be auto|live|cached")
    with _lock:
        try:
            return _neutral(service.generate_brief(conn(), sid, mode=req.mode))
        except KeyError:
            raise HTTPException(404, f"Unknown submission {sid}")
        except (RuntimeError, FileNotFoundError) as e:
            import logging
            logging.getLogger("uec").warning("LLM generation failed for %s: %s", sid, e)
            raise HTTPException(503, "Live model generation unavailable. Retry, or use Cached mode (clearly labelled).")


@app.post("/api/cases/{sid}/brief/{brief_id}/edit")
def edit(sid: str, brief_id: int, req: EditReq):
    with _lock:
        try:
            return {"edited_brief_id": service.save_edit(conn(), sid, brief_id, req.edited, req.reviewer_id, req.reason)}
        except KeyError:
            raise HTTPException(404, f"Unknown brief {brief_id} for submission {sid}")


@app.post("/api/cases/{sid}/decision")
def decision(sid: str, req: DecisionReq):
    _check_role(req.reviewer_role)
    with _lock:
        try:
            did = service.record_decision(conn(), sid, req.action, req.rationale, req.reviewer_id,
                                          req.reviewer_role, req.presented_rule_versions)
        except KeyError:
            raise HTTPException(404, f"Unknown submission {sid}")
        except policy.PolicyViolation as e:
            return JSONResponse(status_code=403, content={"error": "policy_violation", "reason": e.reason})
        except ValueError as e:
            return JSONResponse(status_code=422, content={"error": "invalid", "reason": str(e)})
    return {"decision_id": did}


@app.get("/api/playbook")
def playbook():
    return policy.load_playbook()


@app.get("/api/evals/latest")
def evals_latest():
    with _lock:
        c = conn()
        run = c.execute("SELECT * FROM evaluation_runs ORDER BY run_id DESC LIMIT 1").fetchone()
        if not run:
            return {"run": None, "results": [], "history": []}
        res = [dict(r) for r in c.execute("SELECT * FROM evaluation_results WHERE run_id=?", (run["run_id"],))]
        hist = [dict(r) for r in c.execute("SELECT * FROM evaluation_runs ORDER BY run_id DESC LIMIT 10")]
        return _neutral({"run": dict(run), "results": res, "history": hist})


@app.post("/api/evals/run")
def evals_run(req: EvalReq):
    from evals import run_evals
    with _lock:
        out = run_evals.run(req.mode, db.DB_PATH, verbose=False)
    return _neutral(out)


@app.get("/")
def index():
    return FileResponse(STATIC / "index.html")


app.mount("/static", StaticFiles(directory=STATIC), name="static")
