import { getJson } from "../api.js";
import { badge } from "../badge.js";
import {
  championIconUrl,
  championName,
  dataDragonReady,
  itemIconUrl,
  itemName,
  spellIconUrl,
  spellName,
} from "../ddragon.js";
import { el } from "../dom.js";
import { formatNumber } from "../format.js";
import { ratio, ratioClass } from "../kda.js";

const TABS = [
  { id: "teams", label: "Equipos" },
  { id: "build", label: "Objetos" },
];

const COLUMNS = ["Nota", "KDA", "Ratio", "Daño", "CS", "Objetos"];

// A partir de esta nota se resalta. Las bajas no se marcan en rojo, porque
// Riot no quiere que las webs señalen a los jugadores para mal
const HIGH_SCORE = 7;

// Solo hay una partida abierta a la vez. Si se abre otra antes de que llegue
// la respuesta de la anterior, esa respuesta ya no vale
let latest = 0;

function message(text) {
  return el("p", { className: "detail-message" }, text);
}

// Una casilla con su imagen. Si la imagen no existe o falla, queda la casilla vacía
function icon(className, url, name) {
  const box = el("span", { className, attrs: name ? { title: name } : {} });
  if (url === null) return box;
  const image = el("img", { attrs: { src: url, alt: name ?? "", loading: "lazy" } });
  image.addEventListener("error", () => image.remove(), { once: true });
  box.append(image);
  return box;
}

// Riot guarda un 0 en los huecos sin objeto
function itemSlot(id, extraClass = "") {
  const empty = !id;
  return icon(
    `sb-item${extraClass}`,
    empty ? null : itemIconUrl(id),
    empty ? null : itemName(id),
  );
}

function cells(...children) {
  return children.map((child) => el("div", { className: "sb-cell" }, child));
}

// El dato y su acompañante en la misma línea, para que las filas sean bajas
function withSub(main, sub, subClass = "") {
  return el("p", { className: "sb-value" }, main, " ", el("span", { className: `sb-sub ${subClass}`.trim() }, sub));
}

// El puesto de cada jugador por su nota, de 1 a 10. Los empates se ordenan por
// número de jugador, igual que los sellos en la base de datos
function places(players) {
  const ranked = players
    .filter((p) => p.score !== null)
    .sort((a, b) => b.score - a.score || a.participant_id - b.participant_id);
  return new Map(ranked.map((p, i) => [p.participant_id, i + 1]));
}

function playerRow(player, context) {
  const { meId, minutes, maxDamage, teamDamage, place } = context;
  const name = player.riot_id ?? championName(player.champion);
  const champion = icon("sb-champion", championIconUrl(player.champion), championName(player.champion));
  const spells = el(
    "div",
    { className: "sb-spells" },
    player.summoner_spells.map((id) => icon("sb-spell", spellIconUrl(id), spellName(id))),
  );

  const scoreText = player.score === null ? "—" : formatNumber(player.score, 1);
  const scoreClass = player.score >= HIGH_SCORE ? "sb-score is-high" : "sb-score";
  const placeText = place === undefined ? "" : `${place}.º`;

  const value = ratio(player);
  const kda = `${player.kills} / ${player.deaths} / ${player.assists}`;
  const ratioText = value === null ? "Perfecto" : formatNumber(value, 2);

  const damage = player.damage_to_champions ?? 0;
  const share = teamDamage > 0 ? (100 * damage) / teamDamage : 0;
  const fill = el("div", {
    className: "sb-fill",
    style: { width: `${maxDamage > 0 ? (100 * damage) / maxDamage : 0}%` },
  });
  const damageCell = el(
    "div",
    { attrs: { title: `${formatNumber(share, 0)}% del daño de su equipo` } },
    el("p", { className: "sb-value" }, formatNumber(damage, 0)),
    el("div", { className: "sb-track" }, fill),
  );

  const cs = player.cs ?? 0;
  const items = el(
    "div",
    { className: "sb-items" },
    player.items.slice(0, 6).map((id) => itemSlot(id)),
    // El séptimo es el abalorio, y va un poco separado
    itemSlot(player.items[6], " is-trinket"),
  );

  const rowClass = player.participant_id === meId ? "sb-row is-me" : "sb-row";
  return el(
    "div",
    { className: rowClass },
    ...cells(
      el("div", { className: "sb-who" }, champion, spells),
      [el("p", { className: "sb-name" }, name), badge(player.badge)],
      el("div", { className: "sb-score-cell" }, el("span", { className: scoreClass }, scoreText), placeText),
      el("p", { className: "sb-value" }, kda),
      // En su propia columna, para que los diez ratios queden uno debajo de otro
      el("p", { className: `sb-value ${ratioClass(value)}` }, ratioText),
      damageCell,
      withSub(formatNumber(cs, 0), `${formatNumber(cs / minutes, 1)}/min`),
      items,
    ),
  );
}

// contextOf da, para cada jugador, lo que su fila necesita saber del resto
function teamBlock(title, players, contextOf) {
  const win = players[0].win;
  const header = el(
    "div",
    { className: "sb-head" },
    el(
      "p",
      { className: win ? "sb-team is-win" : "sb-team is-loss" },
      el("strong", {}, win ? "Victoria" : "Derrota"),
      ` · ${title}`,
    ),
    COLUMNS.map((label) => el("p", { className: "sb-column" }, label)),
  );
  return el("div", { className: "sb-block" }, header, players.map((p) => playerRow(p, contextOf(p))));
}

function teamsTab(detail) {
  const { players, me } = detail;
  // Las partidas guardadas antes de tener a los diez jugadores no tienen marcador
  if (players.length < 10) {
    return message("Esta partida se guardó antes de tener a los diez jugadores, así que no hay marcador.");
  }
  const myTeam = players.find((p) => p.participant_id === me.participant_id).team_id;
  const allies = players.filter((p) => p.team_id === myTeam);
  const enemies = players.filter((p) => p.team_id !== myTeam);
  const damageOf = (team) => team.reduce((sum, p) => sum + (p.damage_to_champions ?? 0), 0);
  const ranking = places(players);
  const base = {
    meId: me.participant_id,
    minutes: detail.duration_seconds / 60,
    maxDamage: Math.max(...players.map((p) => p.damage_to_champions ?? 0)),
  };
  const block = (title, team) =>
    teamBlock(title, team, (player) => ({
      ...base,
      teamDamage: damageOf(team),
      place: ranking.get(player.participant_id),
    }));
  return el("div", { className: "scoreboard" }, block("Tu equipo", allies), block("Rivales", enemies));
}

// Objetos llega en el siguiente subpaso
const PANELS = {
  teams: teamsTab,
  build: () => message("Los objetos llegan en el siguiente paso."),
};

function tabs(detail) {
  const content = el("div", { className: "detail-content", attrs: { role: "tabpanel" } });
  const buttons = TABS.map(({ id, label }) =>
    el(
      "button",
      { className: "detail-tab", attrs: { type: "button", role: "tab" }, on: { click: () => show(id) } },
      label,
    ),
  );

  function show(id) {
    TABS.forEach((tab, i) => buttons[i].setAttribute("aria-selected", String(tab.id === id)));
    content.replaceChildren(PANELS[id](detail));
  }

  show("teams");
  return [el("div", { className: "detail-tabs", attrs: { role: "tablist" } }, buttons), content];
}

// Pinta el detalle dentro del panel que hay debajo de la partida. La API manda
// Cache-Control, así que al volver a abrir la misma el navegador no la pide
export async function renderMatchDetail(panel, matchId) {
  const turn = ++latest;
  panel.replaceChildren(message("Cargando…"));
  try {
    const [detail] = await Promise.all([
      getJson(`/matches/${encodeURIComponent(matchId)}`),
      dataDragonReady,
    ]);
    if (turn !== latest) return;
    panel.replaceChildren(...tabs(detail));
  } catch (error) {
    if (turn !== latest) return;
    console.error("No se ha podido cargar el detalle de la partida.", error);
    panel.replaceChildren(message("No se ha podido cargar el detalle de la partida."));
  }
}
