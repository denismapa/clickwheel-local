// Shared helpers: API calls, toasts, formatting. Text only ever goes in through textContent.

export const $ = (id) => document.getElementById(id);

const TOAST_MS = 6000;

export class ApiError extends Error {
  constructor(info, status) {
    super(info.title);
    this.info = info;
    this.status = status;
  }
}

export async function api(path, { method = "GET", body, signal } = {}) {
  const init = { method, signal, headers: {} };
  if (body !== undefined) {
    init.headers["Content-Type"] = "application/json";
    init.body = JSON.stringify(body);
  }
  let response;
  try {
    response = await fetch(path, init);
  } catch (err) {
    if (err.name === "AbortError") throw err;
    throw new ApiError({ title: "SERVER LOST.", message: "Restart Clickwheel, then reload this page." }, 0);
  }
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    const info = data.error || { title: "SERVER ERROR.", message: `HTTP ${response.status}.` };
    throw new ApiError(info, response.status);
  }
  return data;
}

export function errorText(err, fallback) {
  return err.info ? `${err.info.title} ${err.info.message}` : `${fallback} ${err.message || ""}`.trim();
}

export function fmtDuration(seconds) {
  const total = Math.max(0, Math.round(seconds || 0));
  const h = Math.floor(total / 3600);
  const m = Math.floor((total % 3600) / 60);
  const s = total % 60;
  const mm = h ? String(m).padStart(2, "0") : String(m);
  return `${h ? `${h}:` : ""}${mm}:${String(s).padStart(2, "0")}`;
}

export function fmtBytes(bytes) {
  if (bytes >= 1e9) return [(bytes / 1e9).toFixed(2), "GB"];
  if (bytes >= 1e6) return [String(Math.round(bytes / 1e6)), "MB"];
  return [String(Math.max(1, Math.round(bytes / 1e3))), "KB"];
}

export function fmtSpeed(bytesPerSecond) {
  if (!bytesPerSecond) return "";
  const [n, unit] = fmtBytes(bytesPerSecond);
  return `${n} ${unit}/s`;
}

export function fmtDate(epochSeconds) {
  return new Date(epochSeconds * 1000).toLocaleDateString("sv-SE"); // YYYY-MM-DD, local time
}

export function node(tag, { cls, text, attrs } = {}, ...children) {
  const el = document.createElement(tag);
  if (cls) el.className = cls;
  if (text !== undefined) el.textContent = text;
  for (const [key, value] of Object.entries(attrs || {})) el.setAttribute(key, value);
  el.append(...children);
  return el;
}

export function reveal(section) {
  if (!section.hidden) return;
  section.hidden = false;
  section.classList.remove("enter");
  void section.offsetWidth; // restart the entrance animation
  section.classList.add("enter");
}

export function toast(kind, title, message) {
  const el = node("div", { cls: `toast toast-${kind}`, attrs: { role: kind === "danger" ? "alert" : "status" } },
    node("p", { cls: "eyebrow muted", text: title }),
    node("p", { text: message }));
  $("toasts").append(el);
  setTimeout(() => {
    el.classList.add("leaving");
    el.addEventListener("animationend", () => el.remove(), { once: true });
    setTimeout(() => el.remove(), 400);
  }, TOAST_MS);
}
