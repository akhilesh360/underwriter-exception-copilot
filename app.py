"""Underwriter Exception Copilot - Streamlit UI (synthetic prototype).
All backend calls go through uec.service. The UI never decides policy; the backend gate does."""
from __future__ import annotations
import html
import json
import sqlite3

import pandas as pd
import streamlit as st

from uec import db, llm, policy, service

st.set_page_config(page_title="Underwriter Exception Copilot", page_icon="🛡️", layout="wide",
                   initial_sidebar_state="expanded")

ACTIONS = ["APPROVE", "DECLINE", "REQUEST_INFORMATION", "REFER", "ESCALATE"]
ACTION_LABEL = {"APPROVE": "Approve", "DECLINE": "Decline", "REQUEST_INFORMATION": "Request information",
                "REFER": "Refer", "ESCALATE": "Escalate"}
MODE_MAP = {"Auto": "auto", "Live DeepSeek": "live", "Cached": "cached"}

CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Source+Sans+3:wght@400;500;600;700&display=swap');
:root{--p:#3A0CA3;--pd:#2A0A6E;--ac:#5B3FC4;--lav:#B8B0E3;--lav2:#EEEBFA;--sky:#A9C9E8;--ok:#0F8B8D;--warn:#C98A0B;--bad:#B42318;
--bg:#F7F6FC;--sf:#FFFFFF;--bd:#E4E0F3;--tx:#3A3A3A;--mu:#6B6B7B;}
html,body,[class*="css"],.stApp,button,input,textarea,select{font-family:'Source Sans 3',system-ui,sans-serif !important;}
.stApp{background:var(--bg);}
#MainMenu,footer,header[data-testid="stHeader"]{visibility:hidden;height:0;}
[data-testid="stToolbar"],[data-testid="stDecoration"]{display:none;}
.block-container{padding-top:1rem;padding-bottom:2rem;max-width:100%;}
section[data-testid="stSidebar"]{background:var(--sf);border-right:1px solid var(--bd);}
.uec-header{background:var(--pd);color:#fff;border-radius:10px;
  padding:18px 24px;margin-bottom:14px;display:flex;align-items:center;justify-content:space-between;}
.uec-header h1{font-size:1.6rem;font-weight:500;margin:0;color:#fff;letter-spacing:-.01em;padding:0;}
.uec-header .sub{font-size:.78rem;color:#D9D3F5;margin-top:4px;}
.uec-header .tag{font-size:.72rem;border:1px solid rgba(255,255,255,.35);border-radius:999px;padding:4px 10px;color:#fff;}
.card{background:var(--sf);border:1px solid var(--bd);border-radius:10px;padding:12px 14px;margin-bottom:8px;}
.card.sel{border:2px solid var(--ac);box-shadow:0 2px 10px rgba(58,12,163,.15);}
.card h4{margin:0 0 4px 0;font-size:1.05rem;color:#3A3A3A;font-weight:600;padding:0;}
.muted{color:var(--mu);font-size:.8rem;}
.sec{font-size:.72rem;font-weight:700;letter-spacing:.06em;text-transform:uppercase;color:var(--mu);margin:10px 0 6px;}
.colhead{font-size:1.2rem;font-weight:500;color:#3A3A3A;border-bottom:2px solid var(--p);padding-bottom:6px;margin-bottom:10px;}
.pill{display:inline-block;padding:2px 9px;border-radius:999px;font-size:.7rem;font-weight:600;margin:2px 4px 2px 0;
  border:1px solid var(--bd);background:var(--lav2);color:var(--p);}
.pill.ok{background:#E3F4F4;color:var(--ok);border-color:#BFE3E3;}
.pill.warn{background:#FBF1DC;color:#8A5E00;border-color:#EED7A3;}
.pill.bad{background:#FCE8E6;color:var(--bad);border-color:#F4C1BB;}
.pill.ai{background:var(--lav2);color:var(--ac);border:1px dashed var(--ac);}
.pill.dark{background:var(--p);color:#fff;border-color:var(--p);}
.ai{border:1.5px dashed var(--ac);background:#FBFAFE;border-radius:10px;padding:10px 12px;margin-bottom:8px;}
.ai .lbl{font-size:.68rem;font-weight:700;color:var(--ac);letter-spacing:.05em;}
.det{border-left:4px solid var(--p);}
.banner{border-radius:8px;padding:9px 12px;font-size:.82rem;font-weight:600;margin:6px 0;}
.banner.ok{background:#E3F4F4;color:var(--ok);border:1px solid #BFE3E3;}
.banner.warn{background:#FBF1DC;color:#7A5300;border:1px solid #EED7A3;}
.banner.bad{background:#FCE8E6;color:var(--bad);border:1px solid #F4C1BB;}
.banner.info{background:var(--lav2);color:var(--pd);border:1px solid var(--lav);border-left:4px solid var(--sky);}
.meter{height:8px;background:var(--lav2);border-radius:999px;overflow:hidden;margin:6px 0 8px;}
.meter>div{height:100%;background:linear-gradient(90deg,var(--ac),var(--p));}
.chk{font-size:.82rem;margin:2px 0;}
.chk .y{color:var(--ok);font-weight:700;}.chk .n{color:var(--bad);font-weight:700;}
.blocked{background:#FAFAFC;border:1px solid var(--bd);border-radius:8px;padding:8px 10px;margin:4px 0;font-size:.78rem;color:var(--mu);}
.blocked b{color:var(--bad);}
.doc{background:#fff;border:1px solid var(--bd);border-radius:8px;padding:12px;font-family:ui-monospace,Menlo,monospace;
  font-size:.8rem;white-space:pre-wrap;line-height:1.5;}
mark{background:#F4C95D;padding:0 2px;border-radius:3px;}
.tl{border-left:2px solid var(--bd);margin-left:6px;padding-left:12px;}
.tl .ev{position:relative;font-size:.76rem;margin-bottom:8px;}
.tl .ev:before{content:"";position:absolute;left:-18px;top:4px;width:9px;height:9px;border-radius:50%;background:var(--ac);}
.tl .ev.bad:before{background:var(--bad);} .tl .ev.ok:before{background:var(--ok);}
.stButton>button{border-radius:8px;font-weight:600;}
.stButton>button[kind="primary"],.stFormSubmitButton>button{background:var(--p);border-color:var(--p);color:#fff;}
.stButton>button[kind="primary"]:hover{background:#2E0A82;border-color:#2E0A82;}
.stTabs [data-baseweb="tab"]{font-weight:600;}
div[data-testid="stMetricValue"]{font-size:1.3rem;}
</style>
"""
st.markdown(CSS, unsafe_allow_html=True)


# --------------------------------------------------------------------------- data access
@st.cache_resource
def get_conn():
    conn = sqlite3.connect(db.DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    db.init_db(conn)
    return conn


conn = get_conn()
e = html.escape


def pill(text, kind=""):
    return f'<span class="pill {kind}">{e(str(text))}</span>'


def fmt_ts(ts):
    return (ts or "—").replace("T", " ").replace("+00:00", " UTC")


# --------------------------------------------------------------------------- header + sidebar
st.markdown(
    '<div class="uec-header"><div><h1>Underwriter Exception Copilot</h1>'
    '<div class="sub">Synthetic prototype · Not production-certified · Not HIPAA/NAIC certified · All data synthetic</div>'
    '</div><span class="tag">Medical Professional Liability · Demo</span></div>', unsafe_allow_html=True)

with st.sidebar:
    st.markdown('<div class="colhead">Reviewer session</div>', unsafe_allow_html=True)
    reviewer_id = st.text_input("Reviewer ID", value="uw.demo")
    reviewer_role = st.selectbox("Role", ["underwriter", "senior_underwriter"])
    mode_label = st.selectbox("Generation mode", list(MODE_MAP), index=0)
    st.markdown('<div class="sec">Model status</div>', unsafe_allow_html=True)
    if llm.llm_available():
        st.markdown(f'<div class="banner ok">● Live model available · {e(llm.model_name())}</div>', unsafe_allow_html=True)
    else:
        st.markdown('<div class="banner warn">● Live model unavailable — cached outputs only</div>', unsafe_allow_html=True)
    st.markdown('<div class="muted" style="margin-top:14px">Decisions are made by humans. AI drafts are advisory, '
                'runtime-validated, and every action is checked by a backend policy gate and audited.</div>',
                unsafe_allow_html=True)

queue = service.list_queue(conn)
if "sid" not in st.session_state:
    st.session_state.sid = queue[0]["submission_id"] if queue else None
sid = st.session_state.sid

tab_ws, tab_gov = st.tabs(["Workspace", "Governance"])

# =========================================================================== WORKSPACE
with tab_ws:
    left, center, right = st.columns([1.0, 2.1, 1.35], gap="medium")

    # ---------------- LEFT: queue
    with left:
        st.markdown('<div class="colhead">Exception queue</div>', unsafe_allow_html=True)
        for q in queue:
            pr = q["priority"]
            prk = {"HIGH": "bad", "MEDIUM": "warn"}.get(pr, "ok")
            codes = "".join(pill(c) for c in q["exceptions"]) or pill("No exceptions", "ok")
            sel = " sel" if q["submission_id"] == sid else ""
            st.markdown(
                f'<div class="card{sel}"><div style="display:flex;justify-content:space-between;align-items:center">'
                f'<h4>{e(q["submission_id"])}</h4>{pill(pr if pr != "NONE" else "LOW", prk)}</div>'
                f'<div class="muted">{e(q["specialty"])}</div><div style="margin:6px 0">{codes}</div>'
                f'<div class="muted">Status: <b>{e(q["status"])}</b> · Evidence {e(q["completeness"])}</div></div>',
                unsafe_allow_html=True)
            if st.button("Open case" if not sel else "Selected ✓", key=f"open_{q['submission_id']}",
                         use_container_width=True, type="primary" if sel else "secondary"):
                st.session_state.sid = q["submission_id"]
                st.session_state.pop("cite", None)
                st.rerun()

    if not sid:
        st.stop()
    case = service.open_case(conn, sid, reviewer_role)
    bundle = case["bundle"]
    passages = {p["passage_id"]: p for p in bundle["passages"]}
    docs = {d["document_id"]: d for d in bundle["documents"]}
    brief = case["edited_brief"] or case["generated_brief"]
    gen_brief = case["generated_brief"]

    # ---------------- CENTER: evidence & brief
    with center:
        sub = bundle["submission"]
        st.markdown(f'<div class="colhead">Evidence &amp; brief — {e(sid)}</div>', unsafe_allow_html=True)
        st.markdown(f'<div class="muted">{e(sub["physician_name"])} · {e(sub["specialty"])} · '
                    f'{e(sub["practice_location"])} · submitted {e(fmt_ts(sub["submitted_at"]))}</div>',
                    unsafe_allow_html=True)

        c1, c2 = st.columns([1.1, 1])
        with c1:
            st.markdown('<div class="sec">Detected reason codes</div>', unsafe_allow_html=True)
            if case["exceptions"]:
                for x in case["exceptions"]:
                    extra = f' · claim {e(x["claim_id"])}' if x.get("claim_id") else ""
                    vr = pill("Verification required", "warn") if x.get("verification_required") else ""
                    st.markdown(f'<div class="card det">{pill(x["reason_code"], "dark")}{pill(x["severity"], "bad" if x["severity"] == "HIGH" else "warn")}{vr}'
                                f'<div class="muted" style="margin-top:4px">Deterministic rule — not LLM{extra}</div></div>',
                                unsafe_allow_html=True)
            else:
                st.markdown('<div class="card det">No exceptions detected<div class="muted">Deterministic rule — not LLM</div></div>',
                            unsafe_allow_html=True)
        with c2:
            comp = case["completeness"]
            pct = int(100 * comp["present"] / max(comp["required"], 1))
            items = "".join(
                f'<div class="chk"><span class="{"y" if i["present"] else "n"}">{"✓" if i["present"] else "✗"}</span> '
                f'{e(i["item"].replace("_", " "))}</div>' for i in comp["items"])
            st.markdown('<div class="sec">Evidence completeness</div>'
                        f'<div class="card"><b style="font-size:1.1rem">{comp["present"]} of {comp["required"]}</b> '
                        f'<span class="muted">required items present</span><div class="meter"><div style="width:{pct}%"></div></div>'
                        f'{items}<div class="muted" style="margin-top:4px">Computed by app logic, not the LLM.</div></div>',
                        unsafe_allow_html=True)

        g1, g2 = st.columns([1, 2])
        with g1:
            if st.button("Generate brief", type="primary", use_container_width=True):
                with st.spinner("Generating and validating brief…"):
                    service.generate_brief(conn, sid, mode=MODE_MAP[mode_label])
                st.session_state.pop("cite", None)
                st.rerun()
        with g2:
            st.markdown(f'<div class="muted" style="padding-top:8px">Mode: <b>{e(mode_label)}</b>. '
                        'Output is schema-checked, citation-checked and policy-checked before display.</div>',
                        unsafe_allow_html=True)

        if not brief:
            st.markdown('<div class="banner info">No brief yet. Generate an AI draft to summarise evidence.</div>',
                        unsafe_allow_html=True)
        else:
            val = brief.get("validation") or {}
            # Generation label (always shown)
            g = gen_brief or brief
            if g["generation_mode"] == "live":
                glabel = f'LIVE · {g["model_version"]} · generated {fmt_ts(val.get("generated_at") or g["created_at"])}'
                gk = "ok"
            else:
                glabel = (f'CACHED · {g["model_version"]} · cached {fmt_ts(val.get("cached_at"))} '
                          '— not a fresh model execution')
                gk = "info"
            st.markdown(f'<div class="banner {gk}">{e(glabel)} · prompt {e(g["prompt_version"])}</div>',
                        unsafe_allow_html=True)
            if val.get("note") and g["generation_mode"] != "live":
                st.caption(val["note"])
            vs = (gen_brief or brief)["validation_status"]
            if vs == "VALIDATED":
                st.markdown('<div class="banner ok">VALIDATED · citations, facts and actions passed runtime checks</div>',
                            unsafe_allow_html=True)
            elif vs == "FLAGGED":
                st.markdown('<div class="banner warn">FLAGGED · some items failed checks and were removed or flagged — review issues</div>',
                            unsafe_allow_html=True)
            else:
                st.markdown(f'<div class="banner bad">FAILED · Not validated — do not rely on this draft</div>',
                            unsafe_allow_html=True)
            if case["edited_brief"]:
                st.markdown(f'<div class="banner info">Showing human-edited version (brief #{brief["brief_id"]}) by '
                            f'{e(brief["created_by"])}. Original AI draft preserved in Governance → Audit.</div>',
                            unsafe_allow_html=True)

            rm, vm = val.get("raw_metrics") or {}, val.get("validated_metrics") or {}
            if rm:
                st.markdown('<div class="sec">Raw model output vs validated output</div>', unsafe_allow_html=True)
                mc = st.columns(4)
                for col, k in zip(mc, ["items", "citation_errors", "unsupported", "policy_errors"]):
                    col.metric(k.replace("_", " ").capitalize(), vm.get(k, 0),
                               delta=f"raw {rm.get(k, 0)}", delta_color="off")

            support = {f["path"]: f for f in val.get("fact_support") or []}

            def cite_buttons(ids, key):
                cols = st.columns(min(len(ids), 4) or 1)
                for i, pid in enumerate(ids):
                    if cols[i % len(cols)].button(f"📄 {pid}", key=f"{key}_{pid}_{i}"):
                        st.session_state.cite = pid

            def ai_box(body):
                st.markdown(f'<div class="ai"><div class="lbl">AI DRAFT · ADVISORY</div>{body}</div>',
                            unsafe_allow_html=True)

            st.markdown('<div class="sec">Known facts</div>', unsafe_allow_html=True)
            for i, k in enumerate(brief.get("known") or []):
                fs = support.get(f"known[{i}]")
                sp = ""
                if fs:
                    sk = {"SUPPORTED": "ok", "UNSUPPORTED": "bad"}.get(fs["status"], "warn")
                    sp = f'{pill(fs["status"], sk)}<span class="muted">{e(fs.get("reason", ""))}</span>'
                ai_box(f'<div>{e(k.get("fact", ""))}</div>'
                       f'<div class="muted" style="margin:4px 0">“{e(k.get("quote", ""))}”</div>{sp}')
                cite_buttons(k.get("evidence_ids") or [], f"k{i}")
            if not brief.get("known"):
                st.caption("No validated facts.")

            st.markdown('<div class="sec">Conflicts</div>', unsafe_allow_html=True)
            for i, c in enumerate(brief.get("conflicts") or []):
                vr = pill("Verification required", "warn") if c.get("verification_required") else ""
                ai_box(f'<div>{e(c.get("description", ""))}</div>{vr}')
                cite_buttons(c.get("evidence_ids") or [], f"c{i}")
            if not brief.get("conflicts"):
                st.caption("No conflicts reported.")

            st.markdown('<div class="sec">Missing information</div>', unsafe_allow_html=True)
            for m in brief.get("missing") or []:
                ai_box(f'<b>{e(m.get("field", "").replace("_", " "))}</b><div class="muted">{e(m.get("reason", ""))}</div>')
            if not brief.get("missing"):
                st.caption("Nothing reported missing.")

            st.markdown('<div class="sec">Suggested next steps</div>', unsafe_allow_html=True)
            for n in brief.get("next_steps") or []:
                ai_box(f'{pill(ACTION_LABEL.get(n.get("action"), n.get("action")), "ai")}'
                       f'<div class="muted">{e(n.get("reason", ""))}</div>')
            if not brief.get("next_steps"):
                st.caption("No next steps suggested.")

            # Citation viewer
            pid = st.session_state.get("cite")
            if pid:
                p = passages.get(pid)
                st.markdown('<div class="sec">Source evidence</div>', unsafe_allow_html=True)
                if not p:
                    st.markdown(f'<div class="banner bad">Citation {e(pid)} not found in evidence bundle</div>',
                                unsafe_allow_html=True)
                else:
                    d = docs.get(p["document_id"], {})
                    content = d.get("content", "")
                    s0, s1 = p["start_offset"], p["end_offset"]
                    hl = e(content[:s0]) + "<mark>" + e(content[s0:s1]) + "</mark>" + e(content[s1:])
                    st.markdown(
                        f'<div class="card"><div style="display:flex;justify-content:space-between">'
                        f'<b>{e(d.get("title", ""))}</b><span>{pill(pid, "dark")}</span></div>'
                        f'<div class="muted" style="margin:4px 0 8px">Document {e(p["document_id"])} · version '
                        f'{p["document_version"]} · page {p["page"]} · chars {s0}–{s1}</div>'
                        f'<div class="doc">{hl}</div></div>', unsafe_allow_html=True)
                    if st.button("Close source", key="close_cite"):
                        st.session_state.pop("cite", None)
                        st.rerun()

            issues = val.get("issues") or []
            with st.expander(f"Validation issues ({len(issues)})"):
                if issues:
                    st.dataframe(pd.DataFrame(issues), hide_index=True, use_container_width=True)
                else:
                    st.write("No issues found.")
                if val.get("schema_errors"):
                    st.write("Schema errors:", val["schema_errors"])
                if val.get("attempts"):
                    st.caption("Attempts: " + ", ".join(
                        f'#{a["attempt"]} {a["mode"]} schema_ok={a["schema_ok"]}' for a in val["attempts"]))

            with st.expander("Edit brief (human edit is stored as a new version; original is preserved)"):
                with st.form(f"edit_{brief['brief_id']}"):
                    texts = {}
                    for sec in ("known", "conflicts", "missing", "next_steps"):
                        texts[sec] = st.text_area(sec.replace("_", " ").capitalize() + " (JSON)",
                                                  json.dumps(brief.get(sec) or [], indent=2), height=140)
                    reason = st.text_input("Reason for edit (required)")
                    if st.form_submit_button("Save edit", type="primary"):
                        try:
                            edited = {k: json.loads(v) for k, v in texts.items()}
                            if not reason.strip():
                                st.error("A reason is required for edits.")
                            else:
                                service.save_edit(conn, sid, brief["brief_id"], edited, reviewer_id, reason)
                                st.success("Edit saved as new version.")
                                st.rerun()
                        except json.JSONDecodeError as ex:
                            st.error(f"Invalid JSON: {ex}")

    # ---------------- RIGHT: human decision
    with right:
        st.markdown('<div class="colhead">Human decision</div>', unsafe_allow_html=True)
        st.markdown('<div class="sec">Triggered playbook rules</div>', unsafe_allow_html=True)
        if not case["rules"]:
            st.markdown('<div class="card muted">No playbook rules triggered.</div>', unsafe_allow_html=True)
        for r in case["rules"]:
            acts = "".join(pill(ACTION_LABEL.get(a, a), "ok") for a in r["permitted_actions"])
            ev = ", ".join(x.replace("_", " ") for x in r["required_evidence"])
            role = f'<div class="muted">Required role: {e(r["required_role"])}</div>' if r.get("required_role") else ""
            final = pill("Final decision blocked", "bad") if not r.get("final_decision_allowed") else ""
            st.markdown(f'<div class="card det"><div style="display:flex;justify-content:space-between">'
                        f'<b>{e(r["rule_id"])}</b>{pill("v" + r["version"], "dark")}</div>'
                        f'<div style="font-size:.85rem;margin:4px 0">{e(r["title"])}</div>'
                        f'<div class="muted">Permitted:</div>{acts}{final}'
                        f'<div class="muted" style="margin-top:4px">Required evidence: {e(ev)}</div>{role}</div>',
                        unsafe_allow_html=True)

        st.markdown('<div class="sec">Action</div>', unsafe_allow_html=True)
        acts = case["actions"]
        allowed = [a for a in ACTIONS if acts[a]["allowed"]]
        for a in ACTIONS:
            if not acts[a]["allowed"]:
                st.markdown(f'<div class="blocked">🔒 <b>{ACTION_LABEL[a]}</b> — blocked<br>{e(acts[a]["reason"])}</div>',
                            unsafe_allow_html=True)
        choice = st.radio("Permitted actions", allowed, format_func=lambda a: ACTION_LABEL[a],
                          key=f"act_{sid}") if allowed else None
        rationale = st.text_area("Rationale (mandatory)", key=f"rat_{sid}", height=90,
                                 placeholder="Explain the decision with reference to the evidence…")
        if st.button("Submit decision", type="primary", use_container_width=True, disabled=not choice):
            try:
                did = service.record_decision(conn, sid, choice, rationale, reviewer_id, reviewer_role,
                                              presented_rule_versions=case["rule_versions"])
                st.session_state.flash = ("ok", f"Decision #{did} recorded: {ACTION_LABEL[choice]}")
                st.rerun()
            except policy.PolicyViolation as ex:
                st.error(f"Blocked by backend policy gate: {ex.reason}")
            except ValueError as ex:
                st.error(str(ex))
        flash = st.session_state.pop("flash", None)
        if flash:
            st.success(flash[1])

        with st.expander("Test backend gate (bypass UI)"):
            st.caption("Attempts APPROVE directly against the backend, as if the UI were bypassed.")
            if st.button("Attempt APPROVE via API", key="gate"):
                try:
                    service.record_decision(conn, sid, "APPROVE", "Gate test: direct API approval attempt",
                                            reviewer_id, reviewer_role, presented_rule_versions=case["rule_versions"])
                    st.warning("Backend accepted APPROVE (no blocking rules apply to this case).")
                except policy.PolicyViolation as ex:
                    st.markdown(f'<div class="banner bad">Backend blocked APPROVE: {e(ex.reason)}</div>',
                                unsafe_allow_html=True)
                    st.caption("The blocked attempt was written to the audit log.")

        st.markdown('<div class="sec">Recorded decisions</div>', unsafe_allow_html=True)
        decs = case["decisions"]
        if not decs:
            st.caption("No decision recorded yet.")
        for d in reversed(decs):
            st.markdown(f'<div class="card">{pill(ACTION_LABEL.get(d["action"], d["action"]), "dark")}'
                        f'<span class="muted">{e(d["reviewer_id"])} ({e(d["reviewer_role"])}) · {e(fmt_ts(d["created_at"]))}</span>'
                        f'<div style="font-size:.82rem;margin-top:4px">{e(d["rationale"])}</div>'
                        f'<div class="muted">Rules {e(d["rule_versions_json"])} · model {e(str(d["model_version"]))}</div></div>',
                        unsafe_allow_html=True)

        st.markdown('<div class="sec">Audit timeline</div>', unsafe_allow_html=True)
        evs = case["audit"][-10:]
        rows = "".join(
            f'<div class="ev {"bad" if "BLOCK" in a["event_type"] or "FAIL" in a["event_type"] else ("ok" if "DECISION" in a["event_type"] else "")}">'
            f'<b>{e(a["event_type"])}</b> · {e(a["actor"])}<br><span class="muted">{e(fmt_ts(a["timestamp"]))}'
            f'{(" · " + e(a["reason"][:90])) if a.get("reason") else ""}</span></div>' for a in reversed(evs))
        st.markdown(f'<div class="tl">{rows or "<span class=muted>No events</span>"}</div>', unsafe_allow_html=True)

# =========================================================================== GOVERNANCE
with tab_gov:
    st.markdown('<div class="banner info">Governance view · Synthetic evaluation — not a production certification</div>',
                unsafe_allow_html=True)
    sec_e, sec_p, sec_v, sec_a = st.tabs(["Evals", "Playbook", "Provenance", "Audit"])

    with sec_e:
        run = conn.execute("SELECT * FROM evaluation_runs ORDER BY run_id DESC LIMIT 1").fetchone()
        if not run:
            st.info("No evaluation run found. Run `python -m evals.run_evals` to populate results.")
        else:
            run = dict(run)
            st.markdown(f'<div class="card">{pill("Run #" + str(run["run_id"]), "dark")}{pill(run["status"] or "", "ok")}'
                        f'<div class="muted" style="margin-top:6px">Dataset {e(str(run["dataset_version"]))} · model '
                        f'{e(str(run["model_version"]))} · prompt {e(str(run["prompt_version"]))} · rules {e(str(run["rule_version"]))}'
                        f' · completed {e(fmt_ts(run["completed_at"]))}</div>'
                        '<div class="muted"><b>Synthetic evaluation — not a production certification</b></div></div>',
                        unsafe_allow_html=True)
            res = pd.read_sql_query("SELECT eval_case_id,metric_name,observed_value,threshold,passed,failure_reason,stage "
                                    "FROM evaluation_results WHERE run_id=?", conn, params=(run["run_id"],))
            if res.empty:
                st.caption("No results in this run.")
            else:
                res["stage"] = res["stage"].fillna("validated")
                summ = res.groupby(["stage", "metric_name"]).agg(
                    mean=("observed_value", "mean"), threshold=("threshold", "first"),
                    pass_rate=("passed", "mean"), n=("passed", "size")).reset_index()
                stages = list(summ["stage"].unique())
                cols = st.columns(max(len(stages), 1))
                for col, stg in zip(cols, stages):
                    with col:
                        st.markdown(f'<div class="sec">{e(str(stg))} output</div>', unsafe_allow_html=True)
                        st.dataframe(summ[summ.stage == stg].drop(columns="stage"), hide_index=True,
                                     use_container_width=True)
                with st.expander("All evaluation results"):
                    st.dataframe(res, hide_index=True, use_container_width=True)

    with sec_p:
        pb = policy.load_playbook()
        st.markdown(f'<div class="card">{pill("Playbook v" + str(pb.get("playbook_version")), "dark")}'
                    f'<span class="muted">{e(pb.get("label", ""))}</span></div>', unsafe_allow_html=True)
        st.dataframe(pd.DataFrame([{
            "rule_id": r["rule_id"], "version": r["version"], "effective_date": r["effective_date"],
            "trigger": r["trigger"], "title": r["title"], "permitted_actions": ", ".join(r["permitted_actions"]),
            "final_decision_allowed": r["final_decision_allowed"], "required_role": r.get("required_role") or "—",
            "required_evidence": ", ".join(r["required_evidence"])} for r in pb["rules"]]),
            hide_index=True, use_container_width=True)

    with sec_v:
        st.markdown(f'<div class="sec">Case {e(sid)}</div>', unsafe_allow_html=True)
        pc = st.columns(4)
        g = gen_brief
        pc[0].metric("Model", g["model_version"] if g else "—")
        pc[1].metric("Prompt version", g["prompt_version"] if g else "—")
        pc[2].metric("Generation", (g["generation_mode"].upper() if g else "—"))
        pc[3].metric("Playbook", "v" + str(case["playbook_version"]))
        if g:
            st.caption("CACHED output is a stored prior model response, not a fresh execution."
                       if g["generation_mode"] == "cached" else "LIVE output from a fresh model call.")
        st.markdown('<div class="sec">Rule versions presented</div>', unsafe_allow_html=True)
        st.write(" ".join(f'{pill(k + " v" + v, "dark")}' for k, v in case["rule_versions"].items()) or "None",
                 unsafe_allow_html=True)
        st.markdown('<div class="sec">Evidence documents</div>', unsafe_allow_html=True)
        st.dataframe(pd.DataFrame([{k: d[k] for k in ("document_id", "document_type", "title", "version", "created_at")}
                                   for d in bundle["documents"]]), hide_index=True, use_container_width=True)
        briefs = pd.read_sql_query("SELECT brief_id,kind,parent_brief_id,generation_mode,model_version,prompt_version,"
                                   "validation_status,created_by,created_at FROM exception_briefs WHERE submission_id=? "
                                   "ORDER BY brief_id DESC", conn, params=(sid,))
        st.markdown('<div class="sec">Brief versions</div>', unsafe_allow_html=True)
        st.dataframe(briefs, hide_index=True, use_container_width=True)

    with sec_a:
        st.markdown(f'<div class="sec">Original AI brief vs human-edited brief — {e(sid)}</div>', unsafe_allow_html=True)
        ga, gb = st.columns(2)
        def brief_view(b):
            return {k: b.get(k) for k in ("known", "conflicts", "missing", "next_steps")} if b else None
        with ga:
            st.markdown(f'<div class="ai"><div class="lbl">ORIGINAL AI DRAFT'
                        f'{" · #" + str(gen_brief["brief_id"]) if gen_brief else ""}</div></div>', unsafe_allow_html=True)
            st.json(brief_view(gen_brief) or {"note": "no generated brief"}, expanded=False)
        with gb:
            eb = case["edited_brief"]
            st.markdown(f'<div class="card det"><b>HUMAN-EDITED</b>'
                        f'{" · #" + str(eb["brief_id"]) + " by " + e(eb["created_by"]) if eb else ""}</div>',
                        unsafe_allow_html=True)
            st.json(brief_view(eb) or {"note": "no human edit"}, expanded=False)
        if gen_brief and case["edited_brief"]:
            diffs = []
            for k in ("known", "conflicts", "missing", "next_steps"):
                a, b = gen_brief.get(k) or [], case["edited_brief"].get(k) or []
                if a != b:
                    diffs.append({"section": k, "ai_items": len(a), "edited_items": len(b),
                                  "removed": len([x for x in a if x not in b]), "added": len([x for x in b if x not in a])})
            st.dataframe(pd.DataFrame(diffs or [{"section": "—", "note": "No differences"}]), hide_index=True,
                         use_container_width=True)
        st.markdown('<div class="sec">Decision rationales</div>', unsafe_allow_html=True)
        st.dataframe(pd.DataFrame(case["decisions"]) if case["decisions"] else pd.DataFrame([{"note": "No decisions"}]),
                     hide_index=True, use_container_width=True)
        st.markdown('<div class="sec">Audit events (append-only)</div>', unsafe_allow_html=True)
        ad = pd.DataFrame([{**a, "before": json.dumps(a["before"]) if a["before"] else "",
                            "after": json.dumps(a["after"]) if a["after"] else ""} for a in case["audit"]])
        st.dataframe(ad, hide_index=True, use_container_width=True)
