/* Governance view: Evals · Playbook · Provenance · Audit */
(function () {
  'use strict';

  var SCENARIOS = {
    'S1-clean': 'Clean submission (false-positive check)',
    'S2-missing-loss-history': 'Missing loss history',
    'S3-claims-mismatch': 'Claims mismatch with generated brief',
    'S4-fabricated-citation': 'Fabricated citation',
    'S5-unsupported-fact': 'Unsupported material fact',
    'S6-prompt-injection': 'Prompt injection in broker note',
    'S7-unauthorized-approval': 'Unauthorized approval attempt + audit integrity',
    'S8-stale-rule-version': 'Outdated playbook rule version'
  };
  var METRIC_LABELS = {
    schema_validity: 'Schema validity',
    citation_integrity: 'Citation integrity',
    factual_support: 'Factual support',
    exception_recall: 'Exception recall',
    missing_evidence_recall: 'Missing-evidence recall',
    false_positive: 'False-positive control',
    injection_resistance: 'Prompt-injection resistance',
    policy_compliance: 'Policy compliance',
    audit_integrity: 'Audit integrity'
  };
  var SECTIONS = [
    ['evals', 'Evals'], ['playbook', 'Playbook'], ['provenance', 'Provenance'], ['audit', 'Audit']
  ];

  var gs = { section: 'evals', caseId: null, running: null, evalError: null };

  function esc(s) {
    if (window.UEC && typeof window.UEC.esc === 'function') return window.UEC.esc(s);
    return String(s == null ? '' : s).replace(/[&<>"']/g, function (c) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
    });
  }
  async function api(UEC, path, opts) {
    if (UEC && typeof UEC.api === 'function') return UEC.api(path, opts);
    opts = opts || {};
    opts.headers = Object.assign({ 'Content-Type': 'application/json' }, opts.headers || {});
    try {
      var r = await fetch(path, opts);
      var data = null;
      try { data = await r.json(); } catch (e) { /* non-JSON */ }
      return { ok: r.ok, status: r.status, data: data };
    } catch (e) {
      return { ok: false, status: 0, data: { error: String(e) } };
    }
  }
  function fmtTs(t) {
    if (!t) return '—';
    var d = new Date(t);
    if (isNaN(d)) return esc(t);
    return d.toLocaleString(undefined, { year: 'numeric', month: 'short', day: '2-digit', hour: '2-digit', minute: '2-digit', second: '2-digit' });
  }
  function pct(v) { return v == null ? '—' : (Math.round(v * 1000) / 10).toString().replace(/\.0$/, '') + '%'; }
  function pill(text, kind) { return '<span class="pill pill-' + (kind || 'neutral') + '">' + esc(text) + '</span>'; }
  function passPill(p) { return p ? pill('PASS', 'success') : pill('FAIL', 'danger'); }
  function bar(v, tone) {
    var w = v == null ? 0 : Math.max(0, Math.min(1, v)) * 100;
    return '<span class="gov-bar gov-bar-' + tone + '"><span style="width:' + w + '%"></span></span>';
  }
  function parseJSON(v) {
    if (v == null || typeof v !== 'string') return v;
    try { return JSON.parse(v); } catch (e) { return v; }
  }
  function sectionHead(title, sub, right) {
    return '<div class="gov-sec-head"><div><h2 class="gov-h2">' + esc(title) + '</h2>' +
      (sub ? '<p class="gov-sub">' + sub + '</p>' : '') + '</div>' + (right || '') + '</div>';
  }

  /* ---------------- EVALS ---------------- */
  function aggregate(results) {
    var metrics = {}, scen = {};
    results.forEach(function (r) {
      var m = metrics[r.metric_name] || (metrics[r.metric_name] = { raw: [], validated: [], threshold: r.threshold });
      (r.stage === 'raw' ? m.raw : m.validated).push(r);
      var s = scen[r.eval_case_id] || (scen[r.eval_case_id] = { total: 0, passed: 0, fails: [], rawWarn: [] });
      if (r.stage === 'raw') {
        if (!r.passed) s.rawWarn.push(r);
      } else {
        s.total++; if (r.passed) s.passed++; else s.fails.push(r);
      }
    });
    function avg(arr) { return arr.length ? arr.reduce(function (a, r) { return a + (+r.observed_value || 0); }, 0) / arr.length : null; }
    var rows = Object.keys(metrics).map(function (k) {
      var m = metrics[k];
      return {
        metric: k, threshold: m.threshold,
        raw: avg(m.raw), rawN: m.raw.length, rawFails: m.raw.filter(function (r) { return !r.passed; }),
        val: avg(m.validated), valN: m.validated.length,
        valPass: m.validated.length > 0 && m.validated.every(function (r) { return !!r.passed; })
      };
    });
    var order = Object.keys(METRIC_LABELS);
    rows.sort(function (a, b) { return order.indexOf(a.metric) - order.indexOf(b.metric); });
    return { rows: rows, scen: scen };
  }

  async function renderEvals(body, UEC) {
    var res = await api(UEC, '/api/evals/latest');
    var d = (res && res.data) || {};
    var run = d.run, results = d.results || [], history = d.history || [];
    var btns = '<div class="gov-actions">' +
      '<button class="btn btn-secondary" data-gov-run="cached"' + (gs.running ? ' disabled' : '') + '>' +
      (gs.running === 'cached' ? '<span class="gov-spin"></span>Running…' : 'Run evals · Cached') + '</button>' +
      '<button class="btn btn-primary" data-gov-run="live"' + (gs.running ? ' disabled' : '') + '>' +
      (gs.running === 'live' ? '<span class="gov-spin"></span>Running live (~60s)…' : 'Run evals · Live AI') + '</button></div>';

    var h = sectionHead('Evaluation scorecard',
      'Golden-scenario regression suite gating every model, prompt and rule change. ' +
      '<span class="gov-tag">Synthetic evaluation — not a production certification</span>', btns);
    if (gs.evalError) h += '<div class="gov-alert gov-alert-danger">' + esc(gs.evalError) + '</div>';
    if (gs.running === 'live') h += '<div class="gov-alert gov-alert-info"><span class="gov-spin gov-spin-dark"></span>Executing 8 scenarios against the live AI model. This typically takes about a minute.</div>';

    if (!run) {
      body.innerHTML = h + '<div class="card gov-empty">No evaluation runs yet. Run the suite to populate the scorecard.</div>';
      bindEvalRun(body, UEC);
      return;
    }
    var agg = aggregate(results);
    var rawWarnTotal = agg.rows.reduce(function (a, r) { return a + r.rawFails.length; }, 0);
    var passed = run.status === 'PASSED';

    h += '<div class="card gov-runbar">' +
      '<div class="gov-runstatus ' + (passed ? 'is-pass' : 'is-fail') + '"><div class="gov-k">Overall gate</div>' +
      '<div class="gov-big">' + (passed ? 'PASSED' : 'FAILED') + '</div><div class="gov-k">Run #' + esc(run.run_id) + '</div></div>' +
      '<dl class="gov-meta">' +
      meta('Dataset version', run.dataset_version) + meta('Model version', run.model_version) +
      meta('Prompt version', run.prompt_version) + meta('Rule version', run.rule_version) +
      meta('Run time', fmtTs(run.completed_at || run.started_at), true) +
      meta('Raw-stage warnings', rawWarnTotal ? '<span class="gov-amber-text">' + rawWarnTotal + ' caught by validator</span>' : '0', true) +
      '</dl></div>';

    h += '<div class="gov-callout"><div class="gov-callout-icon">i</div><div><strong>Two stages, reported separately.</strong> ' +
      'Raw generation quality and validated output quality are reported separately. A perfect validated score after dropping invalid content is not proof the raw model output was error-free.</div></div>';

    // Scorecard
    h += '<div class="card gov-card"><div class="card-header gov-card-h"><span class="section-title">Metric scorecard</span>' +
      '<span class="muted gov-small">Averaged across scenarios where each metric applies</span></div>' +
      '<div class="gov-table-wrap"><table class="table gov-table"><thead><tr>' +
      '<th>Metric</th><th class="gov-num">Gate</th><th>Raw generation</th><th>Validated output</th><th>Result</th></tr></thead><tbody>';
    agg.rows.forEach(function (r) {
      var rawWarn = r.rawFails.length > 0;
      h += '<tr' + (rawWarn ? ' class="gov-row-warn"' : '') + '>' +
        '<td><div class="gov-metric">' + esc(METRIC_LABELS[r.metric] || r.metric) + '</div><div class="gov-code">' + esc(r.metric) + '</div></td>' +
        '<td class="gov-num">' + pct(r.threshold) + '</td>' +
        '<td>' + (r.rawN ? '<div class="gov-score">' + bar(r.raw, rawWarn ? 'warn' : 'ok') +
          '<span class="gov-num ' + (rawWarn ? 'gov-amber-text' : '') + '">' + pct(r.raw) + '</span>' +
          (rawWarn ? pill(r.rawFails.length + ' raw warning' + (r.rawFails.length > 1 ? 's' : ''), 'warning') : '') + '</div>' +
          (rawWarn ? '<div class="gov-rawnote">' + r.rawFails.map(function (f) {
            return '<div><b>' + esc(f.eval_case_id) + ':</b> ' + esc(f.failure_reason || 'below gate') + '</div>';
          }).join('') + '</div>' : '')
          : '<span class="muted gov-small">n/a — deterministic check</span>') + '</td>' +
        '<td><div class="gov-score">' + bar(r.val, r.valPass ? 'ok' : 'bad') + '<span class="gov-num">' + pct(r.val) + '</span>' +
        '<span class="muted gov-small">n=' + r.valN + '</span></div></td>' +
        '<td>' + passPill(r.valPass) + '</td></tr>';
    });
    h += '</tbody></table></div></div>';

    // Scenarios + history side by side
    h += '<div class="gov-grid2"><div class="card gov-card"><div class="card-header gov-card-h"><span class="section-title">Scenarios</span>' +
      '<span class="muted gov-small">' + Object.keys(agg.scen).length + ' golden scenarios</span></div><div class="gov-scen-list">';
    Object.keys(agg.scen).sort().forEach(function (id) {
      var s = agg.scen[id], ok = s.fails.length === 0;
      var detail = '';
      if (s.fails.length) detail += s.fails.map(function (f) {
        return '<div class="gov-reason gov-reason-bad"><b>' + esc(METRIC_LABELS[f.metric_name] || f.metric_name) + '</b> — ' + esc(f.failure_reason || 'below gate') + '</div>';
      }).join('');
      if (s.rawWarn.length) detail += s.rawWarn.map(function (f) {
        return '<div class="gov-reason gov-reason-warn"><b>Raw · ' + esc(METRIC_LABELS[f.metric_name] || f.metric_name) + '</b> — ' + esc(f.failure_reason || 'raw output below gate') + ' <i>(removed by validator)</i></div>';
      }).join('');
      h += '<details class="gov-scen' + (s.rawWarn.length ? ' has-warn' : '') + '"' + (detail ? '' : ' data-empty') + '><summary>' +
        '<span class="gov-scen-id">' + esc(id.split('-')[0]) + '</span>' +
        '<span class="gov-scen-name">' + esc(SCENARIOS[id] || id) + '</span>' +
        '<span class="gov-num gov-scen-count">' + s.passed + '/' + s.total + '</span>' +
        (s.rawWarn.length ? pill('raw warning', 'warning') : '') + passPill(ok) + '</summary>' +
        '<div class="gov-scen-body">' + (detail || '<div class="muted gov-small">All checks passed at both stages. No failure reasons recorded.</div>') + '</div></details>';
    });
    h += '</div></div>';

    h += '<div class="card gov-card"><div class="card-header gov-card-h"><span class="section-title">Run history</span><span class="muted gov-small">Last 10 runs</span></div>' +
      '<div class="gov-table-wrap gov-scroll"><table class="table gov-table gov-compact"><thead><tr><th>Run</th><th>Completed</th><th>Model</th><th>Result</th></tr></thead><tbody>';
    history.forEach(function (r) {
      var live = /live/i.test(r.model_version || '') || !/cached/i.test(r.model_version || '');
      h += '<tr' + (r.run_id === run.run_id ? ' class="gov-current"' : '') + '><td class="gov-num">#' + esc(r.run_id) + '</td><td class="gov-num gov-small">' + fmtTs(r.completed_at) +
        '</td><td>' + (live ? pill('LIVE', 'ai') : pill('CACHED', 'neutral')) + '</td><td>' + (r.status === 'PASSED' ? pill('PASSED', 'success') : pill(r.status || 'FAILED', 'danger')) + '</td></tr>';
    });
    h += '</tbody></table></div>' +
      '<div class="gov-pilot"><div class="gov-pilot-h">Pilot plan <span class="gov-tag">documented, not built</span></div>' +
      'Expand to a 30–50 scenario golden dataset curated with senior underwriters, with per-exception-type coverage, adversarial broker notes, and sign-off before any model or prompt promotion.</div></div></div>';

    body.innerHTML = h;
    bindEvalRun(body, UEC);
  }
  function bindEvalRun(body, UEC) {
    body.querySelectorAll('[data-gov-run]').forEach(function (b) {
      b.addEventListener('click', async function () {
        var mode = b.getAttribute('data-gov-run');
        gs.running = mode; gs.evalError = null;
        await renderEvals(body, UEC);
        var r = await api(UEC, '/api/evals/run', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ mode: mode }) });
        gs.running = null;
        if (!r || !r.ok) gs.evalError = 'Eval run failed (' + (r && r.status) + '): ' + ((r && r.data && (r.data.detail || r.data.error)) || 'unknown error');
        if (body.isConnected) await renderEvals(body, UEC);
      });
    });
  }
  function meta(k, v, rawHtml) {
    return '<div><dt>' + esc(k) + '</dt><dd>' + (rawHtml ? v : esc(v || '—')) + '</dd></div>';
  }

  /* ---------------- PLAYBOOK ---------------- */
  async function renderPlaybook(body, UEC) {
    var res = await Promise.all([api(UEC, '/api/playbook'), api(UEC, '/api/cases/' + encodeURIComponent(gs.caseId) + '?role=' + encodeURIComponent(role(UEC)))]);
    var pb = (res[0] && res[0].data) || { rules: [] };
    var cs = (res[1] && res[1].ok && res[1].data) || {};
    var triggered = {};
    (cs.rules || []).forEach(function (r) { triggered[r.rule_id] = true; });
    var nTrig = Object.keys(triggered).length;

    var h = sectionHead('Underwriting playbook',
      '<span class="gov-tag">Synthetic demonstration playbook — not Indigo\'s underwriting manual</span>',
      '<div class="gov-ver"><span class="muted gov-small">Playbook version</span><span class="gov-ver-n">v' + esc(pb.playbook_version || '—') + '</span></div>');
    h += '<div class="gov-callout gov-callout-soft"><div class="gov-callout-icon">★</div><div>' +
      (nTrig ? '<strong>' + nTrig + ' rule' + (nTrig > 1 ? 's' : '') + ' triggered</strong> by <b>' + esc(gs.caseId) + '</b> are highlighted.' :
        'No rules triggered by <b>' + esc(gs.caseId) + '</b>.') +
      ' No rule permits the copilot to make a final decision; every action requires a named human reviewer.</div></div>';

    h += '<div class="card gov-card"><div class="gov-table-wrap"><table class="table gov-table gov-pb"><thead><tr>' +
      '<th>Rule</th><th>Trigger</th><th>Required evidence</th><th>Permitted actions</th><th>Final decision</th><th>Escalation</th><th>Required role</th></tr></thead><tbody>';
    (pb.rules || []).forEach(function (r) {
      var t = triggered[r.rule_id];
      h += '<tr class="' + (t ? 'gov-row-hit' : '') + '"><td><div class="gov-rule-id">' + esc(r.rule_id) + (t ? ' ' + pill('Triggered', 'warning') : '') + '</div>' +
        '<div class="gov-rule-title">' + esc(r.title || '') + '</div>' +
        '<div class="gov-small muted gov-num">v' + esc(r.version) + ' · ' + esc(r.jurisdiction) + ' · eff. ' + esc(r.effective_date) + '</div></td>' +
        '<td><code class="gov-codebox">' + esc(r.trigger) + '</code></td>' +
        '<td><ul class="gov-ev">' + (r.required_evidence || []).map(function (e) { return '<li>' + esc(e) + '</li>'; }).join('') + '</ul></td>' +
        '<td><div class="gov-pills">' + (r.permitted_actions || []).map(function (a) { return pill(a, 'ai'); }).join('') + '</div></td>' +
        '<td>' + (r.final_decision_allowed ? pill('Yes', 'warning') : pill('No', 'danger')) + '</td>' +
        '<td>' + (r.escalation_required ? pill('Required', 'warning') : '<span class="muted">Optional</span>') + '</td>' +
        '<td>' + (r.required_role ? pill(r.required_role, 'neutral') : '<span class="muted">Any underwriter</span>') + '</td></tr>';
    });
    h += '</tbody></table></div></div>';
    body.innerHTML = h;
  }

  /* ---------------- PROVENANCE ---------------- */
  async function loadCase(UEC) {
    var r = await api(UEC, '/api/cases/' + encodeURIComponent(gs.caseId) + '?role=' + encodeURIComponent(role(UEC)));
    return r && r.ok ? r.data : null;
  }
  function role(UEC) { return (UEC && UEC.state && UEC.state.role) || 'underwriter'; }

  async function renderProvenance(body, UEC) {
    var c = await loadCase(UEC);
    if (!c) { body.innerHTML = '<div class="card gov-empty">Could not load case ' + esc(gs.caseId) + '.</div>'; return; }
    var b = c.generated_brief, v = (b && b.validation) || {};
    var docs = (c.bundle && c.bundle.documents) || [];
    var h = sectionHead('Provenance · ' + gs.caseId, 'Every artifact the copilot produced, traced to its model, prompt, rule and evidence versions.');

    h += '<div class="gov-grid2">';
    // brief provenance
    h += '<div class="card gov-card"><div class="card-header gov-card-h"><span class="section-title">Generated brief</span>' +
      (b ? modeBadge(b.generation_mode) : '') + '</div>';
    if (!b) h += '<div class="gov-pad muted">No brief generated yet for this case.</div>';
    else {
      if (b.generation_mode === 'cached') h += '<div class="gov-alert gov-alert-warn gov-m">Cached replay of a previously recorded model response — <b>not a fresh model execution</b>.</div>';
      h += '<dl class="gov-kv">' +
        kv('Brief ID', '#' + esc(b.brief_id)) + kv('Model version', '<code>' + esc(b.model_version) + '</code>') +
        kv('Prompt version', '<code>' + esc(b.prompt_version) + '</code>') + kv('Generation mode', esc(b.generation_mode)) +
        kv('Generated at', fmtTs(v.generated_at || b.created_at)) +
        (v.cached_at ? kv('Cached at', fmtTs(v.cached_at)) : '') +
        kv('Validation', b.validation_status === 'VALIDATED' ? pill('VALIDATED', 'success') : pill(b.validation_status || '—', 'warning')) +
        kv('Schema attempts', esc((v.attempts || []).length || 1)) +
        kv('Validator issues', esc((v.issues || []).length)) +
        kv('Created by', '<code>' + esc(b.created_by) + '</code>') + '</dl>';
      if (v.raw_metrics || v.validated_metrics) {
        h += '<div class="gov-mini"><div class="gov-mini-h">Raw vs validated</div><table class="gov-mini-t"><thead><tr><th></th><th>Raw</th><th>Validated</th></tr></thead><tbody>';
        ['items', 'citation_errors', 'unsupported', 'policy_errors'].forEach(function (k) {
          var rv = (v.raw_metrics || {})[k], vv = (v.validated_metrics || {})[k];
          var warn = k !== 'items' && rv > 0;
          h += '<tr><td>' + esc(k.replace(/_/g, ' ')) + '</td><td class="gov-num' + (warn ? ' gov-amber-text' : '') + '">' + esc(rv == null ? '—' : rv) + '</td><td class="gov-num">' + esc(vv == null ? '—' : vv) + '</td></tr>';
        });
        h += '</tbody></table></div>';
      }
    }
    h += '</div>';

    // rules
    h += '<div class="card gov-card"><div class="card-header gov-card-h"><span class="section-title">Policy context</span>' +
      '<span class="pill pill-neutral">Playbook v' + esc(c.playbook_version) + '</span></div><div class="gov-pad">';
    var rv = c.rule_versions || {};
    if (!Object.keys(rv).length) h += '<div class="muted">No rules applied — no exceptions detected.</div>';
    else h += '<div class="gov-k">Rule versions applied</div><div class="gov-pills gov-mt">' + Object.keys(rv).map(function (k) { return '<span class="gov-chip"><b>' + esc(k) + '</b> v' + esc(rv[k]) + '</span>'; }).join('') + '</div>';
    h += '<div class="gov-k gov-mt2">Exceptions detected</div><div class="gov-pills gov-mt">' +
      ((c.exceptions || []).map(function (e) { return pill(e.reason_code + (e.severity ? ' · ' + e.severity : ''), e.severity === 'HIGH' ? 'danger' : 'warning'); }).join('') || '<span class="muted">None</span>') + '</div>';
    h += '<div class="gov-k gov-mt2">Evidence completeness</div><div class="gov-score gov-mt">' + bar(c.completeness ? c.completeness.present / c.completeness.required : 0, 'ok') +
      '<span class="gov-num">' + esc(c.completeness ? c.completeness.present + ' / ' + c.completeness.required : '—') + '</span></div>';
    h += '</div></div></div>';

    // docs
    h += '<div class="card gov-card"><div class="card-header gov-card-h"><span class="section-title">Evidence documents</span><span class="muted gov-small">' + docs.length + ' source documents</span></div>' +
      '<div class="gov-table-wrap"><table class="table gov-table"><thead><tr><th>Document</th><th>Type</th><th>Title</th><th class="gov-num">Version</th><th>Ingested</th></tr></thead><tbody>' +
      docs.map(function (d) {
        return '<tr><td><code class="gov-codebox">' + esc(d.document_id) + '</code></td><td>' + pill(String(d.document_type || '').replace(/_/g, ' '), 'neutral') + '</td><td>' + esc(d.title) +
          '</td><td class="gov-num">v' + esc(d.version) + '</td><td class="gov-num gov-small">' + fmtTs(d.created_at) + '</td></tr>';
      }).join('') + '</tbody></table></div></div>';

    // decisions
    var decs = c.decisions || [];
    h += '<div class="card gov-card"><div class="card-header gov-card-h"><span class="section-title">Decisions</span><span class="muted gov-small">Versions recorded at time of decision</span></div>';
    if (!decs.length) h += '<div class="gov-pad muted">No human decision recorded for this case yet.</div>';
    else {
      h += '<div class="gov-table-wrap"><table class="table gov-table"><thead><tr><th>Decision</th><th>Action</th><th>Reviewer</th><th>Rule versions</th><th>Model</th><th>Prompt</th><th>Recorded</th></tr></thead><tbody>' +
        decs.map(function (d) {
          var rvs = parseJSON(d.rule_versions_json) || d.rule_versions || {};
          return '<tr><td class="gov-num">#' + esc(d.decision_id) + '</td><td>' + pill(d.action, 'ai') + '</td><td>' + esc(d.reviewer_id) + ' <span class="muted gov-small">(' + esc(d.reviewer_role) + ')</span></td><td>' +
            (typeof rvs === 'object' ? Object.keys(rvs).map(function (k) { return '<span class="gov-chip"><b>' + esc(k) + '</b> v' + esc(rvs[k]) + '</span>'; }).join(' ') || '—' : esc(rvs)) +
            '</td><td><code>' + esc(d.model_version || '—') + '</code></td><td><code>' + esc(d.prompt_version || '—') + '</code></td><td class="gov-num gov-small">' + fmtTs(d.created_at) + '</td></tr>';
        }).join('') + '</tbody></table></div>';
    }
    h += '</div>';
    body.innerHTML = h;
  }
  function modeBadge(m) {
    if (m === 'live') return '<span class="gov-mode gov-mode-live"><i></i>LIVE</span>';
    if (m === 'cached') return '<span class="gov-mode gov-mode-cached">CACHED</span>';
    return '<span class="gov-mode gov-mode-cached">' + esc(String(m || '—').toUpperCase()) + '</span>';
  }
  function kv(k, v) { return '<div><dt>' + esc(k) + '</dt><dd>' + v + '</dd></div>'; }

  /* ---------------- AUDIT ---------------- */
  var SECTIONS_BRIEF = [['known', 'Known facts', 'fact'], ['conflicts', 'Conflicts', 'description'], ['missing', 'Missing evidence', 'field'], ['next_steps', 'Next steps', 'action']];
  function itemText(it, key) {
    if (it == null) return '';
    if (typeof it !== 'object') return String(it);
    if (key === 'missing') return (it.field || '') + (it.reason ? ': ' + it.reason : '');
    if (key === 'next_steps') return (it.action || '') + (it.reason ? ': ' + it.reason : '');
    return it.fact || it.description || JSON.stringify(it);
  }
  function wordDiff(a, b) {
    var A = a.split(/(\s+)/), B = b.split(/(\s+)/), n = A.length, m = B.length;
    if (n * m > 250000) return { left: '<del>' + esc(a) + '</del>', right: '<ins>' + esc(b) + '</ins>' };
    var L = []; for (var i = 0; i <= n; i++) { L.push(new Array(m + 1).fill(0)); }
    for (i = n - 1; i >= 0; i--) for (var j = m - 1; j >= 0; j--) L[i][j] = A[i] === B[j] ? L[i + 1][j + 1] + 1 : Math.max(L[i + 1][j], L[i][j + 1]);
    var left = '', right = ''; i = 0; j = 0;
    while (i < n && j < m) {
      if (A[i] === B[j]) { left += esc(A[i]); right += esc(B[j]); i++; j++; }
      else if (L[i + 1][j] >= L[i][j + 1]) { left += '<del>' + esc(A[i++]) + '</del>'; }
      else { right += '<ins>' + esc(B[j++]) + '</ins>'; }
    }
    while (i < n) left += '<del>' + esc(A[i++]) + '</del>';
    while (j < m) right += '<ins>' + esc(B[j++]) + '</ins>';
    return { left: left, right: right };
  }

  async function renderAudit(body, UEC) {
    var c = await loadCase(UEC);
    if (!c) { body.innerHTML = '<div class="card gov-empty">Could not load case ' + esc(gs.caseId) + '.</div>'; return; }
    var g = c.generated_brief, e = c.edited_brief;
    var h = sectionHead('Audit trail · ' + gs.caseId, 'Who changed what, when, and why — original AI output is never overwritten.',
      '<span class="gov-lock">&#128274; Audit log is append-only (enforced by database triggers)</span>');

    // Draft vs edit
    h += '<div class="card gov-card"><div class="card-header gov-card-h"><span class="section-title">Original AI draft vs human-edited version</span>' +
      (e ? '<span class="muted gov-small">Edited by <b>' + esc(e.created_by) + '</b> · ' + fmtTs(e.created_at) + '</span>' : '') + '</div>';
    if (!g) h += '<div class="gov-pad muted">No AI draft generated yet.</div>';
    else if (!e) h += '<div class="gov-pad"><div class="gov-alert gov-alert-info">No human edits recorded — the reviewer has not modified the AI draft (brief #' + esc(g.brief_id) + ', ' + esc(g.model_version) + ' / ' + esc(g.prompt_version) + ').</div></div>';
    else {
      var nChanged = 0, rows = '';
      SECTIONS_BRIEF.forEach(function (s) {
        var a = (g[s[0]] || []).map(function (x) { return itemText(x, s[0]); });
        var bb = (e[s[0]] || []).map(function (x) { return itemText(x, s[0]); });
        var len = Math.max(a.length, bb.length);
        if (!len) return;
        rows += '<div class="gov-diff-sec">' + esc(s[1]) + '</div>';
        for (var i = 0; i < len; i++) {
          var l = a[i], r = bb[i], cls = '', L, R;
          if (l == null) { L = '<span class="muted">—</span>'; R = '<ins>' + esc(r) + '</ins>'; cls = 'added'; }
          else if (r == null) { L = '<del>' + esc(l) + '</del>'; R = '<span class="muted">removed</span>'; cls = 'removed'; }
          else if (l === r) { L = esc(l); R = esc(r); }
          else { var dd = wordDiff(l, r); L = dd.left; R = dd.right; cls = 'changed'; }
          if (cls) nChanged++;
          rows += '<div class="gov-diff-row ' + (cls ? 'is-' + cls : '') + '"><div>' + L + '</div><div>' + R + '</div></div>';
        }
      });
      h += '<div class="gov-diff"><div class="gov-diff-head"><div>Original AI draft <span class="pill pill-ai">#' + esc(g.brief_id) + '</span></div>' +
        '<div>Human-edited version <span class="pill pill-success">#' + esc(e.brief_id) + '</span> <span class="muted gov-small">' + nChanged + ' item' + (nChanged === 1 ? '' : 's') + ' changed</span></div></div>' + rows + '</div>';
    }
    h += '</div>';

    // rationales
    var decs = c.decisions || [];
    h += '<div class="card gov-card"><div class="card-header gov-card-h"><span class="section-title">Decision rationales</span></div>';
    if (!decs.length) h += '<div class="gov-pad muted">No decisions recorded yet.</div>';
    else h += '<div class="gov-rationales">' + decs.map(function (d) {
      return '<div class="gov-rat"><div class="gov-rat-h">' + pill(d.action, 'ai') + '<b>' + esc(d.reviewer_id) + '</b><span class="muted gov-small">' + esc(d.reviewer_role) + '</span><span class="gov-num muted gov-small gov-right">' + fmtTs(d.created_at) + '</span></div>' +
        '<blockquote>' + esc(d.rationale) + '</blockquote></div>';
    }).join('') + '</div>';
    h += '</div>';

    // events
    var ev = c.audit || [];
    h += '<div class="card gov-card"><div class="card-header gov-card-h"><span class="section-title">Audit events</span><span class="muted gov-small">' + ev.length + ' events · oldest first</span></div>' +
      '<div class="gov-table-wrap gov-scroll-lg"><table class="table gov-table"><thead><tr><th>#</th><th>Timestamp</th><th>Actor</th><th>Event</th><th>Reason</th><th>Before / after</th></tr></thead><tbody>';
    ev.forEach(function (a) {
      var t = a.event_type || '', kind = /BLOCK|VIOLAT|FAIL/.test(t) ? 'danger' : /DECISION/.test(t) ? 'success' : /BRIEF|EDIT/.test(t) ? 'ai' : /EXCEPTION/.test(t) ? 'warning' : 'neutral';
      var hasJ = a.before != null || a.after != null;
      h += '<tr><td class="gov-num muted">' + esc(a.event_id) + '</td><td class="gov-num gov-small gov-nowrap">' + fmtTs(a.timestamp) + '</td><td><code>' + esc(a.actor) + '</code></td><td>' + pill(t, kind) +
        '</td><td class="gov-reason-cell">' + (a.reason ? esc(a.reason) : '<span class="muted">—</span>') + '</td><td>' +
        (hasJ ? '<details class="gov-json"><summary>View</summary><div class="gov-json-grid"><div><div class="gov-k">Before</div><pre>' + esc(a.before == null ? 'null' : JSON.stringify(a.before, null, 2)) +
          '</pre></div><div><div class="gov-k">After</div><pre>' + esc(a.after == null ? 'null' : JSON.stringify(a.after, null, 2)) + '</pre></div></div></details>' : '<span class="muted">—</span>') + '</td></tr>';
    });
    h += '</tbody></table></div></div>';
    body.innerHTML = h;
  }

  /* ---------------- SHELL ---------------- */
  window.renderGovernance = async function (el, UEC) {
    UEC = UEC || window.UEC || {};
    if (!gs.caseId) gs.caseId = (UEC.state && UEC.state.selectedId) || 'SUB-1042';
    else if (UEC.state && UEC.state.selectedId && UEC.state.selectedId !== gs._lastSel) gs.caseId = UEC.state.selectedId;
    gs._lastSel = UEC.state && UEC.state.selectedId;

    var q = await api(UEC, '/api/queue');
    var cases = (q && q.ok && Array.isArray(q.data)) ? q.data : [];
    if (!cases.some(function (c) { return c.submission_id === gs.caseId; })) cases.unshift({ submission_id: gs.caseId });

    el.innerHTML = '<div class="gov-root"><div class="gov-nav-bar"><nav class="gov-nav" role="tablist">' +
      SECTIONS.map(function (s) { return '<button role="tab" class="gov-nav-btn' + (gs.section === s[0] ? ' active' : '') + '" data-gov-sec="' + s[0] + '">' + s[1] + '</button>'; }).join('') +
      '</nav><label class="gov-case-sel"><span>Case</span><select data-gov-case>' +
      cases.map(function (c) { return '<option value="' + esc(c.submission_id) + '"' + (c.submission_id === gs.caseId ? ' selected' : '') + '>' + esc(c.submission_id) + (c.specialty ? ' · ' + esc(c.specialty) : '') + '</option>'; }).join('') +
      '</select></label></div><div class="gov-body"><div class="gov-loading"><span class="gov-spin gov-spin-dark"></span>Loading…</div></div></div>';

    var body = el.querySelector('.gov-body');
    var sel = el.querySelector('.gov-case-sel');
    sel.style.visibility = gs.section === 'evals' ? 'hidden' : 'visible';

    async function show() {
      body.innerHTML = '<div class="gov-loading"><span class="gov-spin gov-spin-dark"></span>Loading…</div>';
      sel.style.visibility = gs.section === 'evals' ? 'hidden' : 'visible';
      try {
        if (gs.section === 'evals') await renderEvals(body, UEC);
        else if (gs.section === 'playbook') await renderPlaybook(body, UEC);
        else if (gs.section === 'provenance') await renderProvenance(body, UEC);
        else await renderAudit(body, UEC);
      } catch (err) {
        console.warn('Governance render error', err);
        body.innerHTML = '<div class="card gov-empty">Unable to load this section: ' + esc(err && err.message) + '</div>';
      }
    }
    el.querySelectorAll('[data-gov-sec]').forEach(function (b) {
      b.addEventListener('click', function () {
        gs.section = b.getAttribute('data-gov-sec');
        el.querySelectorAll('[data-gov-sec]').forEach(function (x) { x.classList.toggle('active', x === b); });
        show();
      });
    });
    el.querySelector('[data-gov-case]').addEventListener('change', function (ev) { gs.caseId = ev.target.value; show(); });
    await show();
  };
})();
