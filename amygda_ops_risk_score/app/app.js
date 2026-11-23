// The fleet app's controls: run now, add files, and the schedule. The page
// under it is the same dashboard the monitor writes to a file; this script is
// only added when the page is served by `amygda-risk app`.
(function () {
  "use strict";
  const main = document.querySelector("main");
  if (!main) return;
  const bar = document.createElement("div");
  bar.id = "app-bar";
  main.insertBefore(bar, main.firstChild);

  const esc = s => String(s).replace(/[&<>"']/g, c => ({"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"}[c]));
  const when = iso => {
    if (!iso) return "";
    const d = new Date(iso), now = new Date();
    const time = d.toLocaleTimeString([], {hour: "2-digit", minute: "2-digit"});
    if (d.toDateString() === now.toDateString()) return `today ${time}`;
    return `${d.toLocaleDateString([], {weekday: "short", month: "short", day: "numeric"})} ${time}`;
  };
  const size = n => n < 1024 ? `${n} B` : n < 1048576 ? `${(n / 1024).toFixed(0)} KB` : `${(n / 1048576).toFixed(1)} MB`;

  async function api(method, path, body, raw) {
    const opts = {method, headers: {"X-Amygda-App": "1"}};
    if (body !== undefined) opts.body = raw ? body : JSON.stringify(body);
    const res = await fetch(path, opts);
    let data = {};
    try { data = await res.json(); } catch (e) { /* no body */ }
    if (!res.ok) throw new Error(data.error || `The app answered ${res.status}.`);
    return data;
  }

  let state = null, version = null, showSchedule = false, message = null, uploading = 0, timer = null;

  function statusLine(s) {
    if (s.running) return {cls: "busy", text: `Running a ${s.running.trigger} run`, sub: `started ${when(s.running.started_at)}`};
    const r = s.last_run;
    if (!r) return {cls: "", text: "Ready", sub: "no run yet"};
    const what = r.status === "ok" ? "Scored" : r.status === "failed" ? "Failed" : "Nothing new";
    const how = r.trigger === "scheduled" ? "scheduled" : "manual";
    return {cls: r.status === "failed" ? "bad" : "", text: `Last run: ${what}`, sub: `${how}, ${when(r.finished_at || r.started_at)}${r.status === "failed" && r.reason ? ` · ${r.reason}` : ""}`};
  }

  function schedulePanel(s) {
    const sc = s.schedule || {every: "off"};
    const opt = (v, label, cur) => `<option value="${v}"${String(v) === String(cur) ? " selected" : ""}>${label}</option>`;
    const days = [["mon", "Monday"], ["tue", "Tuesday"], ["wed", "Wednesday"], ["thu", "Thursday"], ["fri", "Friday"], ["sat", "Saturday"], ["sun", "Sunday"]];
    return `<div class="panel"><div class="line">
      <label>Run <select id="ab-every">${opt("off", "only when I press Run now", sc.every)}${opt("hours", "every few hours", sc.every)}${opt("day", "every day", sc.every)}${opt("week", "every week", sc.every)}</select></label>
      <label id="ab-hours-l">every <select id="ab-hours">${[1, 2, 3, 4, 6, 8, 12].map(h => opt(h, h === 1 ? "hour" : `${h} hours`, sc.hours || 6)).join("")}</select></label>
      <label id="ab-day-l">on <select id="ab-day">${days.map(d => opt(d[0], d[1], sc.weekday || "mon")).join("")}</select></label>
      <label id="ab-at-l">at <input type="time" id="ab-at" value="${esc(sc.at || "06:00")}"></label>
      <button class="btn primary" id="ab-save" type="button">Save</button>
      ${s.schedule ? `<button class="btn" id="ab-pause" type="button">${s.schedule.paused ? "Resume" : "Pause"}</button>` : ""}
      <button class="btn" id="ab-close" type="button">Close</button></div>
      <p class="sub" style="margin:8px 0 0">A scheduled run scores whatever files are waiting, and does nothing when there are none. Times are this computer's local time. The schedule only runs while the app is running.</p></div>`;
  }

  function render() {
    const s = state;
    if (!s) return;
    const st = statusLine(s), n = s.inbox.length, busy = !!s.running || uploading > 0;
    const next = s.schedule && !s.schedule.paused && s.next_run ? `next ${when(s.next_run)}` : "";
    let h = `<div class="line">
      <div class="grow"><div class="status"><span class="dot ${st.cls}"></span>${esc(st.text)}</div><div class="sub">${esc(st.sub)}</div></div>
      <div class="sub">${esc(s.schedule_text)}${next ? ` · ${esc(next)}` : ""}</div>
      <input type="file" id="ab-file" multiple accept="${s.file_types.join(",")}" hidden>
      <button class="btn" id="ab-add" type="button"${uploading ? " disabled" : ""}>${uploading ? "Adding…" : "Add files"}</button>
      <button class="btn primary" id="ab-run" type="button"${busy || !n || !s.key_present ? " disabled" : ""}>${s.running ? "Running…" : n ? `Run now (${n} file${n > 1 ? "s" : ""})` : "Run now"}</button>
      <button class="btn" id="ab-sched" type="button">Schedule</button></div>`;
    if (n) h += `<div class="files"><span class="sub">Waiting:</span>${s.inbox.map(f => `<span class="file">${esc(f.name)} <span class="sub">${size(f.size)}</span><button type="button" title="Remove" aria-label="Remove ${esc(f.name)}" data-rm="${esc(f.name)}"${s.running ? " disabled" : ""}>✕</button></span>`).join("")}</div>`;
    const notes = [];
    if (!s.key_present) notes.push({err: true, text: `No API key found in ${s.key_env}. Set it (for example in a .env file beside the monitor folder) and start the app again.`});
    if (s.problem) notes.push({err: true, text: s.problem});
    if (message) notes.push(message);
    else if (s.last_action && !s.running) notes.push({err: s.last_action.status === "failed", text: `${s.last_action.status === "failed" ? "The run failed: " : ""}${s.last_action.message}${(s.last_action.warnings || []).length ? ` ${s.last_action.warnings.length === 1 ? "1 warning" : s.last_action.warnings.length + " warnings"} (see the runs).` : ""}`});
    else if (s.note) notes.push({text: s.note});
    notes.forEach(m => { h += `<div class="msg${m.err ? " err" : ""}" role="status">${esc(m.text)}</div>`; });
    if (showSchedule) h += schedulePanel(s);
    bar.innerHTML = h;
    wire();
  }

  function wire() {
    const $ = id => document.getElementById(id);
    $("ab-add").onclick = () => $("ab-file").click();
    $("ab-file").onchange = ev => upload(ev.target.files);
    $("ab-run").onclick = () => act(() => api("POST", "/api/run"));
    $("ab-sched").onclick = () => { showSchedule = !showSchedule; render(); };
    bar.querySelectorAll("[data-rm]").forEach(b => b.onclick = () => act(() => api("DELETE", "/api/inbox/" + encodeURIComponent(b.dataset.rm))));
    if (!showSchedule) return;
    const every = $("ab-every");
    const show = () => {
      $("ab-hours-l").hidden = every.value !== "hours";
      $("ab-day-l").hidden = every.value !== "week";
      $("ab-at-l").hidden = every.value !== "day" && every.value !== "week";
    };
    every.onchange = show; show();
    $("ab-close").onclick = () => { showSchedule = false; render(); };
    $("ab-save").onclick = () => {
      let body = null;
      if (every.value === "hours") body = {every: "hours", hours: +$("ab-hours").value};
      else if (every.value === "day") body = {every: "day", at: $("ab-at").value};
      else if (every.value === "week") body = {every: "week", weekday: $("ab-day").value, at: $("ab-at").value};
      if (body && state.schedule && state.schedule.paused) body.paused = true;
      act(() => api("POST", "/api/schedule", body), () => { showSchedule = false; }, true);
    };
    if ($("ab-pause")) $("ab-pause").onclick = () => act(() => api("POST", "/api/schedule/" + (state.schedule.paused ? "resume" : "pause")), null, true);
  }

  // keepPage: the change (a schedule) doesn't alter the dashboard, so the
  // page isn't loaded again for it.
  async function act(fn, after, keepPage) {
    message = null;
    try { await fn(); if (after) after(); } catch (e) { message = {err: true, text: e.message}; }
    await refresh(false, keepPage);
  }

  async function upload(files) {
    const list = Array.from(files || []);
    if (!list.length) return;
    message = null; uploading = list.length; render();
    const failed = [];
    for (const f of list) {
      try { await api("PUT", "/api/inbox/" + encodeURIComponent(f.name), f, true); } catch (e) { failed.push(`${f.name}: ${e.message}`); }
      uploading--;
    }
    uploading = 0;
    if (failed.length) message = {err: true, text: failed.join(" ")};
    await refresh();
  }

  // Acknowledge buttons in the dashboard's Alerts panel. The page loads again
  // once the alert is saved.
  document.addEventListener("click", ev => {
    const b = ev.target.closest ? ev.target.closest("[data-ack]") : null;
    if (!b) return;
    b.disabled = true;
    act(() => api("POST", "/api/alerts/" + encodeURIComponent(b.dataset.ack) + "/ack"));
  });

  // Alert settings in the Alerts panel: the page draws them read-only, and
  // here they can be changed and saved. The page loads again once saved.
  const ruleLines = () => Array.from(document.querySelectorAll("[data-rule]"));
  document.addEventListener("change", ev => {
    const on = ev.target.matches && ev.target.matches("[data-on]") ? ev.target : null;
    if (!on) return;
    const line = on.closest("[data-rule]");
    line.querySelector("[data-value]").disabled = !on.checked;
    line.classList.toggle("off", !on.checked);
  });
  document.addEventListener("click", ev => {
    const b = ev.target.closest ? ev.target.closest("[data-save-rules]") : null;
    if (!b) return;
    const note = document.getElementById("rules-msg");
    const rules = ruleLines().filter(l => l.querySelector("[data-on]").checked).map(l => {
      const v = l.querySelector("[data-value]").value;
      return {type: l.dataset.rule, [l.dataset.setting]: l.dataset.setting === "band" ? v : Number(v)};
    });
    b.disabled = true;
    api("POST", "/api/alerts/rules", {rules})
      .then(() => { note.textContent = "Saved."; return refresh(); })
      .catch(e => { note.textContent = e.message; b.disabled = false; });
  });

  // Dropping files anywhere on the bar adds them too.
  ["dragenter", "dragover"].forEach(t => bar.addEventListener(t, ev => { ev.preventDefault(); bar.classList.add("drop"); }));
  ["dragleave", "drop"].forEach(t => bar.addEventListener(t, ev => { ev.preventDefault(); bar.classList.remove("drop"); }));
  bar.addEventListener("drop", ev => upload(ev.dataTransfer.files));

  // polled: a timed check. It leaves an open schedule form alone, so what the
  // person is choosing isn't reset under them.
  async function refresh(polled, keepPage) {
    clearTimeout(timer);
    const formOpen = polled && showSchedule;
    try {
      state = await api("GET", "/api/state");
      if (version === null || (keepPage && !state.running)) version = state.version;
      // New scores, a finished run or a new layout: load the page again.
      if (state.version !== version && !state.running && !uploading && !formOpen) { location.reload(); return; }
      if (!formOpen) render();
    } catch (e) {
      if (!formOpen) bar.innerHTML = `<div class="msg err" role="status">The app is not answering. Is it still running? (${esc(e.message)})</div>`;
    }
    timer = setTimeout(() => refresh(true), state && state.running ? 2000 : 8000);
  }
  refresh();
})();
