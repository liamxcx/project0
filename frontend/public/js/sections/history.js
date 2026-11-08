import { getJson } from "../api.js";
import { championName, championSplashUrl, dataDragonReady } from "../ddragon.js";
import { el } from "../dom.js";
import { formatNumber } from "../format.js";

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

async function fetchPage(offset) {
  const [page] = await Promise.all([getJson("/matches", { offset }), dataDragonReady]);
  return page;
}

// Añade la tanda debajo de las que ya hay y deja al final el botón para pedir
// la siguiente, o el aviso de que no quedan más
function showPage(list, footer, page, offset) {
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
      showPage(list, footer, await fetchPage(next), next);
    } catch (error) {
      console.error("No se han podido cargar más partidas.", error);
      const warning = el("p", { className: "matches-end" }, "No se han podido cargar más partidas.");
      footer.replaceChildren(warning, button);
      button.disabled = false;
    }
  });
  footer.replaceChildren(button);
}

export async function renderHistory(section) {
  const head = el("div", { className: "section-head" }, el("h2", {}, "Últimas partidas"));
  const message = (text) => el("p", { className: "section-message" }, text);
  try {
    const page = await fetchPage(0);
    if (page.matches.length === 0) {
      section.replaceChildren(head, message("Todavía no hay partidas guardadas."));
      return;
    }
    const list = el("ol", { className: "matches" });
    const footer = el("div", { className: "matches-footer" });
    section.replaceChildren(head, list, footer);
    showPage(list, footer, page, 0);
  } catch (error) {
    console.error("No se ha podido cargar el historial.", error);
    section.replaceChildren(head, message("No se ha podido cargar el historial."));
  }
}
