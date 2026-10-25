// Rescript Studio front end. Talks to app/server.py, which runs the same commands as the `rescript` CLI.
const $ = (id) => document.getElementById(id);
const api = async (path, body) => {
  const r = await fetch(path, body === undefined ? {} : { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify(body) });
  const j = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(j.error || `request failed (${r.status})`);
  return j;
};
// Round down, like the video players do, so the times on the page always agree with them.
const mmss = (s) => (s == null ? "–" : `${Math.floor(s / 60)}:${String(Math.floor(s % 60)).padStart(2, "0")}`);
const esc = (s) => s.replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));

let current = null;      // the recording on screen
let project = null;      // its /api/project data
let polling = null;

function show(view) {
  for (const v of ["home", "work", "result"]) $(`view-${v}`).hidden = v !== view;
  $("home-btn").hidden = view === "home";
  if (view === "home") loadHome();
}

function toast(msg, ms = 3200) {
  const t = $("toast"); t.textContent = msg; t.hidden = false;
  clearTimeout(t._h); t._h = setTimeout(() => (t.hidden = true), ms);
}

// ---------- home ----------

async function loadHome() {
  const [voices, recent] = await Promise.all([api("/api/voices"), api("/api/projects")]);
  const sel = $("voice"), keep = sel.value;
  sel.innerHTML = '<option value="">Clone it from this recording</option>' +
    voices.map((v) => `<option value="${esc(v)}">My saved voice: ${esc(v)}</option>`).join("");
  sel.value = voices.includes(keep) ? keep : (voices[0] || "");
  $("recent-box").hidden = !recent.length;
  $("recent").innerHTML = recent.map((p) => `<li data-name="${esc(p.name)}"><span>${esc(p.name)}</span>
    <span class="pill ${p.polished ? "done" : ""}">${p.polished ? "Polished" : "Not polished yet"}</span></li>`).join("");
  for (const li of $("recent").children) li.onclick = () => openProject(li.dataset.name);
}

function upload(file) {
  if (!/\.(mov|mp4|m4v)$/i.test(file.name)) return toast("Drop a .mov or .mp4 screen recording.");
  const xhr = new XMLHttpRequest();
  xhr.open("POST", "/api/upload");
  xhr.setRequestHeader("X-Filename", encodeURIComponent(file.name));
  $("upload").hidden = false;
  xhr.upload.onprogress = (e) => {
    const pct = e.lengthComputable ? Math.round((100 * e.loaded) / e.total) : 0;
    $("upload-bar").style.width = pct + "%"; $("upload-text").textContent = `Copying ${pct}%`;
  };
  xhr.onload = async () => {
    $("upload").hidden = true;
    const j = JSON.parse(xhr.responseText || "{}");
    if (xhr.status !== 200) return toast(j.error || "Upload failed");
    startPolish(j.name);
  };
  xhr.onerror = () => { $("upload").hidden = true; toast("Upload failed"); };
  xhr.send(file);
}

async function startPolish(name, extra = {}) {
  try {
    await api("/api/polish", { name, voice: $("voice").value, cursor: $("cursor").checked, ...extra });
    current = name; watch();
  } catch (e) { toast(e.message); }
}

const drop = $("drop");
drop.addEventListener("dragover", (e) => { e.preventDefault(); drop.classList.add("over"); });
drop.addEventListener("dragleave", () => drop.classList.remove("over"));
drop.addEventListener("drop", (e) => { e.preventDefault(); drop.classList.remove("over"); if (e.dataTransfer.files[0]) upload(e.dataTransfer.files[0]); });
$("file").onchange = (e) => e.target.files[0] && upload(e.target.files[0]);
$("home-btn").onclick = () => show("home");
$("fresh-btn").onclick = () => { $("fresh-btn").hidden = true; startPolish(current, { fresh: true }); };

// ---------- working ----------

function paintSteps(job) {
  $("step-cursor").hidden = job.stages < 7;
  for (const li of $("steps").children) {
    const st = li.dataset.stages.split(",").map(Number);
    const b = li.querySelector("b"); b.dataset.n ??= b.textContent;
    const done = job.stage > Math.max(...st) || (!job.busy && !job.error && job.stage >= Math.min(...st));
    const active = job.busy && st.includes(job.stage);
    li.classList.toggle("done", done && !active);
    li.classList.toggle("active", active);
    b.textContent = done && !active ? "✓" : b.dataset.n;
  }
}

const withTotal = (job) => (job.total && /^Spoke line \d+$/.test(job.detail) ? `${job.detail} of ${job.total}` : job.detail);

function watch() {
  clearInterval(polling);
  const tick = async () => {
    let job;
    try { job = await api("/api/job"); } catch { return; }
    if (!job.name) return;
    current = job.name;
    if (job.kind === "fix") return paintFix(job);
    if (!$("view-work").hidden || job.busy) {
      show("work");
      $("work-title").textContent = job.name;
      const fresh = (job.error || "").includes("--fresh");   // an old work folder belongs to another file
      $("work-detail").textContent = job.error ? "Something went wrong" : withTotal(job);
      $("work-time").textContent = job.elapsed ? `${mmss(job.elapsed)} so far` : "";
      $("work-log").textContent = job.log.join("\n");
      $("work-error").hidden = !job.error;
      $("work-error").textContent = fresh ? "An older project with the same name is in the way. Start over to polish this recording from the beginning." : job.error || "";
      $("fresh-btn").hidden = !fresh;
      document.querySelector(".status .spinner").hidden = !job.busy;
      paintSteps(job);
    }
    if (!job.busy) {
      clearInterval(polling);
      if (!job.error) { await openProject(job.name); toast(job.kind === "cursor" ? "Cursor removed" : `Done in ${mmss(job.elapsed)}`); }
    }
  };
  tick(); polling = setInterval(tick, 700);
}

// ---------- result ----------

async function openProject(name) {
  current = name;
  project = await api(`/api/project?name=${encodeURIComponent(name)}`);
  if (!project.polished) { show("home"); return startPolish(name); }
  show("result");
  $("res-title").textContent = name.replace(/\.(mov|mp4|m4v)$/i, "");
  const s = project.stats || {};
  // the percentage comes from the rounded times on screen, so anyone checking 0:50 -> 0:19 gets the same number
  const pct = s.before_s && s.after_s ? Math.round(100 * (1 - Math.floor(s.after_s) / Math.floor(s.before_s))) : null;
  $("chips").innerHTML = [
    `<span class="chip good">Length <b>${mmss(s.before_s)} → ${mmss(s.after_s)}</b>${pct != null ? ` (${pct}% shorter)` : ""}</span>`,
    `<span class="chip">Words <b>${s.words_before} → ${s.words_after}</b></span>`,
    `<span class="chip">Long pauses removed <b>${s.long_pauses}</b> (${s.long_pause_s} s)</span>`,
    s.suspects ? `<span class="chip">Voice check <b>${s.suspects} to review</b></span>`
               : `<span class="chip good">Voice check <b>all ${s.lines} lines ✓</b></span>`,
    `<span class="chip">Retakes <b>0</b></span>`,
  ].join("");
  $("cap-before").textContent = mmss(s.before_s);
  $("cap-after").textContent = mmss(s.after_s);
  $("clean-toggle").hidden = !project.clean;
  $("cursor-btn").hidden = project.clean;
  loadVideos();
  renderLines();
}

function loadVideos(seek) {
  const v = Date.now(), n = encodeURIComponent(current);
  $("before").src = `/media?name=${n}&which=original&v=${v}`;
  const which = project.clean && $("show-clean").checked ? "clean" : "polished";
  const after = $("after");
  after.src = `/media?name=${n}&which=${which}&v=${v}`;
  if (seek != null) after.addEventListener("loadedmetadata", () => { after.currentTime = seek; after.play(); }, { once: true });
}
$("show-clean").onchange = () => loadVideos($("after").currentTime);

function renderLines() {
  $("lines").innerHTML = project.lines.map((l) => `
    <li data-i="${l.i}">
      <button class="t" title="Play this line">${mmss(l.start)}</button>
      <div class="body">
        <div class="text">${esc(l.text)}</div>
        ${l.suspect ? '<div class="warn">The voice check heard this line differently. Give it a listen.</div>' : ""}
        ${l.said ? `<div class="said">${esc(l.said)}</div>` : ""}
      </div>
      <div class="row-actions"><button data-act="edit">Edit</button><button data-act="ask">Ask for a change</button></div>
    </li>`).join("");
  for (const li of $("lines").children) {
    const l = project.lines[+li.dataset.i];
    const play = () => { const a = $("after"); a.currentTime = l.start + 0.01; a.play(); };
    li.querySelector(".t").onclick = play;
    li.querySelector(".text").onclick = play;
    li.querySelector('[data-act="edit"]').onclick = () => editLine(li, l, false);
    li.querySelector('[data-act="ask"]').onclick = () => editLine(li, l, true);
  }
}

function editLine(li, l, ask) {
  const body = li.querySelector(".body");
  body.innerHTML = ask
    ? `<div class="text">${esc(l.text)}</div><input class="ask" placeholder="For example: say it more simply, or spell out the number">
       <div class="editbar"><button class="primary">Change and re-speak</button><button>Cancel</button></div>`
    : `<textarea rows="2">${esc(l.text)}</textarea>
       <div class="editbar"><button class="primary">Re-speak this line</button><button>Cancel</button></div>`;
  const field = body.querySelector(ask ? "input" : "textarea");
  field.focus();
  const [go, cancel] = body.querySelectorAll(".editbar button");
  cancel.onclick = renderLines;
  const submit = async () => {
    const val = field.value.trim();
    if (!val) return;
    try {
      await api("/api/line", ask ? { name: current, i: l.i, change: val } : { name: current, i: l.i, text: val });
      li.classList.add("working"); watch();
    } catch (e) { toast(e.message); }
  };
  go.onclick = submit;
  field.onkeydown = (e) => { if (e.key === "Enter" && (ask || e.metaKey)) { e.preventDefault(); submit(); } };
}

function paintFix(job) {
  if ($("view-result").hidden) return;
  $("busy-line").hidden = !job.busy;
  $("busy-text").textContent = `Redoing line ${job.line + 1}: ${job.detail.replace(/^Spoke line \d+$/, "spoken, now re-cutting the video")}`;
  for (const b of document.querySelectorAll(".row-actions button")) b.disabled = job.busy;
  if (!job.busy) {
    clearInterval(polling);
    if (job.error) return toast(job.error, 6000);
    openProject(current).then(() => { loadVideos(project.lines[job.line].start); toast(`Line ${job.line + 1} redone`); });
  }
}

// Highlight the line being spoken while the polished video plays.
$("after").addEventListener("timeupdate", () => {
  if (!project) return;
  const t = $("after").currentTime;
  for (const li of $("lines").children) {
    const l = project.lines[+li.dataset.i];
    li.classList.toggle("playing", t >= l.start && t < l.start + l.dur);
  }
});

$("reveal").onclick = () => api("/api/reveal", { name: current }).catch((e) => toast(e.message));
$("cursor-btn").onclick = async () => {
  try { await api("/api/cursor", { name: current }); watch(); } catch (e) { toast(e.message); }
};
$("save-voice").onclick = async () => {
  const voice = prompt("Name this voice (for example, your first name):");
  if (!voice) return;
  try { await api("/api/save-voice", { name: current, voice }); toast(`Saved. Next time pick "My saved voice: ${voice}".`); }
  catch (e) { toast(e.message); }
};

// On load: if a job is running (the window was closed and reopened), go straight back to it.
(async () => {
  show("home");
  const job = await api("/api/job").catch(() => ({}));
  if (job.busy) watch();
})();
