// Clickwheel UI: paste a link, read the source, download, save to the device.
// All text reaches the page through textContent; nothing is parsed as HTML.

import { $, api, fmtBytes, fmtDuration, fmtSpeed, node, reveal, toast } from "./core.js";

const ui = {
  intro: $("intro"), wm: $("wm"), engine: $("engine"),
  form: $("source-form"), url: $("url"), field: $("url-field"), caption: $("url-caption"),
  go: $("go"), cancel: $("cancel"), reset: $("reset"), split: $("split"),
  tabs: [...document.querySelectorAll("[data-mode]")],
  specNum: $("spec-num"), specLabel: $("spec-label"),
  mix: $("mix"), mixTitle: $("mix-title"), mixMeta: $("mix-meta"), cover: $("cover"),
  tDuration: $("t-duration"), tTracks: $("t-tracks"), tTracksCap: $("t-tracks-cap"),
  tSource: $("t-source"), tSourceCap: $("t-source-cap"), tSize: $("t-size"), tSizeCap: $("t-size-cap"),
  trackRows: $("track-rows"),
  run: $("run"), runTitle: $("run-title"), runName: $("run-name"), runNum: $("run-num"),
  runDetail: $("run-detail"), runStats: $("run-stats"),
  sectors: [$("s1"), $("s2"), $("s3")], sectorLabels: [$("s1-label"), $("s2-label"), $("s3-label")],
  runError: $("run-error"), runErrorTitle: $("run-error-title"), runErrorMessage: $("run-error-message"),
  runErrorMore: $("run-error-more"), runErrorDetail: $("run-error-detail"),
  log: $("log"), logRows: $("log-rows"),
  engEncoder: $("eng-encoder"), engYtdlp: $("eng-ytdlp"), footVersion: $("foot-version"),
};

const DEFAULT_CAPTION = "Videos and mixes. Chapters become tracks.";
const LOOKS_LIKE_YOUTUBE = /(^|\/\/|\.)(youtube\.com|youtu\.be|youtube-nocookie\.com)\//i;
const STAGE_TITLES = { queued: "Queued", fetch: "Fetch", encode: "Encode", pack: "Pack", done: "Done", error: "Stopped", cancelled: "Cancelled" };
const SPEC = {
  aac: { num: "256", label: "kbps · Apple AAC-LC", name: "AAC 256" },
  alac: { num: "16", label: "bit · Apple Lossless", name: "ALAC" },
};
const POLL_MS = 400;
const READ_DELAY_MS = 450;

const state = {
  phase: "idle", // idle | reading | ready | running | done | failed
  mode: "aac",
  split: true,
  preview: null,
  previewFor: "",
  job: null,
  reader: null,
  readTimer: 0,
  pollTimer: 0,
  logged: new Set(),
};

// ---------- preferences (per-viewer convenience only)

function loadPrefs() {
  try {
    const saved = JSON.parse(localStorage.getItem("clickwheel:prefs") || "{}");
    if (saved.mode in SPEC) state.mode = saved.mode;
    if (typeof saved.split === "boolean") state.split = saved.split;
  } catch { /* storage unavailable: defaults stand */ }
}

function savePrefs() {
  try {
    localStorage.setItem("clickwheel:prefs", JSON.stringify({ mode: state.mode, split: state.split }));
  } catch { /* ignore */ }
}

// ---------- controls

function setPhase(phase) {
  state.phase = phase;
  const running = phase === "running";
  ui.url.disabled = running;
  ui.split.disabled = running;
  ui.tabs.forEach((tab) => { tab.disabled = running; });
  ui.cancel.hidden = !running;
  ui.go.hidden = running;
  ui.reset.hidden = !(phase === "done" || phase === "failed");
  ui.go.disabled = !(phase === "ready" || phase === "done" || phase === "failed");
  ui.go.textContent = { done: "Save file", failed: "Retry", reading: "Reading" }[phase] || "Download";
}

function setCaption(text, invalid = false) {
  ui.caption.textContent = text;
  ui.field.classList.toggle("invalid", invalid);
}

function renderMode() {
  ui.tabs.forEach((tab) => tab.setAttribute("aria-selected", String(tab.dataset.mode === state.mode)));
  ui.specNum.textContent = SPEC[state.mode].num;
  ui.specLabel.textContent = SPEC[state.mode].label;
  ui.split.checked = state.split;
  if (state.preview) renderPreviewNumbers();
}

// ---------- read the source

function scheduleRead() {
  clearTimeout(state.readTimer);
  const value = ui.url.value.trim();
  if (value === state.previewFor && state.preview) return;
  state.reader?.abort();
  state.preview = null;
  state.previewFor = "";
  ui.mix.hidden = true;
  setPhase("idle");
  if (!value) {
    setCaption(DEFAULT_CAPTION);
    return;
  }
  if (LOOKS_LIKE_YOUTUBE.test(value)) {
    state.readTimer = setTimeout(readSource, READ_DELAY_MS);
  } else {
    setCaption(DEFAULT_CAPTION);
  }
}

async function readSource() {
  clearTimeout(state.readTimer);
  const value = ui.url.value.trim();
  if (!value) return;
  state.reader?.abort();
  const reader = new AbortController();
  state.reader = reader;
  setPhase("reading");
  setCaption("Reading source.");
  try {
    const preview = await api("/api/analyze", { method: "POST", body: { url: value }, signal: reader.signal });
    if (reader.signal.aborted) return;
    state.preview = preview;
    state.previewFor = value;
    renderPreview();
    setCaption(`${preview.source.codec} ${preview.source.kbps} kbps source. Ready.`);
    setPhase("ready");
  } catch (err) {
    if (err.name === "AbortError") return;
    const info = err.info || { title: "READ FAILED.", message: String(err) };
    setCaption(`${info.title} ${info.message}`, true);
    setPhase("idle");
  }
}

function previewTracks() {
  const p = state.preview;
  if (state.split && p.tracks.length) return p.tracks;
  return [{ number: 1, title: p.single.title, artist: p.single.artist, duration: p.duration }];
}

function renderPreview() {
  const p = state.preview;
  ui.mixTitle.textContent = p.title;
  ui.mixMeta.textContent = [p.channel, p.year].filter(Boolean).join(" · ");
  if (p.thumbnail) {
    ui.cover.src = p.thumbnail;
    ui.cover.hidden = false;
  } else {
    ui.cover.removeAttribute("src");
    ui.cover.hidden = true;
  }
  ui.tDuration.textContent = fmtDuration(p.duration);
  ui.tSource.textContent = String(p.source.kbps);
  ui.tSourceCap.textContent = `kbps ${p.source.codec} · ${p.source.khz} kHz`;
  renderPreviewNumbers();
  reveal(ui.mix);
}

function renderPreviewNumbers() {
  const p = state.preview;
  const tracks = previewTracks();
  ui.tTracks.textContent = String(tracks.length);
  ui.tTracksCap.textContent = p.tracks.length
    ? (state.split ? "Chapters as tracks" : "Split off · one file")
    : "No chapters · one file";
  const [size, unit] = fmtBytes(p.estimate[state.mode]);
  ui.tSize.textContent = size;
  ui.tSizeCap.textContent = `${unit} est. · ${SPEC[state.mode].name}`;
  ui.trackRows.replaceChildren(...tracks.map((t) => node("tr", {},
    node("td", { cls: "num", text: String(t.number).padStart(2, "0") }),
    node("td", { text: t.title }),
    node("td", { text: t.artist }),
    node("td", { cls: "num", text: fmtDuration(t.duration) }))));
}

// ---------- run a job

async function startJob() {
  if (!state.preview) return;
  setPhase("running");
  try {
    const job = await api("/api/jobs", {
      method: "POST",
      body: { url: state.preview.url, mode: state.mode, split: state.split },
    });
    trackJob(job);
  } catch (err) {
    toast("danger", err.info?.title || "START FAILED.", err.info?.message || String(err));
    setPhase("ready");
  }
}

function trackJob(job) {
  state.job = job;
  ui.runError.hidden = true;
  ui.runName.textContent = job.title || state.preview?.title || job.url;
  reveal(ui.run);
  renderRun(job);
  setPhase("running");
  clearTimeout(state.pollTimer);
  state.pollTimer = setTimeout(poll, POLL_MS);
}

async function poll() {
  const id = state.job?.id;
  if (!id) return;
  try {
    const job = await api(`/api/jobs/${id}`);
    state.job = job;
    renderRun(job);
    if (job.state === "done") return finished(job);
    if (job.state === "error") return failed(job);
    if (job.state === "cancelled") return cancelled();
  } catch (err) {
    if (err.status === 401) return; // signed out: the access view has taken over
    if (err.status === 404) return failed({ error: err.info });
    ui.runStats.textContent = "Server not answering. Retrying.";
  }
  state.pollTimer = setTimeout(poll, POLL_MS);
}

function renderRun(job) {
  const pct = Math.floor((job.progress || 0) * 100);
  ui.runNum.textContent = `${pct}%`;
  ui.runNum.setAttribute("aria-valuenow", String(pct));
  ui.runTitle.textContent = STAGE_TITLES[job.state] || job.state;
  if (job.title) ui.runName.textContent = job.title;
  ui.runDetail.textContent = job.detail || "";
  const stats = [];
  if (job.state === "fetch" && job.speed) stats.push(fmtSpeed(job.speed));
  if (job.state === "fetch" && Number.isFinite(job.eta)) stats.push(`${fmtDuration(job.eta)} left`);
  if (job.result) stats.push(`${job.result.tracks} ${job.result.tracks === 1 ? "track" : "tracks"}`, fmtBytes(job.result.size).join(" "));
  ui.runStats.textContent = stats.join(" · ");
  const active = { fetch: 0, encode: 1, pack: 2 }[job.state];
  job.sectors.forEach((fraction, i) => {
    ui.sectors[i].style.setProperty("--f", `${Math.round(fraction * 1000) / 10}%`);
    ui.sectorLabels[i].classList.toggle("on", i === active);
    ui.sectorLabels[i].classList.toggle("done", fraction >= 1 && i !== active);
  });
}

function finished(job) {
  saveFile(job.id);
  const [size, unit] = fmtBytes(job.result.size);
  toast("success", "Saved", `${job.result.tracks} ${job.result.tracks === 1 ? "track" : "tracks"} · ${size} ${unit}. Check Downloads.`);
  addLog(job);
  setPhase("done");
}

function failed(job) {
  const error = job.error || { title: "JOB FAILED.", message: "No detail from the server." };
  ui.runErrorTitle.textContent = error.title;
  ui.runErrorMessage.textContent = error.message;
  ui.runErrorDetail.textContent = error.detail || "";
  ui.runErrorMore.hidden = !error.detail;
  ui.runError.hidden = false;
  ui.runTitle.textContent = STAGE_TITLES.error;
  setPhase("failed");
}

function cancelled() {
  ui.runTitle.textContent = STAGE_TITLES.cancelled;
  ui.runDetail.textContent = "Stopped. Files discarded.";
  ui.runStats.textContent = "";
  setPhase(state.preview ? "ready" : "idle");
}

function saveFile(id) {
  const link = node("a", { attrs: { href: `/api/jobs/${id}/file`, download: "" } });
  document.body.append(link);
  link.click();
  link.remove();
}

function addLog(job) {
  if (!job.result || state.logged.has(job.id)) return;
  state.logged.add(job.id);
  const [size, unit] = fmtBytes(job.result.size);
  const save = node("a", { cls: "btn btn-ghost btn-sm log-save", text: "Save", attrs: { href: `/api/jobs/${job.id}/file`, download: "" } });
  ui.logRows.prepend(node("tr", {},
    node("td", { text: job.result.filename }),
    node("td", {}, node("span", { cls: "badge badge-silver badge-sq", text: SPEC[job.mode]?.name || job.mode })),
    node("td", { cls: "num", text: String(job.result.tracks) }),
    node("td", { cls: "num", text: `${size} ${unit}` }),
    node("td", { cls: "num" }, save)));
  reveal(ui.log);
}

function clearRun() {
  clearTimeout(state.pollTimer);
  clearTimeout(state.readTimer);
  state.reader?.abort();
  state.job = null;
  state.preview = null;
  state.previewFor = "";
  ui.url.value = "";
  ui.mix.hidden = true;
  ui.run.hidden = true;
  setCaption(DEFAULT_CAPTION);
  setPhase("idle");
}

// ---------- signed in or out

async function openApp() {
  ui.intro.hidden = false;
  ui.wm.textContent = "01";
  ui.engine.hidden = false;
  try {
    const info = await api("/api/info");
    ui.engEncoder.textContent = info.aac_encoder === "aac_at" ? "Apple AAC" : "ffmpeg AAC";
    ui.engYtdlp.textContent = `yt-dlp ${info.yt_dlp}`;
    ui.footVersion.textContent = `v${info.version} · yt-dlp ${info.yt_dlp} · ffmpeg ${info.ffmpeg}`;
    if (!info.js_runtime) {
      ui.engYtdlp.className = "badge badge-danger badge-sq";
      toast("danger", "NO JAVASCRIPT RUNTIME.", "YouTube needs one. Run: brew install deno");
    }
    const jobs = await api("/api/jobs");
    jobs.filter((j) => j.state === "done").reverse().forEach(addLog);
    const live = jobs.find((j) => !["done", "error", "cancelled"].includes(j.state));
    if (live) trackJob(live);
  } catch (err) {
    if (err.status !== 401) toast("danger", err.info?.title || "SERVER LOST.", err.info?.message || String(err));
  }
  if (!state.job) ui.url.focus();
}

function closeApp() {
  clearRun();
  ui.intro.hidden = true;
  ui.engine.hidden = true;
  ui.log.hidden = true;
  ui.logRows.replaceChildren();
  state.logged.clear();
  ui.wm.textContent = "00";
}

// ---------- events

ui.url.addEventListener("input", scheduleRead);
ui.url.addEventListener("paste", () => setTimeout(() => {
  if (ui.url.value.trim() !== state.previewFor) readSource();
}, 0));
// Enter reads the link; the form's own submit is blocked while DOWNLOAD is disabled.
ui.url.addEventListener("keydown", (event) => {
  if (event.key === "Enter" && state.phase === "idle") {
    event.preventDefault();
    readSource();
  }
});

ui.form.addEventListener("submit", (event) => {
  event.preventDefault();
  if (state.phase === "done" && state.job) return saveFile(state.job.id);
  if (state.phase === "ready" || state.phase === "failed") return startJob();
  if (state.phase === "idle" && ui.url.value.trim()) return readSource();
});

ui.cancel.addEventListener("click", async () => {
  if (!state.job) return;
  ui.cancel.disabled = true;
  try {
    await api(`/api/jobs/${state.job.id}`, { method: "DELETE" });
  } catch (err) {
    toast("danger", err.info?.title || "CANCEL FAILED.", err.info?.message || String(err));
  } finally {
    ui.cancel.disabled = false;
  }
});

ui.reset.addEventListener("click", () => {
  clearRun();
  ui.url.focus();
});

// A new format or split choice after a finished run offers DOWNLOAD again.
function optionsChanged() {
  savePrefs();
  renderMode();
  if ((state.phase === "done" || state.phase === "failed") && state.preview) setPhase("ready");
}

ui.tabs.forEach((tab) => tab.addEventListener("click", () => {
  state.mode = tab.dataset.mode;
  optionsChanged();
}));

ui.tabs.forEach((tab, i) => tab.addEventListener("keydown", (event) => {
  if (event.key !== "ArrowRight" && event.key !== "ArrowLeft") return;
  const next = ui.tabs[(i + (event.key === "ArrowRight" ? 1 : ui.tabs.length - 1)) % ui.tabs.length];
  next.focus();
  next.click();
}));

ui.split.addEventListener("change", () => {
  state.split = ui.split.checked;
  optionsChanged();
});

ui.cover.addEventListener("error", () => { ui.cover.hidden = true; });

// ---------- boot

async function boot() {
  loadPrefs();
  renderMode();
  setPhase("idle");
  try {
    await openApp();
  } catch (err) {
    toast("danger", err.info?.title || "SERVER LOST.", err.info?.message || String(err));
  }
}

boot();
