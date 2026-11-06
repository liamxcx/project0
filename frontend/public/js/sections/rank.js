import { el } from "../dom.js";
import { formatNumber, formatTimeAgo } from "../format.js";

const TIERS = [
  "IRON",
  "BRONZE",
  "SILVER",
  "GOLD",
  "PLATINUM",
  "EMERALD",
  "DIAMOND",
  "MASTER",
  "GRANDMASTER",
  "CHALLENGER",
];
const TIER_NAMES = {
  IRON: "Hierro",
  BRONZE: "Bronce",
  SILVER: "Plata",
  GOLD: "Oro",
  PLATINUM: "Platino",
  EMERALD: "Esmeralda",
  DIAMOND: "Diamante",
  MASTER: "Master",
  GRANDMASTER: "Grandmaster",
  CHALLENGER: "Challenger",
};
const DIVISIONS = ["IV", "III", "II", "I"];
// Riot les pone división I, pero en estos tres no hay divisiones
const APEX = ["MASTER", "GRANDMASTER", "CHALLENGER"];

function rankName(tier, division) {
  const name = TIER_NAMES[tier] ?? tier;
  return APEX.includes(tier) ? name : `${name} ${division}`;
}

// El siguiente escalón y cuántos LP pide. En Master y Gran Maestro el corte
// cambia cada día con la liga, así que viene de la API
function nextStep(rank) {
  if (rank.tier === "CHALLENGER") return null;
  if (rank.tier === "MASTER" || rank.tier === "GRANDMASTER") {
    const next = rank.tier === "MASTER" ? "GRANDMASTER" : "CHALLENGER";
    return { name: TIER_NAMES[next], target: rank.next_cutoff_lp };
  }
  const division = DIVISIONS.indexOf(rank.division);
  const name =
    division < DIVISIONS.length - 1
      ? rankName(rank.tier, DIVISIONS[division + 1])
      : rankName(TIERS[TIERS.indexOf(rank.tier) + 1], "IV");
  return { name, target: 100 };
}

function progress(rank, step) {
  if (step === null) return el("p", { className: "rank-max" }, "Rango máximo");
  // A principio de temporada la liga de arriba puede estar vacía
  if (step.target === null) {
    return el("p", { className: "card-message" }, `Todavía no hay corte de ${step.name}.`);
  }

  const lp = rank.league_points;
  const left = step.target - lp;
  const pct = Math.max(0, Math.min(100, Math.round((100 * lp) / step.target)));
  return el(
    "div",
    { className: "rank-progress" },
    el(
      "div",
      { className: "rank-progress-head" },
      el("span", {}, `Hacia ${step.name}`),
      el(
        "span",
        { className: "rank-missing" },
        left > 0 ? `Faltan ${formatNumber(left, 0)} LP` : "Por encima del corte",
      ),
    ),
    el(
      "div",
      { className: "rank-bar" },
      el(
        "div",
        { className: "rank-track" },
        el("div", { className: "rank-fill", style: { width: `${pct}%` } }),
      ),
      el("span", { className: "rank-pct" }, `${pct} %`),
    ),
    el(
      "div",
      { className: "rank-progress-foot" },
      el("span", {}, `${formatNumber(lp, 0)} LP`),
      el("span", {}, `${formatNumber(step.target, 0)} LP`),
    ),
  );
}

export async function renderRank(card, rankData) {
  const title = el("p", { className: "card-title" }, "Clasificatoria Solo/Duo");
  const message = (text) => el("p", { className: "card-message" }, text);
  try {
    const rank = await rankData;
    if (rank === null) {
      card.replaceChildren(title, message("Sin clasificar esta temporada."));
      return;
    }
    const tier = rank.tier.toLowerCase();
    // El color de la barra lo pone el CSS según el rango
    card.classList.add(`tier-${tier}`);
    const emblem = el("img", {
      className: "rank-emblem",
      attrs: { src: `/emblems/${encodeURIComponent(tier)}.png`, alt: "", width: "56", height: "56" },
    });
    card.replaceChildren(
      title,
      el(
        "div",
        { className: "rank-main" },
        el("span", { className: "rank-frame" }, emblem),
        el(
          "div",
          {},
          el("p", { className: "rank-name" }, rankName(rank.tier, rank.division)),
          el("p", { className: "rank-lp" }, `${formatNumber(rank.league_points, 0)} LP`),
        ),
      ),
      progress(rank, nextStep(rank)),
      // Es la última foto del collector, así que un dato viejo no debe
      // parecer de ahora
      el("p", { className: "rank-updated" }, `Actualizado ${formatTimeAgo(rank.taken_at)}`),
    );
  } catch (error) {
    console.error("No se ha podido cargar la clasificatoria.", error);
    card.replaceChildren(title, message("No se ha podido cargar la clasificatoria."));
  }
}
