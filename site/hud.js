const series = [28.1, 27.9, 27.6, 27.2, 26.4, 25.1, 24.4, 23.8, 24.6, 26.2, 27.4];

export function mountHud(root) {
  const canvas = root.querySelector("#trace");
  const readouts = root.querySelector("#readouts");
  const reduce = matchMedia("(prefers-reduced-motion: reduce)").matches;
  let frame = 0;

  function draw(index) {
    const ctx = canvas.getContext("2d");
    const w = canvas.width;
    const h = canvas.height;
    ctx.clearRect(0, 0, w, h);
    ctx.strokeStyle = "#9af6ff";
    ctx.lineWidth = 2;
    ctx.beginPath();
    series.forEach((volts, i) => {
      const x = (i / (series.length - 1)) * (w - 12) + 6;
      const y = h - 8 - ((volts - 22) / 8) * (h - 16);
      if (i === 0) ctx.moveTo(x, y);
      else ctx.lineTo(x, y);
    });
    ctx.stroke();
    const shown = series[Math.min(series.length - 1, index)];
    readouts.textContent = `BUS ${shown.toFixed(2)} V   ATT ${((index % 5) * 0.8).toFixed(2)} deg   SOC ${Math.max(40, 70 - index).toFixed(0)}%`;
  }

  draw(reduce ? series.length - 1 : 0);
  if (reduce) return;
  const timer = setInterval(() => {
    frame = (frame + 1) % series.length;
    draw(frame);
  }, 900);
  return () => clearInterval(timer);
}

export function mountReplay(node) {
  fetch("./replay.json")
    .then((response) => response.json())
    .then((log) => {
      const lines = log.lines || [];
      node.innerHTML = lines
        .map(
          (line) =>
            `<div class="glass" style="margin-bottom:8px"><b>${line.who}</b> <span class="hash">${line.ts}</span><div class="mono">${escape(line.text)}</div></div>`,
        )
        .join("");
    })
    .catch(() => {
      node.textContent = "Replay log is not beside this page.";
    });
}

function escape(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;");
}

const sound = document.querySelector("#sound");
let audio = null;
sound?.addEventListener("click", () => {
  const on = sound.getAttribute("aria-pressed") !== "true";
  sound.setAttribute("aria-pressed", on ? "true" : "false");
  sound.textContent = on ? "Sound on" : "Sound off";
  if (!on) {
    audio?.suspend();
    return;
  }
  const Context = window.AudioContext || window.webkitAudioContext;
  if (!Context) return;
  audio = audio || new Context();
  audio.resume();
  const osc = audio.createOscillator();
  const gain = audio.createGain();
  osc.frequency.value = 440;
  gain.gain.value = 0.02;
  osc.connect(gain).connect(audio.destination);
  osc.start();
  osc.stop(audio.currentTime + 0.08);
});
