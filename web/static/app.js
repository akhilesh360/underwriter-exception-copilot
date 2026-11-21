/* Underwriter Exception Copilot — workspace front end (vanilla JS). */
(function () {
  "use strict";

  const $ = (s, r = document) => r.querySelector(s);
  const esc = (s) => String(s == null ? "" : s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

  async function api(path, opts = {}) {
    const init = { method: opts.method || (opts.body !== undefined ? "POST" : "GET"), headers: {} };
    if (opts.body !== undefined) { init.headers["Content-Type"] = "application/json"; init.body = typeof opts.body === "string" ? opts.body : JSON.stringify(opts.body); }
    try {
      const r = await fetch(path, init);
      let data = null;
      try { data = await r.json(); } catch (e) { data = null; }
      return { ok: r.ok, status: r.status, data };
    } catch (e) {
      return { ok: false, status: 0, data: { detail: String(e) } };
    }
  }

  const state = { selectedId: null, reviewerId: "uw.demo", role: "underwriter", mode: "auto", caseData: null, queue: [], status: null,
    generating: false, editing: false, showOriginal: false, selectedAction: null, decisionError: null, gateResult: null };
  window.UEC = { api, state, esc };

  /* ---------- helpers ---------- */
  const ICON = {
    lock: '<svg class="lock" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.6"><rect x="3" y="7" width="10" height="7" rx="1.5"/><path d="M5.5 7V5a2.5 2.5 0 015 0v2"/></svg>',
    doc: '<svg viewBox="0 0 12 12" fill="none" stroke="currentColor" stroke-width="1.3"><path d="M3 1h4l2 2v8H3z"/><path d="M7 1v2h2"/></svg>',
    cog: '<svg viewBox="0 0 12 12" fill="none" stroke="currentColor" stroke-width="1.3"><circle cx="6" cy="6" r="2"/><path d="M6 1v1.5M6 9.5V11M1 6h1.5M9.5 6H11M2.5 2.5l1 1M8.5 8.5l1 1M2.5 9.5l1-1M8.5 3.5l1-1"/></svg>',
    spark: '<svg viewBox="0 0 12 12" width="11" height="11" fill="currentColor"><path d="M6 0l1.4 4.6L12 6l-4.6 1.4L6 12 4.6 7.4 0 6l4.6-1.4z"/></svg>',
  };
  const fmtTime = (t) => { if (!t) return "—"; const d = new Date(t); if (isNaN(d)) return esc(t); return d.toLocaleString(undefined, { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" }); };
  const human = (s) => String(s || "").replace(/_/g, " ").toLowerCase().replace(/^\w/, (c) => c.toUpperCase());
  const actionLabel = { APPROVE: "Approve", DECLINE: "Decline", REQUEST_INFORMATION: "Request information", REFER: "Refer to senior underwriter", ESCALATE: "Escalate" };
  const priorityPill = (p) => p === "HIGH" ? "pill-danger" : p === "MEDIUM" ? "pill-warning" : "pill-neutral";
  function statusPill(s) {
    s = s || "";
    if (s.startsWith("DECIDED")) return `<span class="pill pill-success">${esc(human(s.split(":")[1] || "Decided"))}</span>`;
    if (s === "FLAGGED") return '<span class="pill pill-warning">Flagged</span>';
    return `<span class="pill pill-neutral">${esc(human(s))}</span>`;
  }
  function toast(msg, err) {
    const t = document.createElement("div");
    t.className = "toast" + (err ? " err" : "");
    t.innerHTML = (err ? "" : '<span class="tick">✓</span>') + esc(msg);
    $("#toasts").appendChild(t);
    setTimeout(() => t.remove(), 3800);
  }

  /* ---------- status + queue ---------- */
  async function loadStatus() {
    const r = await api("/api/status");
    const el = $("#llm-status");
    state.status = r.data;
    if (r.ok && r.data.llm_available) { el.className = "llm-status ok"; $(".txt", el).textContent = "AI live"; el.title = `prompt ${r.data.prompt_version}`; }
    else { el.className = "llm-status off"; $(".txt", el).textContent = "Offline – cached only"; }
  }
  async function loadQueue() {
    const r = await api("/api/queue");
    state.queue = r.ok ? r.data : [];
    renderQueue();
  }
  function renderQueue() {
    $("#queue-count").textContent = `${state.queue.length} open`;
    if (!state.queue.length) { $("#queue").innerHTML = '<div class="card empty">No exceptions in queue.</div>'; return; }
    $("#queue").innerHTML = state.queue.map((q) => {
      const [p, t] = String(q.completeness || "0/1").split("/").map(Number);
      const codes = q.exceptions.length ? q.exceptions.map((c) => `<span class="pill pill-code">${esc(c)}</span>`).join("") : '<span class="pill pill-neutral">No exceptions</span>';
      return `<button class="q-item ${q.submission_id === state.selectedId ? "selected" : ""}" data-id="${esc(q.submission_id)}">
        <div class="q-top"><span class="q-id">${esc(q.submission_id)}</span>${q.priority !== "NONE" ? `<span class="pill ${priorityPill(q.priority)}">${esc(human(q.priority))} priority</span>` : '<span class="pill pill-neutral">Routine</span>'}</div>
        <div class="q-spec">${esc(q.specialty)}</div>
        <div class="q-codes">${codes}</div>
        <div class="q-foot">${statusPill(q.status)}<span class="mini"><span class="mini-bar"><i style="width:${t ? (p / t) * 100 : 0}%"></i></span>${esc(q.completeness)}</span></div>
      </button>`;
    }).join("");
    document.querySelectorAll(".q-item").forEach((b) => b.addEventListener("click", () => selectCase(b.dataset.id)));
  }

  /* ---------- case ---------- */
  async function selectCase(id) {
    if (state.selectedId !== id) { state.editing = false; state.showOriginal = false; state.selectedAction = null; state.decisionError = null; state.gateResult = null; }
    state.selectedId = id;
    renderQueue();
    if (!state.caseData || state.caseData.bundle.submission.submission_id !== id) {
      $("#center").innerHTML = '<div class="card card-body"><div class="skeleton" style="width:40%"></div><div class="skeleton"></div><div class="skeleton" style="width:70%"></div></div>';
    }
    await refreshCase();
  }
  async function refreshCase() {
    const r = await api(`/api/cases/${encodeURIComponent(state.selectedId)}?role=${encodeURIComponent(state.role)}`);
    if (!r.ok) { $("#center").innerHTML = `<div class="card empty"><h4>Could not load case</h4>${esc((r.data && r.data.detail) || r.status)}</div>`; $("#right").innerHTML = ""; return; }
    state.caseData = r.data;
    renderCenter(); renderRight();
  }

  function renderCenter() {
    const c = state.caseData, s = c.bundle.submission, comp = c.completeness;
    const pct = comp.required ? (comp.present / comp.required) * 100 : 0;
    const excHtml = c.exceptions.length ? c.exceptions.map((e) => `
      <div class="exc"><span class="pill pill-code">${esc(e.reason_code)}</span>
        <div><div class="exc-detail">${e.claim_id ? `Claim <span class="mono">${esc(e.claim_id)}</span> · ` : ""}Severity ${esc(human(e.severity || "—"))}</div>
        ${e.verification_required ? '<span class="pill pill-warning" style="margin-top:4px">Verification required</span>' : ""}</div></div>`).join("")
      : '<div class="muted">No exceptions detected for this submission.</div>';
    $("#center").innerHTML = `
      <div class="card"><div class="case-head">
        <div><div class="caption">Submission</div><div class="case-id">${esc(s.submission_id)}</div>
          <div class="case-meta"><span><b>${esc(s.physician_name)}</b></span><span>${esc(s.specialty)}</span><span>${esc(s.practice_location)}</span><span class="mono">${esc(s.synthetic_npi)}</span></div></div>
        <div style="display:flex;flex-direction:column;align-items:flex-end;gap:6px">${statusPill(s.status)}<div class="caption">Submitted ${fmtTime(s.submitted_at)}</div></div>
      </div></div>
      <div class="grid2">
        <div class="card"><div class="card-header stack"><h3>Detected exceptions</h3><span class="caption">${ICON.cog} Deterministic rule · not LLM</span></div>
          <div class="card-body">${excHtml}</div></div>
        <div class="card"><div class="card-header stack"><h3>Evidence completeness</h3><span class="caption">${ICON.cog} Calculated by application logic — not the model</span></div>
          <div class="card-body"><div><span class="big-num">${comp.present} of ${comp.required}</span> <span class="muted">required items</span></div>
          <div class="progress"><i style="width:${pct}%"></i></div>
          <ul class="checklist">${comp.items.map((i) => `<li><span class="ck ${i.present ? "yes" : "no"}">${i.present ? "✓" : "✗"}</span>${esc(human(i.item))}<span class="src">${i.source ? esc(i.source) : "missing"}</span></li>`).join("")}</ul></div></div>
      </div>
      <div id="brief-card"></div>`;
    renderBrief();
  }

  /* ---------- brief ---------- */
  function renderBrief() {
    const host = $("#brief-card"), c = state.caseData;
    const gen = c.generated_brief, edit = c.edited_brief;
    if (state.generating) {
      host.innerHTML = `<div class="card brief"><div class="card-header"><h3>Exception brief</h3><span class="pill pill-ai">${ICON.spark} AI draft</span></div>
        <div class="empty"><div class="ill"><span class="spinner dark"></span></div><h4>Generating brief…</h4><div>${state.mode === "cached" ? "Loading cached output" : "Live model calls typically take ~10 seconds"}. Output is validated against source passages before display.</div>
        <div style="max-width:420px;margin:14px auto 0"><div class="skeleton"></div><div class="skeleton" style="width:80%"></div><div class="skeleton" style="width:60%"></div></div></div></div>`;
      return;
    }
    if (!gen) {
      host.innerHTML = `<div class="card brief"><div class="card-header"><h3>Exception brief</h3><span class="pill pill-ai">${ICON.spark} AI draft</span></div>
        <div class="empty"><div class="ill">${ICON.spark}</div><h4>No brief generated yet</h4><div style="max-width:460px;margin:0 auto 14px">The copilot drafts a cited summary of known facts, conflicts and missing evidence. Every citation is checked against the source document before you see it.</div>
        <button class="btn btn-primary" id="gen-btn">Generate brief</button><div class="caption" style="margin-top:10px;justify-content:center;display:flex">Mode: ${esc($("#mode").selectedOptions[0].textContent)}</div></div></div>`;
      $("#gen-btn").onclick = generate;
      return;
    }
    const useEdit = edit && !state.showOriginal;
    const b = useEdit ? edit : gen;
    const v = gen.validation || {};
    const status = gen.validation_status || v.status;

    // provenance
    let prov;
    if (useEdit) prov = `<div class="prov human"><b>Human-edited version</b><span class="sep">·</span>Edited by ${esc(edit.created_by)} · ${fmtTime(edit.created_at)}<span class="sep">·</span>Based on AI draft #${esc(edit.parent_brief_id)} (${esc(gen.model_version)}, original preserved)</div>`;
    else if (gen.generation_mode === "cached") prov = `<div class="prov cached"><b>Cached output</b><span class="sep">·</span>${esc(gen.model_version)} · ${esc(gen.prompt_version)}<span class="sep">·</span>cached ${fmtTime(v.cached_at || gen.created_at)} — not a fresh model execution</div>`;
    else prov = `<div class="prov live"><b>Live</b><span class="sep">·</span>${esc(gen.model_version)} · ${esc(gen.prompt_version)}<span class="sep">·</span>generated ${fmtTime(v.generated_at || gen.created_at)}</div>`;

    const vPill = status === "VALIDATED" ? '<span class="pill pill-success">Validated</span>' : status === "FLAGGED" ? '<span class="pill pill-warning">Flagged</span>' : '<span class="pill pill-danger">Failed</span>';
    const failAlert = status === "FAILED" ? '<div style="padding:12px 18px 0"><div class="alert alert-danger"><b>Not validated — do not rely on this draft.</b> Review the validation details below.</div></div>'
      : status === "FLAGGED" ? '<div style="padding:12px 18px 0"><div class="alert alert-warning">Some items were flagged or removed by validation. Check validation details before relying on this draft.</div></div>' : "";

    const raw = v.raw_brief || {};
    const support = {};
    (v.fact_support || []).forEach((f) => (support[f.path] = f));
    const rawPath = (sec, item, i) => { const arr = raw[sec] || []; const key = sec === "known" ? "fact" : "description"; const j = arr.findIndex((x) => x[key] === item[key]); return `${sec}[${j >= 0 ? j : i}]`; };
    const cites = (ids, sec, item, i) => (ids || []).map((id) => `<button class="cite" data-eid="${esc(id)}" data-path="${esc(rawPath(sec, item, i))}" data-quote="${esc(item.quote || "")}">${ICON.doc}${esc(id)}</button>`).join("");
    const ed = state.editing;
    const ta = (sec, i, k, val) => `<textarea data-sec="${sec}" data-i="${i}" data-k="${k}" rows="2">${esc(val)}</textarea>`;
    const supPill = (f) => !f ? "" : f.status === "SUPPORTED" ? `<span class="pill pill-success" title="${esc(f.reason)}">Supported</span>` : f.status === "NEEDS_VERIFICATION" ? `<span class="pill pill-warning" title="${esc(f.reason)}">Needs verification</span>` : `<span class="pill pill-danger" title="${esc(f.reason)}">Unsupported</span>`;
    const item = (n, body, meta) => `<div class="bitem"><span class="bnum">${n}</span><div class="bmain">${body}${meta ? `<div class="bmeta">${meta}</div>` : ""}</div></div>`;
    const sec = (title, arr, fn, extra) => `<div class="bsec"><h4>${title} <span class="count">${arr.length}</span>${extra || ""}</h4>${arr.length ? arr.map(fn).join("") : '<div class="muted small">None identified.</div>'}</div>`;

    const known = b.known || [], conf = b.conflicts || [], miss = b.missing || [], steps = b.next_steps || [];
    const body = `
      ${sec("Known facts", known, (k, i) => item(i + 1, ed ? ta("known", i, "fact", k.fact) : `<div class="btext">${esc(k.fact)}</div>`, `${supPill(support[rawPath("known", k, i)])}${cites(k.evidence_ids, "known", k, i)}`))}
      ${sec("Conflicts", conf, (k, i) => item(i + 1, ed ? ta("conflicts", i, "description", k.description) : `<div class="btext">${esc(k.description)}</div>`, `${k.verification_required ? '<span class="pill pill-warning">Verification required</span>' : ""}${cites(k.evidence_ids, "conflicts", k, i)}`))}
      ${sec("Missing information", miss, (k, i) => item(i + 1, `<span class="field-name">${esc(k.field)}</span><div class="btext" style="margin-top:4px">${ed ? ta("missing", i, "reason", k.reason) : esc(k.reason)}</div>`))}
      ${sec("Suggested next steps", steps, (k, i) => item(i + 1, `<span class="pill pill-ai">${esc(actionLabel[k.action] || k.action)}</span><div class="btext" style="margin-top:4px">${ed ? ta("next_steps", i, "reason", k.reason) : esc(k.reason)}</div>`), '<span class="caption" style="margin-left:auto;font-weight:400">Suggestions only — a human makes the decision</span>')}`;

    const issues = v.issues || [];
    const rm = v.raw_metrics || {}, vm = v.validated_metrics || {};
    const mrow = (m) => ["items", "citation_errors", "unsupported", "policy_errors"].map((k) => `<div class="metric-row"><span>${human(k)}</span><b class="${k !== "items" && m[k] ? "bad" : ""}">${m[k] ?? 0}</b></div>`).join("");
    const details = `<details class="vd"><summary>Validation details <span class="pill pill-neutral">${issues.length} issue${issues.length === 1 ? "" : "s"}</span><span class="pill pill-neutral">${(v.attempts || []).length || 1} attempt(s)</span></summary><div class="vd-body">
      ${issues.length ? `<table class="table"><thead><tr><th>Layer</th><th>Code</th><th>Message</th><th>Path</th></tr></thead><tbody>${issues.map((x) => `<tr><td>${esc(x.layer)}</td><td class="mono">${esc(x.code)}</td><td>${esc(x.message)}</td><td class="mono">${esc(x.path)}</td></tr>`).join("")}</tbody></table>` : '<div class="muted small">No issues. Schema (A), citations (B), factual support (C) and policy (D) checks passed.</div>'}
      <div class="metrics"><div class="metric-col"><h5>Raw generation</h5>${mrow(rm)}</div><div class="metric-col"><h5>Validated output</h5>${mrow(vm)}</div></div>
      <div class="note">A clean validated score does not mean the raw model output was error-free.</div></div></details>`;

    const headPills = useEdit ? '<span class="pill pill-human">Human-edited</span>' : `<span class="pill pill-ai">${ICON.spark} AI draft</span>`;
    const toggle = edit ? `<button class="btn btn-ghost btn-sm" id="toggle-orig">${state.showOriginal ? "View current (edited) version" : "View original AI draft"}</button>` : "";
    const foot = ed
      ? `<div class="brief-foot"><input class="input" id="edit-reason" placeholder="Reason for edit (recorded in audit log)" style="flex:1;min-width:220px"><div style="display:flex;gap:8px"><button class="btn btn-secondary" id="edit-cancel">Cancel</button><button class="btn btn-primary" id="edit-save">Save edit</button></div></div>`
      : `<div class="brief-foot"><div>${toggle}</div><div style="display:flex;gap:8px"><button class="btn btn-secondary btn-sm" id="edit-btn">Edit brief</button><button class="btn btn-secondary btn-sm" id="regen-btn">Regenerate</button></div></div>`;

    host.innerHTML = `<div class="card brief ${ed ? "editing" : ""}">
      <div class="card-header"><div style="display:flex;align-items:center;gap:8px"><h3>Exception brief</h3>${headPills}</div><div style="display:flex;gap:6px;align-items:center"><span class="caption">Validation</span>${vPill}</div></div>
      ${prov}${failAlert}${body}${foot}${details}</div>`;

    host.querySelectorAll(".cite").forEach((el) => el.addEventListener("click", () => openCitation(el.dataset.eid, el.dataset.path, el.dataset.quote)));
    const on = (id, fn) => { const e = $("#" + id); if (e) e.onclick = fn; };
    on("regen-btn", generate);
    on("edit-btn", () => { state.editing = true; state.showOriginal = false; renderBrief(); });
    on("edit-cancel", () => { state.editing = false; renderBrief(); });
    on("toggle-orig", () => { state.showOriginal = !state.showOriginal; renderBrief(); });
    on("edit-save", () => saveEdit(b));
  }

  async function generate() {
    state.generating = true; state.editing = false; state.showOriginal = false; renderBrief();
    const t0 = performance.now();
    const r = await api(`/api/cases/${encodeURIComponent(state.selectedId)}/brief`, { body: { mode: state.mode } });
    state.generating = false;
    if (!r.ok) { toast(`Brief generation failed: ${(r.data && r.data.detail) || r.status}`, true); renderBrief(); return; }
    toast(`Brief ${r.data.generation_mode === "cached" ? "loaded from cache" : "generated"} · ${r.data.validation_status} · ${((performance.now() - t0) / 1000).toFixed(1)}s`);
    await refreshCase(); loadQueue();
  }

  async function saveEdit(base) {
    const edited = JSON.parse(JSON.stringify({ known: base.known || [], conflicts: base.conflicts || [], missing: base.missing || [], next_steps: base.next_steps || [] }));
    document.querySelectorAll("#brief-card textarea").forEach((t) => { edited[t.dataset.sec][+t.dataset.i][t.dataset.k] = t.value; });
    const reason = $("#edit-reason").value.trim();
    const parentId = state.caseData.edited_brief ? state.caseData.edited_brief.brief_id : state.caseData.generated_brief.brief_id;
    const r = await api(`/api/cases/${encodeURIComponent(state.selectedId)}/brief/${parentId}/edit`, { body: { edited, reviewer_id: state.reviewerId, reason } });
    if (!r.ok) { toast("Could not save edit", true); return; }
    state.editing = false;
    toast("Edit saved as a new version — original AI draft preserved");
    await refreshCase();
  }

  /* ---------- citation drawer ---------- */
  function openCitation(eid, path, quote) {
    const b = state.caseData.bundle;
    const p = b.passages.find((x) => x.passage_id === eid);
    const d = p && b.documents.find((x) => x.document_id === p.document_id);
    let content;
    if (!p || !d) content = `<div class="alert alert-danger">Evidence ID <span class="mono">${esc(eid)}</span> not found in the case bundle.</div>`;
    else {
      const t = d.content;
      const docHtml = esc(t.slice(0, p.start_offset)) + `<mark id="cited">${esc(t.slice(p.start_offset, p.end_offset))}</mark>` + esc(t.slice(p.end_offset));
      const issues = (state.caseData.generated_brief.validation || {}).issues || [];
      const citeIssue = issues.find((x) => x.path === path && x.layer === "B");
      let qHtml = "";
      if (quote) qHtml = `<div><div class="section-title" style="margin-bottom:6px">Model's quote</div><div class="quote">“${esc(quote)}”</div>
        <div style="margin-top:8px">${citeIssue ? `<span class="unverified">✗ ${esc(citeIssue.code)}: ${esc(citeIssue.message)}</span>` : '<span class="verified">Quote verified against source span ✓</span>'}</div></div>`;
      else qHtml = `<div>${citeIssue ? `<span class="unverified">✗ ${esc(citeIssue.message)}</span>` : '<span class="verified">Evidence ID resolved; passage offsets match document version ✓</span>'}</div>`;
      content = `<dl class="docmeta"><dt>Document</dt><dt>Version</dt><dt>Page</dt><dt>Span</dt>
          <dd>${esc(d.document_id)}</dd><dd>v${esc(d.version)}</dd><dd>${esc(p.page)}</dd><dd>${p.start_offset}–${p.end_offset}</dd></dl>
        <div><div class="section-title" style="margin-bottom:6px">Source document · ${esc(human(d.document_type))}</div><div class="doc">${docHtml}</div></div>${qHtml}`;
    }
    $("#drawer").innerHTML = `<div class="drawer-head"><div><div class="caption">Citation <span class="mono">${esc(eid)}</span></div><h3>${esc(d ? d.title : "Unknown source")}</h3></div><button class="xbtn" id="drawer-close" aria-label="Close">×</button></div><div class="drawer-body">${content}</div>`;
    $("#drawer").classList.add("open"); $("#drawer").setAttribute("aria-hidden", "false"); $("#drawer-backdrop").hidden = false;
    $("#drawer-close").onclick = closeDrawer; $("#drawer-close").focus();
  }
  function closeDrawer() { $("#drawer").classList.remove("open"); $("#drawer").setAttribute("aria-hidden", "true"); $("#drawer-backdrop").hidden = true; }
  $("#drawer-backdrop").addEventListener("click", closeDrawer);
  document.addEventListener("keydown", (e) => { if (e.key === "Escape") closeDrawer(); });

  /* ---------- right pane ---------- */
  function renderRight() {
    const c = state.caseData;
    const rules = c.rules.length ? c.rules.map((r) => `<div class="rule">
        <div class="rule-top"><span class="pill pill-code">${esc(r.rule_id)}</span><span class="pill pill-neutral">v${esc(r.version)}</span>${r.required_role ? `<span class="pill pill-warning">Requires ${esc(human(r.required_role))}</span>` : ""}</div>
        <div class="rule-title">${esc(r.title)}</div>
        <div class="kv">Required evidence<div class="tags">${r.required_evidence.map((x) => `<span class="tag">${esc(x)}</span>`).join("")}</div></div>
        <div class="kv">Permitted actions<div class="tags">${r.permitted_actions.map((x) => `<span class="tag">${esc(x)}</span>`).join("")}</div></div>
        <div class="kv">Trigger <span class="mono">${esc(r.trigger)}</span> · effective ${esc(r.effective_date)}${r.final_decision_allowed ? "" : " · final decision not allowed"}</div></div>`).join("")
      : '<div class="card-body muted small">No playbook rules triggered.</div>';

    const order = ["APPROVE", "DECLINE", "REQUEST_INFORMATION", "REFER", "ESCALATE"];
    const acts = order.filter((a) => c.actions[a]).map((a) => {
      const x = c.actions[a];
      if (!x.allowed) return `<div class="action blocked" aria-disabled="true"><input type="radio" disabled><div><div class="a-name">${ICON.lock}${esc(actionLabel[a])}</div><div class="a-why">${esc(x.reason)}</div></div></div>`;
      return `<label class="action ${state.selectedAction === a ? "checked" : ""}"><input type="radio" name="action" value="${a}" ${state.selectedAction === a ? "checked" : ""}><div><div class="a-name">${esc(actionLabel[a])}</div><div class="a-why">${esc(x.reason)}</div></div></label>`;
    }).join("");

    const decs = c.decisions || [];
    const hist = decs.length ? `<div class="hist">${decs.slice().reverse().map((d) => `<div class="hist-item"><div style="display:flex;justify-content:space-between;gap:8px"><b>${esc(actionLabel[d.action] || d.action)}</b><span class="muted">${fmtTime(d.created_at)}</span></div><div class="muted">${esc(d.reviewer_id)} · ${esc(human(d.reviewer_role))}</div><div class="r">“${esc(d.rationale)}”</div></div>`).join("")}</div>` : '<div class="muted small">No decision recorded yet.</div>';

    const audit = (c.audit || []).slice().reverse();
    const tl = audit.length ? `<ul class="timeline">${audit.map((a) => `<li class="${a.event_type === "ACTION_BLOCKED" ? "blocked" : a.event_type === "DECISION_RECORDED" ? "decision" : ""}"><div><span class="ev">${esc(a.event_type)}</span> <span class="who">· ${esc(a.actor)} · ${fmtTime(a.timestamp)}</span></div>${a.reason ? `<div class="why">${esc(a.reason)}</div>` : ""}</li>`).join("")}</ul>` : '<div class="muted small">No events.</div>';

    $("#right").innerHTML = `
      <div class="card"><div class="card-header"><h3>Playbook rules</h3><span class="pill pill-neutral">Playbook v${esc(c.playbook_version)}</span></div>${rules}
        <div class="card-body" style="padding-top:0;padding-bottom:12px"><span class="caption">Synthetic demonstration playbook</span></div></div>
      <div class="card"><div class="card-header"><h3>Human decision</h3><span class="caption">${esc(state.reviewerId)} · ${esc(human(state.role))}</span></div>
        <div class="card-body decision-form">
          <div class="actions" role="radiogroup" aria-label="Decision action">${acts}</div>
          <label class="label" for="rationale">Rationale <span class="req">*</span></label>
          <textarea id="rationale" rows="3" placeholder="Explain the decision. Recorded with rule versions in the audit log."></textarea>
          <div id="decision-alert"></div>
          <button class="btn btn-primary" id="submit-decision">Submit decision</button>
          <div style="text-align:center"><button class="linkbtn" id="gate-test" title="Sends APPROVE directly to the API, ignoring the disabled UI state">Test backend gate (bypass UI)</button></div>
          <div id="gate-result"></div>
        </div></div>
      <div class="card"><div class="card-header"><h3>Decision history</h3><span class="pill pill-neutral">${decs.length}</span></div><div class="card-body">${hist}</div></div>
      <div class="card"><div class="card-header"><h3>Audit trail</h3><span class="pill pill-neutral">${audit.length} events</span></div><div class="card-body" style="max-height:320px;overflow:auto">${tl}</div></div>`;

    document.querySelectorAll('input[name="action"]').forEach((i) => i.addEventListener("change", () => {
      state.selectedAction = i.value; document.querySelectorAll(".action").forEach((a) => a.classList.toggle("checked", !!$("input:checked", a)));
    }));
    renderDecisionAlert(); renderGate();
    $("#submit-decision").onclick = submitDecision;
    $("#gate-test").onclick = testGate;
  }
  function renderDecisionAlert() { const e = $("#decision-alert"); if (e) e.innerHTML = state.decisionError ? `<div class="alert alert-danger">${state.decisionError}</div>` : ""; }
  function renderGate() {
    const e = $("#gate-result"); if (!e || !state.gateResult) { if (e) e.innerHTML = ""; return; }
    const g = state.gateResult;
    e.innerHTML = `<div class="alert ${g.status === 403 ? "alert-danger" : "alert-warning"}" style="flex-direction:column;gap:4px"><div><b>HTTP ${g.status}</b> · POST /decision action=APPROVE (UI bypassed)</div><div class="mono" style="word-break:break-word">${esc(JSON.stringify(g.data))}</div><div class="small">${g.status === 403 ? "Enforcement happens in the backend policy engine — not just disabled buttons. Attempt logged as ACTION_BLOCKED." : ""}</div></div>`;
  }

  async function postDecision(action, rationale) {
    return api(`/api/cases/${encodeURIComponent(state.selectedId)}/decision`, { body: {
      action, rationale, reviewer_id: state.reviewerId, reviewer_role: state.role, presented_rule_versions: state.caseData.rule_versions } });
  }
  async function submitDecision() {
    const rationale = $("#rationale").value.trim();
    state.decisionError = null;
    if (!state.selectedAction) state.decisionError = "Select an action.";
    else if (!rationale) state.decisionError = "A rationale is required for every decision.";
    if (state.decisionError) { renderDecisionAlert(); return; }
    const btn = $("#submit-decision"); btn.disabled = true; btn.innerHTML = '<span class="spinner"></span> Submitting…';
    const r = await postDecision(state.selectedAction, rationale);
    if (r.status === 403) { state.decisionError = `<b>Blocked by backend policy engine:</b> ${esc(r.data.reason)}`; await refreshCase(); return; }
    if (!r.ok) { state.decisionError = esc((r.data && (r.data.reason || r.data.detail)) || `Error ${r.status}`); btn.disabled = false; btn.textContent = "Submit decision"; renderDecisionAlert(); return; }
    toast(`Decision recorded: ${actionLabel[state.selectedAction]} (#${r.data.decision_id})`);
    state.selectedAction = null; state.gateResult = null;
    await refreshCase(); loadQueue();
  }
  async function testGate() {
    const r = await postDecision("APPROVE", "Backend gate test: APPROVE sent directly, bypassing UI disabling.");
    state.gateResult = { status: r.status, data: r.data };
    await refreshCase(); loadQueue();
  }

  /* ---------- header controls + views ---------- */
  $("#reviewer").addEventListener("change", (e) => { state.reviewerId = e.target.value.trim() || "uw.demo"; if (state.caseData) renderRight(); });
  $("#role").addEventListener("change", (e) => { state.role = e.target.value; state.selectedAction = null; if (state.selectedId) refreshCase(); });
  $("#mode").addEventListener("change", (e) => { state.mode = e.target.value; if (state.caseData && !state.caseData.generated_brief) renderBrief(); });
  document.querySelectorAll(".tab").forEach((t) => t.addEventListener("click", () => switchView(t.dataset.view)));
  function switchView(v) {
    document.querySelectorAll(".tab").forEach((t) => { t.classList.toggle("active", t.dataset.view === v); t.setAttribute("aria-selected", t.dataset.view === v); });
    document.querySelectorAll(".view").forEach((s) => s.classList.toggle("active", s.id === "view-" + v));
    if (v === "governance") {
      const el = document.getElementById("view-governance");
      if (typeof window.renderGovernance === "function") window.renderGovernance(el, window.UEC);
      else el.innerHTML = '<div class="card empty" style="margin:24px">Governance view is loading…</div>';
    }
  }

  (async function init() {
    loadStatus();
    await loadQueue();
    const first = state.queue.find((q) => q.submission_id === "SUB-1042") || state.queue[0];
    if (first) selectCase(first.submission_id);
    else $("#center").innerHTML = '<div class="card empty"><h4>No submissions</h4></div>';
  })();
})();
