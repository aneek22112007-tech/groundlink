import { telemetryAt } from "./state.js";

const fmtClock = (s) => {
  const m = Math.floor(s / 60), r = Math.floor(s % 60);
  return `${String(m).padStart(2, "0")}:${String(r).padStart(2, "0")}`;
};

export function mountHud(root, reduced) {
  const $ = (id) => root.getElementById(id);
  const el = { bus: $("t-bus"), soc: $("t-soc"), att: $("t-att"), rpm: $("t-rpm"), comms: $("t-comms"), fuel: $("t-fuel"), state: $("hud-state"), pass: $("hud-pass") };
  const trace = $("trace");
  const ctx = trace.getContext("2d");
  const hist = [];
  const start = performance.now();
  let lastTick = -1;

  const draw = () => {
    const dpr = Math.min(devicePixelRatio || 1, 2);
    const w = trace.clientWidth, h = trace.clientHeight;
    if (trace.width !== Math.round(w * dpr)) { trace.width = Math.round(w * dpr); trace.height = Math.round(h * dpr); }
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.clearRect(0, 0, w, h);
    ctx.strokeStyle = "rgba(148,178,255,.12)"; ctx.lineWidth = 1;
    for (let i = 1; i < 4; i++) { ctx.beginPath(); ctx.moveTo(0, (h * i) / 4); ctx.lineTo(w, (h * i) / 4); ctx.stroke(); }
    // survival floor reference ~ 24.8 V
    const y = (v) => h - ((v - 24.6) / (28.4 - 24.6)) * h;
    ctx.setLineDash([4, 4]); ctx.strokeStyle = "rgba(255,93,108,.45)";
    ctx.beginPath(); ctx.moveTo(0, y(24.8)); ctx.lineTo(w, y(24.8)); ctx.stroke(); ctx.setLineDash([]);
    if (hist.length < 2) return;
    const step = w / 119;
    ctx.lineWidth = 2;
    for (let i = 1; i < hist.length; i++) {
      ctx.strokeStyle = hist[i].alert ? "#ff5d6c" : "#5eead4";
      ctx.beginPath(); ctx.moveTo((i - 1) * step, y(hist[i - 1].bus)); ctx.lineTo(i * step, y(hist[i].bus)); ctx.stroke();
    }
    ctx.fillStyle = "rgba(138,151,180,.9)"; ctx.font = "10px JetBrains Mono, monospace";
    ctx.fillText("BUS V", 4, 11); ctx.fillText("survival floor", w - 92, y(24.8) - 4);
  };

  const tick = () => {
    const t = (performance.now() - start) / 1000;
    const v = telemetryAt(t);
    const alert = v.phase === "anomaly";
    el.bus.textContent = v.bus.toFixed(2);
    el.soc.textContent = v.soc.toFixed(0);
    el.att.textContent = v.att.toFixed(2);
    el.rpm.textContent = v.rpm.toFixed(0);
    el.comms.textContent = v.comms;
    el.fuel.textContent = v.fuel.toFixed(3);
    for (const k of ["bus", "att", "comms"]) el[k].classList.toggle("alert", alert || (k === "comms" && v.comms !== "nominal"));
    const label = { nominal: "NOMINAL", anomaly: "ANOMALY", burn: "AUTHORIZED · BURN", recovering: "RECOVERING" }[v.phase];
    el.state.textContent = label;
    el.state.className = "badge mono" + (alert ? " alert" : v.phase === "burn" ? " warn" : "");
    el.pass.textContent = v.passOpen ? "PASS 3 OPEN · BENGALURU · MAX ELEV 69°" : `AOS BENGALURU T−${fmtClock(v.aosIn)}`;
    const tick10 = Math.floor(t * 4);
    if (tick10 !== lastTick) { lastTick = tick10; hist.push({ bus: v.bus, alert }); if (hist.length > 120) hist.shift(); }
    draw();
  };

  if (reduced) {
    for (let i = 0; i < 120; i++) { const v = telemetryAt(i * 0.12 + 4); hist.push({ bus: v.bus, alert: v.phase === "anomaly" }); }
    tick();
    return;
  }
  // prefill so the chart is never empty
  for (let i = 0; i < 40; i++) hist.push({ bus: telemetryAt(0).bus + Math.sin(i) * 0.02, alert: false });
  const loop = () => { if (!document.hidden) tick(); requestAnimationFrame(loop); };
  requestAnimationFrame(loop);
}

const ROLE = {
  context_agent: ["C", "a-context"], options_agent: ["O", "a-options"], action_agent: ["A", "a-action"],
  flight_ops_engineer: ["P", "a-human"], mission_director: ["A", "a-human2"],
};
const esc = (s) => String(s).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" })[c]);

function lineEl(line) {
  const [ini, cls] = ROLE[line.role] || [line.who?.[0] || "?", "a-human"];
  const human = !line.role.endsWith("_agent");
  const kind = /^Authorized|^Confirmed/.test(line.text) ? " auth" : /^TRANSMITTED|^CONFIRMED/.test(line.text) ? " tx" : /^ROLLBACK|lost/i.test(line.text) ? " alertl" : "";
  const div = document.createElement("div");
  div.className = "line" + (human ? " human" : "") + kind;
  const ini2 = line.who === "Arjun Mehta" ? "AM" : line.who === "Priya Raman" ? "PR" : ini;
  div.innerHTML = `<span class="avatar ${cls}">${esc(ini2)}</span><div class="body glass"><div class="meta"><b>${esc(line.who)}</b><span class="role mono">${esc(line.role)}</span><time class="mono">${esc(line.ts.slice(11, 19))} UTC</time></div><pre>${esc(line.text)}</pre></div>`;
  return div;
}

export async function mountReplay(root) {
  const log = root.getElementById("replay-log");
  const bar = root.getElementById("r-bar");
  const playBtn = root.getElementById("r-play");
  let data;
  try {
    data = await (await fetch("replay.json")).json();
  } catch {
    log.innerHTML = '<p class="empty">Replay log could not be loaded.</p>';
    return;
  }
  const lines = data.lines;
  let i = 0, timer = null;
  const render = () => { bar.style.width = `${(i / lines.length) * 100}%`; playBtn.textContent = timer ? "❚❚ Pause" : i >= lines.length ? "↻ Replay" : "▶ Play"; };
  const step = () => {
    if (i >= lines.length) { stop(); return false; }
    log.appendChild(lineEl(lines[i++]));
    log.scrollTop = log.scrollHeight;
    render();
    return true;
  };
  const stop = () => { clearInterval(timer); timer = null; render(); };
  const reset = () => { stop(); i = 0; log.innerHTML = ""; render(); };
  const play = () => {
    if (timer) return stop();
    if (i >= lines.length) reset();
    step();
    timer = setInterval(() => { if (!step()) stop(); }, 1500);
    render();
  };
  playBtn.addEventListener("click", play);
  root.getElementById("r-step").addEventListener("click", () => { stop(); step(); });
  root.getElementById("r-all").addEventListener("click", () => { stop(); while (step()); });
  root.getElementById("r-reset").addEventListener("click", reset);
  // first three messages visible so the room is never empty
  for (let k = 0; k < 3; k++) step();
  render();
  let autoplayed = false;
  new IntersectionObserver(([e]) => {
    if (e.isIntersecting && !autoplayed && !matchMedia("(prefers-reduced-motion: reduce)").matches) { autoplayed = true; play(); }
  }, { threshold: 0.4 }).observe(log);
  root.querySelectorAll("[data-play]").forEach((a) => a.addEventListener("click", () => { autoplayed = true; if (!timer) { reset(); play(); } }));

  // audit chain from real row hashes
  const chain = root.getElementById("chain");
  const pick = lines.filter((l) => /^CONTEXT|^OPTIONS v2|^Authorized|^Confirmed|fire_pulse|^CONFIRMED/.test(l.text)).slice(0, 6);
  pick.forEach((l, n) => {
    const li = document.createElement("li");
    const what = l.text.split("\n")[0].replace(/\{.*$/, "").trim();
    li.innerHTML = `<span class="who">${esc(l.who)} · ${esc(l.ts.slice(11, 19))}</span><span class="what">${esc(what)}</span><span class="h">${esc((l.hash || "").slice(0, 12))}…</span>`;
    li.style.transitionDelay = `${n * 120}ms`;
    chain.appendChild(li);
  });
  root.getElementById("chain-ok").textContent = data.chain_ok ? `✓ chain verified on export · mission ${data.mission_status}` : "";
  new IntersectionObserver(([e]) => { if (e.isIntersecting) chain.querySelectorAll("li").forEach((li) => li.classList.add("in")); }, { threshold: 0.2 }).observe(chain);
}

export function mountGate(root) {
  const out = root.getElementById("sign-out"), card = root.getElementById("opt-b");
  const set = (cls, html) => { out.className = "sign-out mono " + cls; out.innerHTML = html; };
  root.getElementById("sign-observer").addEventListener("click", () => {
    card.classList.remove("signed");
    set("refused", "observer: “Authorized — Option B” → <b>refused</b>. Only mission_director can authorise an IRREVERSIBLE command. Sequence stays awaiting_auth.");
  });
  root.getElementById("sign-director").addEventListener("click", () => {
    card.classList.add("signed");
    set("ok", "Arjun Mehta (mission_director): “Authorized — Option B, firing on pass 3, I am taking command responsibility” → <b>approval recorded</b>. Priya confirms. arm_rcs → fire_pulse → verify_rate → restore_downlink.");
  });
  root.getElementById("sign-reset").addEventListener("click", () => {
    card.classList.remove("signed");
    set("", "Command sequence for B: <b>awaiting_auth</b>. Nothing transmits without a signed statement.");
  });
}

export function mountChrome(root) {
  const nav = root.getElementById("nav");
  const onScroll = () => nav.classList.toggle("scrolled", scrollY > 20);
  addEventListener("scroll", onScroll, { passive: true }); onScroll();
  const links = [...root.querySelectorAll(".nav nav a")];
  const io = new IntersectionObserver((es) => es.forEach((e) => {
    if (e.isIntersecting) links.forEach((a) => a.classList.toggle("active", a.getAttribute("href") === "#" + e.target.id));
  }), { rootMargin: "-45% 0px -50% 0px" });
  links.forEach((a) => { const s = root.querySelector(a.getAttribute("href")); if (s) io.observe(s); });
  const rv = new IntersectionObserver((es) => es.forEach((e) => { if (e.isIntersecting) { e.target.classList.add("in"); rv.unobserve(e.target); } }), { threshold: 0.15 });
  root.querySelectorAll(".reveal").forEach((el) => rv.observe(el));
  const off = root.getElementById("ks-off");
  new IntersectionObserver(([e]) => { if (e.isIntersecting) { off.classList.add("glitching"); setTimeout(() => off.classList.remove("glitching"), 1400); } }, { threshold: 0.5 }).observe(off);
  root.getElementById("copy").addEventListener("click", async (e) => {
    try { await navigator.clipboard.writeText(root.getElementById("code").textContent); e.target.textContent = "Copied"; }
    catch { e.target.textContent = "Select & copy"; }
    setTimeout(() => (e.target.textContent = "Copy"), 1600);
  });
}
