import { mountHud, mountReplay } from "./hud.js";

const reduce = matchMedia("(prefers-reduced-motion: reduce)").matches;
const narrow = matchMedia("(max-width: 800px)").matches;
if (reduce || narrow) {
  document.documentElement.classList.add("is-static");
} else {
  import("./scene.js").catch((error) => {
    console.error(error);
    document.documentElement.classList.add("is-static");
  });
}
mountHud(document);
mountReplay(document.querySelector("#replay-log"));
