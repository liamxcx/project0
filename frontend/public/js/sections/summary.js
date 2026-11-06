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

// project0 aún no tiene todas las partidas de esta temporada, así que el total
// sale de Riot. Con la de enero puede salir de /summary (ver MEJORAS.md)
export async function renderSummary(card, rankData, patches) {
  const message = (text) => el("p", { className: "card-message" }, text);
  try {
    const [rank, patchList] = await Promise.all([rankData, patches]);
    const season = seasonOf(patchList);
    const title = el(
      "p",
      { className: "card-title" },
      season ? `Resumen · Temporada ${season}` : "Resumen",
    );
    if (rank === null) {
      card.replaceChildren(title, message("Sin partidas clasificatorias esta temporada."));
      return;
    }
    card.replaceChildren(
      title,
      el(
        "div",
        { className: "summary-stats" },
        stat(formatNumber(rank.games, 0), "Partidas"),
        stat(`${rank.wins}V ${rank.losses}D`, "Victorias / derrotas"),
        stat(`${formatNumber(rank.winrate_pct, 0)}%`, "Winrate"),
      ),
    );
  } catch (error) {
    console.error("No se ha podido cargar el resumen.", error);
    card.replaceChildren(message("No se ha podido cargar el resumen."));
  }
}
