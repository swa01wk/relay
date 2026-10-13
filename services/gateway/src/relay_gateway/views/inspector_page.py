"""The operator's session inspector: one self-contained page served at ``GET /admin``.

Everything is rendered with ``textContent`` — conversation text and tool data are never
inserted as HTML.
"""

INSPECTOR_HTML = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="robots" content="noindex">
<title>Relay inspector</title>
<style>
  :root { --bg:#fafafa; --panel:#fff; --line:#e4e4e7; --text:#18181b; --muted:#71717a; --accent:#2563eb; --bad:#b91c1c; --ok:#15803d; }
  @media (prefers-color-scheme: dark) { :root { --bg:#09090b; --panel:#18181b; --line:#27272a; --text:#fafafa; --muted:#a1a1aa; --accent:#60a5fa; --bad:#f87171; --ok:#4ade80; } }
  * { box-sizing: border-box; }
  body { margin:0; background:var(--bg); color:var(--text); font:14px/1.5 system-ui, sans-serif; }
  header { display:flex; gap:12px; align-items:center; padding:12px 16px; border-bottom:1px solid var(--line); background:var(--panel); flex-wrap:wrap; }
  header h1 { font-size:15px; margin:0 12px 0 0; }
  button, input { font:inherit; color:inherit; background:var(--panel); border:1px solid var(--line); border-radius:6px; padding:6px 10px; }
  button { cursor:pointer; } button.on { border-color:var(--accent); color:var(--accent); }
  main { padding:16px; max-width:1200px; margin:0 auto; }
  table { width:100%; border-collapse:collapse; background:var(--panel); border:1px solid var(--line); }
  th, td { text-align:left; padding:8px 10px; border-bottom:1px solid var(--line); vertical-align:top; }
  th { color:var(--muted); font-weight:500; font-size:12px; }
  tr.row { cursor:pointer; } tr.row:hover { background:var(--bg); }
  .scroll { overflow-x:auto; }
  .muted { color:var(--muted); } .bad { color:var(--bad); } .ok { color:var(--ok); }
  .mono { font-family:ui-monospace, monospace; font-size:12px; word-break:break-all; }
  .card { background:var(--panel); border:1px solid var(--line); border-radius:8px; padding:12px; margin:12px 0; }
  .stats { display:flex; gap:24px; flex-wrap:wrap; } .stats b { display:block; font-size:18px; font-variant-numeric:tabular-nums; }
  .turn p { margin:4px 0; white-space:pre-wrap; } h2 { font-size:14px; margin:20px 0 8px; }
  pre { margin:4px 0 0; white-space:pre-wrap; word-break:break-word; }
</style>
</head>
<body>
<header>
  <h1>Relay inspector</h1>
  <button id="tab-sessions" class="on">Sessions</button>
  <button id="tab-audit">Approvals &amp; saves</button>
  <button id="refresh">Refresh</button>
  <span style="flex:1"></span>
  <input id="token" type="password" placeholder="Admin token" autocomplete="off">
  <button id="save-token">Use token</button>
</header>
<main id="main"><p class="muted">Enter the admin token (RELAY_ADMIN_TOKEN) to begin.</p></main>
<script>
(() => {
  const main = document.getElementById("main");
  let token = "", view = "sessions";
  try { token = sessionStorage.getItem("relay-admin-token") || ""; } catch (_) {}

  const el = (tag, text, cls) => { const n = document.createElement(tag); if (text != null) n.textContent = String(text); if (cls) n.className = cls; return n; };
  const when = (iso) => iso ? new Date(iso).toLocaleString() : "—";
  const num = (n) => (n ?? 0).toLocaleString();

  async function api(path) {
    const res = await fetch("/admin" + path, { headers: { Authorization: "Bearer " + token } });
    if (res.status === 401) throw new Error("That token was not accepted.");
    if (!res.ok) throw new Error("Request failed (" + res.status + ").");
    return res.json();
  }

  function table(headers, rows) {
    const wrap = el("div", null, "scroll"), t = el("table"), head = el("tr");
    headers.forEach((h) => head.append(el("th", h)));
    t.append(head); rows.forEach((r) => t.append(r)); wrap.append(t);
    return wrap;
  }
  const row = (cells, onClick) => {
    const tr = el("tr", null, onClick ? "row" : "");
    cells.forEach((c) => { const td = el("td"); if (c instanceof Node) td.append(c); else td.textContent = c == null ? "—" : String(c); tr.append(td); });
    if (onClick) tr.addEventListener("click", onClick);
    return tr;
  };
  const status = (text, cls) => el("span", text, cls);

  function auditTable(entries) {
    if (!entries.length) return el("p", "No approvals or saves yet.", "muted");
    return table(["When", "Tool", "Decision", "Result", "Details", "Session"], entries.map((e) => {
      const details = el("div");
      if (e.summary) details.append(el("div", e.summary));
      if (e.arguments) details.append(el("pre", JSON.stringify(e.arguments, null, 1), "mono"));
      if (e.error) details.append(el("div", e.error, "bad"));
      const result = e.outcome === "saved" ? status("saved", "ok") : e.outcome ? status(e.outcome, "bad") : status("—", "muted");
      const decision = e.decision === "rejected" ? status("rejected", "bad") : status(e.decision + (e.via === "form_submit" ? " (form)" : ""));
      return row([when(e.completed_at || e.decided_at || e.requested_at), e.tool_name, decision, result, details, el("span", e.session_id, "mono")], () => showSession(e.session_id));
    }));
  }

  async function showSessions() {
    const { sessions } = await api("/sessions");
    main.replaceChildren(sessions.length ? table(["Last activity", "Agent", "Turns", "Errors", "Events", "State", "Session"], sessions.map((s) => row([
      when(s.last_event_at), s.agent_id, s.turns, s.errors ? status(s.errors, "bad") : 0, s.event_count,
      s.live ? status("live", "ok") : s.ended ? "ended" : "inactive", el("span", s.session_id, "mono"),
    ], () => showSession(s.session_id)))) : el("p", "No sessions recorded yet.", "muted"));
  }

  async function showSession(id) {
    const t = await api("/sessions/" + encodeURIComponent(id));
    const u = t.usage || {}, stats = el("div", null, "card stats");
    [["Turns", t.turns.length], ["Events", t.event_count], ["Model calls", u.model_calls], ["Input tokens", u.input_tokens],
     ["Output tokens", u.output_tokens], ["Cost (USD)", u.cost_usd == null ? "—" : u.cost_usd.toFixed(4)]].forEach(([label, value]) => {
      const d = el("div"); d.append(el("b", typeof value === "number" ? num(value) : value), el("span", label, "muted")); stats.append(d);
    });
    const ids = el("p", "Session " + id + " · trace " + (t.trace_id || "—"), "mono muted");
    const turns = t.turns.map((turn) => {
      const c = el("div", null, "card turn"), failed = turn.event_types.includes("SESSION_ERROR");
      c.append(el("p", "User: " + (turn.user_text || "—")), el("p", "Assistant: " + (turn.assistant_text || "—")));
      if (turn.tool_names.length) c.append(el("p", "Tools: " + [...new Set(turn.tool_names)].join(", "), "muted"));
      if (failed) c.append(el("p", "This turn failed.", "bad"));
      c.append(el("p", turn.turn_id, "mono muted"));
      return c;
    });
    const timing = Object.entries(t.waterfall_ms || {}).map(([k, v]) => row([k, Math.round(v) + " ms"]));
    main.replaceChildren(ids, stats, el("h2", "Conversation"), ...(turns.length ? turns : [el("p", "No turns.", "muted")]),
      el("h2", "Approvals & saves"), auditTable(t.audit || []),
      ...(timing.length ? [el("h2", "Timing"), table(["Measure", "Value"], timing)] : []));
  }

  async function render() {
    document.getElementById("tab-sessions").className = view === "sessions" ? "on" : "";
    document.getElementById("tab-audit").className = view === "audit" ? "on" : "";
    if (!token) return;
    main.replaceChildren(el("p", "Loading…", "muted"));
    try {
      if (view === "audit") main.replaceChildren(auditTable((await api("/audit")).entries));
      else await showSessions();
    } catch (err) { main.replaceChildren(el("p", err.message, "bad")); }
  }

  document.getElementById("tab-sessions").onclick = () => { view = "sessions"; render(); };
  document.getElementById("tab-audit").onclick = () => { view = "audit"; render(); };
  document.getElementById("refresh").onclick = render;
  document.getElementById("save-token").onclick = () => {
    token = document.getElementById("token").value.trim();
    try { sessionStorage.setItem("relay-admin-token", token); } catch (_) {}
    document.getElementById("token").value = "";
    render();
  };
  render();
})();
</script>
</body>
</html>
"""
