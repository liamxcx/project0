import { getJson } from "../api.js";
import { el } from "../dom.js";
import { formatNumber } from "../format.js";
import { seasonOf } from "../season.js";

function stat(value, label) {
  return el(
    "div",
    {},
    el("p", { className: "summary-value" }, value),
    el("p", { className: "summary-label" }, label),
  );
}

// Cada petición lleva un turno. Si se elige otro parche mientras llega una
// respuesta, esa respuesta ya no vale
let latest = 0;

// project0 aún no tiene todas las partidas de esta temporada, así que el total
// sale de Riot. Con la temporada nueva, en enero, puede salir de /summary (ver MEJORAS.md)
export async function renderSummary(card, rankData, patches, patch) {
  const turn = ++latest;
  const message = (text) => el("p", { className: "card-message" }, text);
  const season = seasonOf(patches);
  const period = patch ? `Parche ${patch}` : season ? `Temporada ${season}` : null;
  const title = el("p", { className: "card-title" }, period ? `Resumen · ${period}` : "Resumen");
  try {
    const data = patch ? await getJson("/summary", { patch }) : await rankData;
    if (turn !== latest) return;
    if (data === null || data.games === 0) {
      card.replaceChildren(title, message("Sin partidas en este periodo."));
      return;
    }
    card.replaceChildren(
      title,
      el(
        "div",
        { className: "summary-stats" },
        stat(formatNumber(data.games, 0), "Partidas"),
        stat(`${data.wins}V ${data.losses}D`, "Victorias / derrotas"),
        stat(`${formatNumber(data.winrate_pct, 0)}%`, "Winrate"),
      ),
    );
  } catch (error) {
    if (turn !== latest) return;
    console.error("No se ha podido cargar el resumen.", error);
    card.replaceChildren(title, message("No se ha podido cargar el resumen."));
  }
}
