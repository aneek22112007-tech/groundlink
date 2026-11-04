// One looping, deterministic Kestrel-7 timeline shared by the 3D scene and the HUD.
// Phases mirror the repo's scenario: nominal -> missed downlink -> pass + authorised burn -> recovering.
export const CYCLE = 32;
export const PHASES = [
  { id: "nominal", until: 7 },
  { id: "anomaly", until: 19 },
  { id: "burn", until: 23 },
  { id: "recovering", until: CYCLE },
];

export function phaseAt(t) {
  const s = ((t % CYCLE) + CYCLE) % CYCLE;
  let start = 0;
  for (const p of PHASES) {
    if (s < p.until) return { id: p.id, k: (s - start) / (p.until - start), s };
    start = p.until;
  }
  return { id: "nominal", k: 0, s };
}

const lerp = (a, b, k) => a + (b - a) * k;

// Values are anchored to demo log figures: bus 28.1 -> ~25.4 V, attitude 0.25 -> ~40 deg,
// fuel 4.200 -> 4.004 kg after the fuel-saving pulse, recovered at 0.01 deg.
export function telemetryAt(t) {
  const { id, k, s } = phaseAt(t);
  const n = Math.sin(t * 7.3) * 0.5 + Math.sin(t * 2.1) * 0.5;
  let bus = 28.1, soc = 72, att = 0.25, rpm = 1100, comms = "nominal", fuel = 4.2;
  if (id === "anomaly") {
    bus = lerp(28.1, 25.4, k); soc = lerp(72, 63, k); att = lerp(0.25, 40.4, k * k);
    rpm = lerp(1100, 1620, k); comms = "no_carrier";
  } else if (id === "burn") {
    bus = 25.4; soc = 63; att = lerp(40.4, 30, k); rpm = lerp(1620, 1400, k);
    comms = "degraded"; fuel = lerp(4.2, 4.004, Math.min(1, k * 1.6));
  } else if (id === "recovering") {
    bus = lerp(25.4, 25.71, k); soc = lerp(63, 66, k); att = lerp(30, 0.01, 1 - (1 - k) ** 3);
    rpm = lerp(1400, 1120, k); comms = k > 0.55 ? "nominal" : "degraded"; fuel = 4.004;
  }
  // countdown to AOS: 36 min of story time compressed into the anomaly phase
  const aosIn = id === "nominal" ? 36 * 60 : id === "anomaly" ? Math.max(0, (1 - k) * 36 * 60) : 0;
  return {
    phase: id, s,
    bus: bus + n * 0.03, soc, att: Math.max(0.01, att + (id === "anomaly" ? n * 0.3 : n * 0.01)),
    rpm: rpm + n * 6, comms, fuel, aosIn,
    passOpen: id === "burn" || id === "recovering",
  };
}
