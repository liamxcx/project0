import { getJson } from "../api.js";
import { badge } from "../badge.js";
import {
  championIconUrl,
  championName,
  championSpells,
  dataDragonReady,
  itemIconUrl,
  itemName,
  runeIconUrl,
  runeName,
  runeTree,
  SHARD_ROWS,
  shardIconUrl,
  shardName,
  spellIconUrl,
  spellName,
} from "../ddragon.js";
import { el } from "../dom.js";
import { formatNumber } from "../format.js";
import { ratio, ratioClass } from "../kda.js";
import { APEX, rankName } from "./rank.js";

const TABS = [
  { id: "teams", label: "Equipos" },
  { id: "build", label: "Build" },
];

const COLUMNS = ["Nota", "KDA", "Ratio", "Daño", "CS", "Objetos"];

// A partir de esta nota se resalta. Las bajas no se marcan en rojo, porque
// Riot no quiere que las webs señalen a los jugadores para mal
const HIGH_SCORE = 7;

// Las iniciales con las que se suele escribir cada liga: D3, P1, M
const TIER_SHORT = {
  IRON: "I",
  BRONZE: "B",
  SILVER: "S",
  GOLD: "G",
  PLATINUM: "P",
  EMERALD: "E",
  DIAMOND: "D",
  MASTER: "M",
  GRANDMASTER: "GM",
  CHALLENGER: "C",
};
const DIVISION_NUMBER = { I: 1, II: 2, III: 3, IV: 4 };

// Solo hay una partida abierta a la vez. Si se abre otra antes de que llegue
// la respuesta de la anterior, esa respuesta ya no vale
let latest = 0;

function message(text) {
  return el("p", { className: "detail-message" }, text);
}

// Una casilla con su imagen. Si la imagen no existe o falla, queda la casilla vacía
function icon(className, url, name) {
  const box = el("span", { className, attrs: name ? { "data-tip": name } : {} });
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

// La etiqueta de rango, con el color de su liga y el nombre completo en el
// tooltip. Es el rango de cuando se guardó la partida
function rankTag(player) {
  if (!player.tier) {
    return el("span", { className: "sb-rank", attrs: { "data-tip": "Sin clasificar" } }, "—");
  }
  const short = TIER_SHORT[player.tier] ?? player.tier;
  const text = APEX.includes(player.tier) ? short : `${short}${DIVISION_NUMBER[player.division] ?? ""}`;
  const tip = `${rankName(player.tier, player.division)} · ${formatNumber(player.league_points, 0)} LP`;
  const className = `sb-rank tier-${player.tier.toLowerCase()}`;
  return el("span", { className, attrs: { "data-tip": tip } }, text);
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
  // El nivel en la esquina del icono, si la partida lo tiene guardado
  if (player.champ_level !== null) {
    champion.append(el("span", { className: "sb-level" }, String(player.champ_level)));
  }
  const spells = el(
    "div",
    { className: "sb-spells" },
    player.summoner_spells.map((id) => icon("sb-spell", spellIconUrl(id), spellName(id))),
  );
  // La runa principal y, debajo, el árbol secundario
  const keystone = player.rune_ids?.[0];
  const runes = el(
    "div",
    { className: "sb-spells" },
    keystone === undefined ? null : icon("sb-rune", runeIconUrl(keystone), runeName(keystone)),
    player.secondary_style_id === null
      ? null
      : icon(
          "sb-rune is-style",
          runeIconUrl(player.secondary_style_id),
          runeName(player.secondary_style_id),
        ),
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
    { attrs: { "data-tip": `${formatNumber(share, 0)}% del daño de su equipo` } },
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
      el("div", { className: "sb-who" }, champion, spells, runes),
      [rankTag(player), el("p", { className: "sb-name" }, name), badge(player.badge)],
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

// Las compras seguidas en el mismo minuto van juntas: [{ minute: 0, items: [1055, 2003] }, ...]
function byMinute(purchases) {
  const groups = [];
  for (const { item_id, minute } of purchases) {
    const last = groups.at(-1);
    if (last && last.minute === minute) last.items.push(item_id);
    else groups.push({ minute, items: [item_id] });
  }
  return groups;
}

function itemsSection(player) {
  const groups = byMinute(player.purchases);
  const timeline =
    groups.length === 0
      ? message("Esta partida se guardó sin las compras.")
      : el(
          "ol",
          { className: "build-timeline" },
          groups.map(({ minute, items }) =>
            el(
              "li",
              { className: "build-step" },
              el(
                "div",
                {},
                el(
                  "div",
                  { className: "build-step-items" },
                  items.map((id) => icon("build-item", itemIconUrl(id), itemName(id))),
                ),
                el("p", { className: "build-minute" }, `${minute} min`),
              ),
            ),
          ),
        );
  return el("section", {}, el("h3", { className: "build-title" }, "Objetos"), timeline);
}

const SKILL_KEYS = ["Q", "W", "E", "R"];

// En qué orden se subieron al máximo Q, W y E. Si la partida acaba antes de
// subirlas todas, va antes la que tiene más puntos
function maxOrder(skills) {
  return [1, 2, 3]
    .map((slot) => {
      const levels = skills.flatMap((s, i) => (s === slot ? [i] : []));
      return {
        slot,
        points: levels.length,
        maxAt: levels[4] ?? Infinity,
        first: levels[0] ?? Infinity,
      };
    })
    .sort((a, b) => a.maxAt - b.maxAt || b.points - a.points || a.first - b.first)
    .map(({ slot }) => slot);
}

// El icono de la habilidad con su tecla en la esquina. Hasta que llega la imagen,
// o si no llega, se queda el cuadrado de su color con la tecla
function skillIcon(slot) {
  return el(
    "span",
    { className: `skill-icon skill-${slot}` },
    el("span", { className: "skill-letter" }, SKILL_KEYS[slot - 1]),
  );
}

// Cuando llegan las habilidades del campeón, pone la imagen y el nombre en cada
// icono. Si mientras tanto se eligió otro jugador, ya no están en la página
async function fillSkillIcons(champion, icons) {
  const spells = await championSpells(champion);
  if (spells === null) return;
  for (const { slot, element } of icons) {
    if (!element.isConnected) return;
    const spell = spells[slot - 1];
    element.setAttribute("data-tip", spell.name);
    element.prepend(el("img", { attrs: { src: spell.icon, alt: spell.name } }));
  }
}

// Una fila por habilidad y una columna por nivel. En cada nivel se marca la
// habilidad que se subió, con el número del nivel
function skillsSection(player) {
  const { skills } = player;
  const head = el("div", { className: "build-head" }, el("h3", { className: "build-title" }, "Habilidades"));
  if (skills.length === 0) {
    return el("section", {}, head, message("Esta partida se guardó sin las habilidades."));
  }
  const icons = [];
  const tracked = (slot) => {
    const element = skillIcon(slot);
    icons.push({ slot, element });
    return element;
  };
  head.append(
    el(
      "p",
      { className: "skill-order" },
      el("span", { className: "skill-order-label" }, "Orden de prioridad"),
      maxOrder(skills).flatMap((slot, i) => (i === 0 ? [tracked(slot)] : ["›", tracked(slot)])),
    ),
  );
  const cells = [1, 2, 3, 4].flatMap((slot) => [
    el("span", { className: "skill-label" }, tracked(slot)),
    ...skills.map((s, i) =>
      s === slot
        ? el("span", { className: `skill-cell is-up skill-${slot}` }, String(i + 1))
        : el("span", { className: "skill-cell" }),
    ),
  ]);
  const grid = el("div", { className: "skill-grid", style: { "--levels": String(skills.length) } }, cells);
  fillSkillIcons(player.champion, icons);
  return el("section", {}, head, grid);
}

// Un árbol entero con las runas elegidas resaltadas. Del árbol secundario solo
// se eligen runas de las filas de abajo, así que su primera fila no se enseña
function treeColumn(tree, chosen, withKeystones) {
  if (tree === null) return null;
  const slots = withKeystones ? tree.slots : tree.slots.slice(1);
  const rows = slots.map((slot, i) =>
    el(
      "div",
      { className: withKeystones && i === 0 ? "rune-row is-keystones" : "rune-row" },
      slot.runes.map((rune) =>
        icon(chosen.includes(rune.id) ? "rune-cell is-chosen" : "rune-cell", runeIconUrl(rune.id), rune.name),
      ),
    ),
  );
  const name = el(
    "p",
    { className: "rune-tree-name" },
    icon("rune-tree-icon", runeIconUrl(tree.id), null),
    tree.name,
  );
  return el("div", { className: "rune-tree" }, name, rows);
}

// Las tres filas de fragmentos. Una misma estadística puede salir en dos filas,
// así que se marca la elegida de cada fila y no todas las que coinciden
function shardColumn(shardIds) {
  const rows = SHARD_ROWS.map((row, i) =>
    el(
      "div",
      { className: "rune-row" },
      row.map((id) =>
        icon(shardIds[i] === id ? "shard-cell is-chosen" : "shard-cell", shardIconUrl(id), shardName(id)),
      ),
    ),
  );
  const name = el("p", { className: "rune-tree-name" }, "Fragmentos");
  return el("div", { className: "rune-tree" }, name, rows);
}

function runesSection(player) {
  const head = el("h3", { className: "build-title" }, "Runas");
  if (player.rune_ids === null) {
    return el("section", {}, head, message("Esta partida se guardó sin las runas."));
  }
  const page = el(
    "div",
    { className: "runes" },
    treeColumn(runeTree(player.primary_style_id), player.rune_ids, true),
    treeColumn(runeTree(player.secondary_style_id), player.rune_ids, false),
    player.shard_ids === null ? null : shardColumn(player.shard_ids),
  );
  return el("section", {}, head, page);
}

// Arriba los diez jugadores, primero tu equipo, para ver la build de cualquiera.
// Al abrir la pestaña sale la tuya
function buildTab(detail) {
  const { players, me } = detail;
  if (players.length < 10) {
    return message("Esta partida se guardó antes de tener a los diez jugadores.");
  }
  const myTeam = players.find((p) => p.participant_id === me.participant_id).team_id;
  const teams = [
    players.filter((p) => p.team_id === myTeam),
    players.filter((p) => p.team_id !== myTeam),
  ];
  const left = el("div", { className: "build-left" });
  const right = el("div", { className: "build-right" });
  const buttons = new Map();

  function select(chosen) {
    for (const [id, button] of buttons) {
      button.setAttribute("aria-pressed", String(id === chosen.participant_id));
    }
    left.replaceChildren(itemsSection(chosen), skillsSection(chosen));
    right.replaceChildren(runesSection(chosen));
  }

  const strip = teams.map((team) =>
    el(
      "div",
      { className: "build-team" },
      team.map((player) => {
        const score = player.score === null ? "—" : formatNumber(player.score, 1);
        const badgeClass = player.badge ? ` is-${player.badge.toLowerCase()}` : "";
        const button = el(
          "button",
          {
            className: `build-player${badgeClass}`,
            attrs: { type: "button", "data-tip": player.riot_id ?? championName(player.champion) },
            on: { click: () => select(player) },
          },
          icon("build-champion", championIconUrl(player.champion), null),
          el("span", { className: player.score >= HIGH_SCORE ? "build-score is-high" : "build-score" }, score),
        );
        buttons.set(player.participant_id, button);
        return button;
      }),
    ),
  );

  select(players.find((p) => p.participant_id === me.participant_id));
  // Tu build sale primero, y mientras la miras se piden las habilidades de los
  // otros nueve, para que al elegir a uno ya estén en la caché
  for (const player of players) championSpells(player.champion);
  // Dos columnas, para que todo quepa a lo alto: a la izquierda los jugadores,
  // los objetos y las habilidades, y a la derecha las runas desde arriba
  return el(
    "div",
    { className: "build" },
    el("div", { className: "build-main" }, el("div", { className: "build-players" }, strip), left),
    right,
  );
}

const PANELS = {
  teams: teamsTab,
  build: buildTab,
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
