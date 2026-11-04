import { getJson } from "../api.js";
import { championName, championSplashUrl, dataDragonReady } from "../ddragon.js";
import { el } from "../dom.js";
import { formatNumber } from "../format.js";

// Todos los invocadores seguidos son de EUW, así que va fijo. Guardar la región
// de cada uno está en MEJORAS.md
const REGION = "EUW";

// El parche público empieza por el año: 26.21 es de la temporada 2026
function seasonOf(patches) {
  if (patches.length === 0) return null;
  return 2000 + Number(patches[0].patch.split(".")[0]);
}

function stat(value, label, className = "") {
  return el(
    "div",
    {},
    el("p", { className: `stat-value ${className}`.trim() }, value),
    el("p", { className: "stat-label" }, label),
  );
}

function splash(champion) {
  const image = el("img", {
    className: "hero-splash",
    attrs: { src: championSplashUrl(champion), alt: "" },
  });
  // Sin la imagen queda el fondo oscuro, que también se lee bien
  image.addEventListener("error", () => image.remove(), { once: true });
  return image;
}

export async function renderHero(hero, summoner) {
  const message = (text) => el("p", { className: "hero-message" }, text);
  try {
    // El héroe va siempre por temporada, así que no lleva parche
    const [champions, patches] = await Promise.all([
      getJson("/champions"),
      getJson("/patches"),
      dataDragonReady,
    ]);
    const season = seasonOf(patches);
    const meta = [
      `${summoner.game_name}#${summoner.tag_line}`,
      REGION,
      season && `Temporada ${season}`,
    ]
      .filter(Boolean)
      .join(" · ");
    const title = el("h1", { className: "hero-meta" }, meta);

    if (champions.length === 0) {
      hero.replaceChildren(
        el("div", { className: "hero-body" }, title, message("Todavía no hay partidas esta temporada.")),
      );
      return;
    }

    const top = champions[0];
    const kda = [top.avg_kills, top.avg_deaths, top.avg_assists]
      .map((value) => formatNumber(value, 1))
      .join(" / ");
    // La API da null cuando no hay ninguna muerte
    const ratio = top.kda_ratio === null ? "Perfecto" : formatNumber(top.kda_ratio, 2);

    hero.replaceChildren(
      splash(top.champion),
      el("div", { className: "hero-shade" }),
      el(
        "div",
        { className: "hero-body" },
        el("div", {}, el("p", { className: "hero-kicker" }, "Campeón más jugado"), title),
        el(
          "div",
          {},
          el("h2", { className: "hero-name" }, championName(top.champion)),
          el("div", { className: "hero-rule" }),
          el(
            "div",
            { className: "hero-stats" },
            stat(String(top.games), "Partidas"),
            stat(`${formatNumber(top.winrate_pct, 0)}%`, "Winrate", "win"),
            stat(kda, "K / D / A medios"),
            stat(ratio, "Ratio KDA"),
          ),
        ),
      ),
    );
  } catch (error) {
    console.error("No se ha podido cargar el campeón más jugado.", error);
    hero.replaceChildren(
      el("div", { className: "hero-body" }, message("No se ha podido cargar el campeón más jugado.")),
    );
  }
}
