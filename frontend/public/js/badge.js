import { el } from "./dom.js";

const SVG_NS = "http://www.w3.org/2000/svg";

// La corona y el escudo de la maqueta, con lo que significa cada sello
const BADGES = {
  MVP: {
    title: "MVP: mejor nota del equipo ganador",
    viewBox: "0 0 24 24",
    paths: [
      "M11.562 3.266a.5.5 0 0 1 .876 0L15.39 8.87a1 1 0 0 0 1.516.294L21.183 5.5a.5.5 0 0 1 .798.519l-2.834 10.246a1 1 0 0 1-.956.734H5.81a1 1 0 0 1-.957-.734L2.02 6.02a.5.5 0 0 1 .798-.519l4.276 3.664a1 1 0 0 0 1.516-.294z",
      "M5 21h14",
    ],
  },
  BASTION: {
    title: "BASTION: mejor nota del equipo perdedor",
    viewBox: "0 0 24 28",
    paths: ["M12 2 L21 5.5 V13 C21 19 17 23.5 12 26 C7 23.5 3 19 3 13 V5.5 Z", "M12 7 V21"],
  },
};

export function badge(name) {
  const info = BADGES[name];
  if (!info) return null;
  const icon = document.createElementNS(SVG_NS, "svg");
  icon.setAttribute("viewBox", info.viewBox);
  icon.setAttribute("aria-hidden", "true");
  for (const d of info.paths) {
    const path = document.createElementNS(SVG_NS, "path");
    path.setAttribute("d", d);
    icon.append(path);
  }
  const className = `badge badge-${name.toLowerCase()}`;
  return el("span", { className, attrs: { title: info.title } }, icon, name);
}
