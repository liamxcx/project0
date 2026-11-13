import { getJson } from "../api.js";
import { championIconUrl, championName, dataDragonReady } from "../ddragon.js";
import { el } from "../dom.js";
import { formatGames, formatNumber } from "../format.js";
import { ratioClass } from "../kda.js";
import { seasonOf } from "../season.js";

// Solo los más jugados, porque son los que tienen partidas suficientes para
// que el winrate diga algo
const TOP = 6;

// Como en summary.js, descarta la respuesta de un parche que ya no está elegido
let latest = 0;

function card(row, onPick) {
  const name = championName(row.champion);
  const icon = el("span", { className: "top-icon" });
  const url = championIconUrl(row.champion);
  if (url !== null) icon.append(el("img", { attrs: { src: url, alt: "" } }));
  const ratio = row.kda_ratio === null ? "Perfecto" : formatNumber(row.kda_ratio, 2);
  // El winrate se resalta si gana más de lo que pierde. Por debajo no se pinta
  // en rojo, porque Riot no quiere que las webs señalen a los jugadores para mal
  const winrateClass = row.winrate_pct > 50 ? "top-winrate is-good" : "top-winrate";
  return el(
    "button",
    {
      className: "top-card",
      attrs: { type: "button", "data-tip": `Ver las partidas con ${name}` },
      on: { click: () => onPick(row.champion) },
    },
    icon,
    el(
      "span",
      { className: "top-text" },
      el("span", { className: "top-name" }, name),
      el("span", { className: "top-games" }, `${formatGames(row.games)} · ${row.wins}V ${row.games - row.wins}D`),
    ),
    el(
      "span",
      { className: "top-stats" },
      el("span", { className: winrateClass }, `${formatNumber(row.winrate_pct, 0)}%`),
      el("span", { className: `top-ratio ${ratioClass(row.kda_ratio)}` }, `${ratio} KDA`),
    ),
  );
}

// Los campeones más jugados del periodo del selector de arriba. Al pinchar en
// uno, onPick enseña sus partidas en el historial
export async function renderTopChampions(section, patches, patch, onPick) {
  const turn = ++latest;
  const season = seasonOf(patches);
  const period = patch ? `Parche ${patch}` : season ? `Temporada ${season}` : null;
  const head = el(
    "div",
    { className: "section-head" },
    el("h2", {}, "Más jugados", period ? el("span", { className: "section-period" }, ` · ${period}`) : null),
  );
  const message = (text) => el("p", { className: "section-message" }, text);
  try {
    const [rows] = await Promise.all([getJson("/champions", { patch }), dataDragonReady]);
    if (turn !== latest) return;
    if (rows.length === 0) {
      section.replaceChildren(head, message("Sin partidas en este periodo."));
      return;
    }
    const cards = rows.slice(0, TOP).map((row) => card(row, onPick));
    section.replaceChildren(head, el("div", { className: "top-grid" }, cards));
  } catch (error) {
    if (turn !== latest) return;
    console.error("No se han podido cargar los campeones más jugados.", error);
    section.replaceChildren(head, message("No se han podido cargar los campeones más jugados."));
  }
}
