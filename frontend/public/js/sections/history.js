import { getJson } from "../api.js";
import { championName, championSplashUrl, dataDragonReady } from "../ddragon.js";
import { el } from "../dom.js";
import { dropdown } from "../dropdown.js";
import { formatGames, formatNumber } from "../format.js";

const SVG_NS = "http://www.w3.org/2000/svg";

// Riot da la posición con su nombre interno, y en la página va el que usa la gente
const POSITIONS = { TOP: "Top", JUNGLE: "Jungla", MIDDLE: "Mid", BOTTOM: "ADC", UTILITY: "Support" };

// No lleva zona horaria, así que sale la hora de quien mira la página
const DATE_FORMAT = new Intl.DateTimeFormat("es-ES", {
  day: "numeric",
  month: "short",
  hour: "2-digit",
  minute: "2-digit",
});

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

function badge(name) {
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

// Redondeado antes de elegir el color, para que un 2,996 que se lee 3,00 no
// salga del color de los que están por debajo de 3. Sin muertes da null
function ratio({ kills, deaths, assists }) {
  if (deaths === 0) return null;
  return Math.round(((kills + assists) / deaths) * 100) / 100;
}

// Los cortes de color de la maqueta. Sin muertes cuenta como el más alto
function ratioClass(value) {
  if (value === null || value >= 4) return "ratio-high";
  if (value >= 3) return "ratio-good";
  if (value >= 2) return "ratio-ok";
  return "ratio-low";
}

function duration(seconds) {
  return `${Math.floor(seconds / 60)}:${String(seconds % 60).padStart(2, "0")}`;
}

function stat(value, label, className) {
  return el(
    "div",
    { className: "match-stat" },
    el("p", { className: className ? `match-value ${className}` : "match-value" }, value),
    el("p", { className: "match-label" }, label),
  );
}

// La splash va de fondo, y si no carga la barra se queda con el color de fondo
function splash(key) {
  const image = el("img", {
    className: "match-splash",
    attrs: { src: championSplashUrl(key), alt: "", loading: "lazy" },
  });
  image.addEventListener("error", () => image.remove(), { once: true });
  return image;
}

function row(match) {
  const value = ratio(match);
  const name = el("p", { className: "match-name" }, championName(match.champion));
  return el(
    "li",
    { className: match.win ? "match is-win" : "match is-loss" },
    splash(match.champion),
    el(
      "div",
      { className: "match-body" },
      el(
        "div",
        { className: "match-champion" },
        name,
        el("p", { className: "match-label" }, POSITIONS[match.position] ?? (match.position || "—")),
      ),
      stat(`${match.kills} / ${match.deaths} / ${match.assists}`, "KDA"),
      stat(value === null ? "Perfecto" : formatNumber(value, 2), "Ratio", ratioClass(value)),
      stat(match.win ? "Victoria" : "Derrota", duration(match.duration_seconds), "match-result"),
      // La columna está aunque no haya sello, para que los demás queden alineados
      el("div", {}, badge(match.badge)),
      stat(DATE_FORMAT.format(new Date(match.played_at)), `Parche ${match.patch}`),
    ),
  );
}

// Cada cambio de filtro abre un turno. Una respuesta que llega de un turno
// anterior se pidió para otra lista, así que se descarta
let latest = 0;

function message(text) {
  return el("p", { className: "section-message" }, text);
}

function emptyText({ patch, champion }) {
  if (!patch && !champion) return "Todavía no hay partidas guardadas.";
  const who = champion ? ` con ${championName(champion)}` : "";
  const when = patch ? ` en el parche ${patch}` : "";
  return `No hay partidas${who}${when}.`;
}

// filter lleva el parche y el campeón. Con null, ese filtro no se aplica
async function fetchPage(filter, offset) {
  const params = { patch: filter.patch, champion: filter.champion, offset };
  const [page] = await Promise.all([getJson("/matches", params), dataDragonReady]);
  return page;
}

// Añade la tanda debajo de las que ya hay y deja al final el botón para pedir
// la siguiente, o el aviso de que no quedan más
function showPage(list, footer, page, filter, offset, turn) {
  list.append(...page.matches.map(row));
  if (!page.has_more) {
    footer.replaceChildren(el("p", { className: "matches-end" }, "No quedan más partidas que mostrar"));
    return;
  }
  const next = offset + page.matches.length;
  const button = el("button", { className: "more-button", attrs: { type: "button" } }, "Mostrar 10 más");
  button.addEventListener("click", async () => {
    // Desactivado mientras llega la respuesta, para que dos clics seguidos no
    // pidan la misma tanda dos veces y salga repetida
    button.disabled = true;
    try {
      const nextPage = await fetchPage(filter, next);
      if (turn !== latest) return;
      showPage(list, footer, nextPage, filter, next, turn);
    } catch (error) {
      if (turn !== latest) return;
      console.error("No se han podido cargar más partidas.", error);
      const warning = el("p", { className: "matches-end" }, "No se han podido cargar más partidas.");
      footer.replaceChildren(warning, button);
      button.disabled = false;
    }
  });
  footer.replaceChildren(button);
}

// Empieza la lista desde la primera tanda. Se queda con una copia del filtro,
// para que las tandas siguientes no cambien si luego se elige otro
async function loadMatches(results, { patch, champion }) {
  const turn = ++latest;
  const filter = { patch, champion };
  try {
    const page = await fetchPage(filter, 0);
    if (turn !== latest) return;
    if (page.matches.length === 0) {
      results.replaceChildren(message(emptyText(filter)));
      return;
    }
    const list = el("ol", { className: "matches" });
    const footer = el("div", { className: "matches-footer" });
    results.replaceChildren(list, footer);
    showPage(list, footer, page, filter, 0, turn);
  } catch (error) {
    if (turn !== latest) return;
    console.error("No se ha podido cargar el historial.", error);
    results.replaceChildren(message("No se ha podido cargar el historial."));
  }
}

function option(label, meta, onClick) {
  return el(
    "button",
    { className: "patch-option", attrs: { type: "button" }, on: { click: onClick } },
    el("span", { className: "patch-option-label" }, label),
    el("span", { className: "patch-option-meta" }, meta),
  );
}

// Con una temporada entera saldrían unos 24 botones, así que se ven los más
// recientes y el resto va en el desplegable de "Más"
const VISIBLE_PATCHES = 3;

function patchFilter(patches, onChange) {
  let selected = null;
  const visible = [{ label: "Todos", patch: null }].concat(
    patches.slice(0, VISIBLE_PATCHES).map(({ patch }) => ({ label: patch, patch })),
  );
  const older = patches.slice(VISIBLE_PATCHES);

  const buttons = visible.map(({ label, patch }) =>
    el(
      "button",
      { className: "filter-button", attrs: { type: "button" }, on: { click: () => choose(patch) } },
      label,
    ),
  );

  const moreLabel = el("span", {}, "Más");
  const caret = el("span", { className: "filter-caret", attrs: { "aria-hidden": "true" } });
  const more = el(
    "button",
    { className: "filter-button", attrs: { type: "button" } },
    moreLabel,
    caret,
  );
  // El mismo menú que el selector de arriba, para que los dos se vean iguales
  const items = older.map(({ patch, games }) => option(patch, formatGames(games), () => choose(patch)));
  const menu = el("div", { className: "patch-menu" }, items);
  const moreSelect = dropdown("filter-dropdown", more, caret, menu);

  // Si el elegido está en el desplegable, "Más" pasa a llamarse como él
  function show() {
    // aria-pressed le dice a un lector de pantalla cuál está elegido
    visible.forEach(({ patch }, i) => {
      buttons[i].classList.toggle("is-selected", patch === selected);
      buttons[i].setAttribute("aria-pressed", String(patch === selected));
    });
    const inMenu = older.some(({ patch }) => patch === selected);
    more.classList.toggle("is-selected", inMenu);
    moreLabel.textContent = inMenu ? selected : "Más";
    older.forEach(({ patch }, i) => items[i].classList.toggle("is-selected", patch === selected));
  }

  function choose(patch) {
    moreSelect.close();
    if (patch === selected) return;
    selected = patch;
    show();
    onChange(patch);
  }

  show();
  return el(
    "div",
    { className: "filter-group" },
    el("span", { className: "filter-label" }, "Filtrar por parche"),
    el("div", { className: "filter-buttons" }, buttons, older.length > 0 ? moreSelect.element : null),
  );
}

// "Kai'Sa" → "kaisa", "Nunu y Willump" → "nunuywillump". Así la búsqueda no
// distingue mayúsculas, tildes, espacios ni apóstrofos
function searchKey(text) {
  return text
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .toLowerCase()
    .replace(/[^a-z0-9]/g, "");
}

// El menú de campeón. Su lista sale de /champions del parche elegido, así que
// las partidas de cada campeón cuadran con lo que se ve en el historial
function championFilter(onChange) {
  let selected = null;
  let champions = [];
  let latestList = 0;

  const label = el("span", {}, "Todos");
  const caret = el("span", { className: "filter-caret", attrs: { "aria-hidden": "true" } });
  const button = el("button", { className: "filter-button", attrs: { type: "button" } }, label, caret);
  const search = el("input", {
    className: "filter-search",
    attrs: {
      type: "search",
      placeholder: "Buscar campeón…",
      "aria-label": "Buscar campeón",
      autocomplete: "off",
    },
  });
  const optionsBox = el("div", { className: "filter-options" });
  const menu = el("div", { className: "patch-menu champion-menu" }, search, optionsBox);
  // Al abrir, la búsqueda empieza vacía y con el cursor dentro, para escribir directamente
  const select = dropdown("filter-dropdown", button, caret, menu, () => {
    search.value = "";
    showOptions();
    search.focus();
  });

  // Primero los que empiezan por lo escrito y después los que lo llevan en
  // medio. Dentro de cada grupo siguen del más jugado al menos
  function found() {
    const wanted = searchKey(search.value);
    const named = champions.map((c) => ({ ...c, key: searchKey(championName(c.champion)) }));
    const starts = named.filter(({ key }) => key.startsWith(wanted));
    const inside = named.filter(({ key }) => !key.startsWith(wanted) && key.includes(wanted));
    return starts.concat(inside);
  }

  function showOptions() {
    const items = found().map(({ champion, games }) => {
      const item = option(championName(champion), formatGames(games), () => choose(champion));
      item.classList.toggle("is-selected", champion === selected);
      return item;
    });
    // "Todos" solo tiene sentido sin búsqueda, porque no es un campeón
    if (searchKey(search.value) === "") {
      const total = champions.reduce((sum, { games }) => sum + games, 0);
      const all = option("Todos", formatGames(total), () => choose(null));
      all.classList.toggle("is-selected", selected === null);
      items.unshift(all);
    }
    const empty = el("p", { className: "filter-empty" }, "Ningún campeón coincide.");
    optionsBox.replaceChildren(...(items.length > 0 ? items : [empty]));
  }

  search.addEventListener("input", showOptions);
  // Enter elige el primero de la lista, que es el que mejor encaja
  search.addEventListener("keydown", (event) => {
    if (event.key !== "Enter" || searchKey(search.value) === "") return;
    const [first] = found();
    if (first) choose(first.champion);
  });

  function show() {
    label.textContent = selected === null ? "Todos" : championName(selected);
    button.classList.toggle("is-selected", selected !== null);
    showOptions();
  }

  function choose(champion) {
    select.close();
    if (champion === selected) return;
    selected = champion;
    show();
    onChange(champion);
  }

  // Cambia la lista a la del parche. Si el campeón elegido no jugó en ese
  // parche, vuelve a "Todos". Devuelve el campeón con el que hay que seguir, o
  // undefined si mientras tanto se pidió la lista de otro parche
  async function load(patch) {
    const turn = ++latestList;
    try {
      const [list] = await Promise.all([getJson("/champions", { patch }), dataDragonReady]);
      if (turn !== latestList) return undefined;
      champions = list;
      if (!champions.some(({ champion }) => champion === selected)) selected = null;
    } catch (error) {
      if (turn !== latestList) return undefined;
      // Sin lista nueva se queda la anterior, y el historial sigue funcionando
      console.warn("No se ha podido cargar la lista de campeones.", error);
    }
    show();
    return selected;
  }

  const element = el(
    "div",
    { className: "filter-group" },
    el("span", { className: "filter-label" }, "Campeón"),
    select.element,
  );
  return { element, load };
}

export async function renderHistory(section, patches) {
  const head = el("div", { className: "section-head" }, el("h2", {}, "Últimas partidas"));
  const filters = el("div", { className: "history-filters" });
  const results = el("div");
  section.replaceChildren(head, filters, results);

  const filter = { patch: null, champion: null };
  loadMatches(results, filter);
  const champions = championFilter((champion) => {
    filter.champion = champion;
    loadMatches(results, filter);
  });
  champions.load(null);
  filters.replaceChildren(champions.element);

  // Si los parches fallan, profile.js ya los da como lista vacía, y entonces
  // el historial sale igual pero sin filtro de parche
  const list = await patches;
  if (list.length === 0) return;
  // Al cambiar de parche, primero se cambia la lista de campeones, porque el
  // elegido puede no estar en el parche nuevo y entonces hay que quitarlo
  const patchGroup = patchFilter(list, async (patch) => {
    filter.patch = patch;
    const champion = await champions.load(patch);
    if (champion === undefined || filter.patch !== patch) return;
    filter.champion = champion;
    loadMatches(results, filter);
  });
  const divider = el("span", { className: "filter-divider", attrs: { "aria-hidden": "true" } });
  filters.replaceChildren(patchGroup, divider, champions.element);
}
