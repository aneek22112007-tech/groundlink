import { mountHud, mountReplay, mountGate, mountChrome } from "./hud.js";

const reduced = matchMedia("(prefers-reduced-motion: reduce)").matches;
mountChrome(document);
mountGate(document);
mountHud(document, reduced);
mountReplay(document);

const canvas = document.getElementById("space");
const hasGL = (() => { try { return !!document.createElement("canvas").getContext("webgl2"); } catch { return false; } })();
if (!hasGL) {
  document.documentElement.classList.add("is-static");
} else {
  import("./scene.js")
    .then(({ mountScene }) => mountScene({ container: document.getElementById("globe"), canvas, label: document.getElementById("sat-label"), reduced }))
    .catch(() => document.documentElement.classList.add("is-static"));
}
