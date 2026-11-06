import { getJson } from "../api.js";
import { el } from "../dom.js";
import { renderHero } from "./hero.js";
import { renderRank } from "./rank.js";

// Riot no distingue mayúsculas en el Riot ID, así que aquí tampoco
function sameRiotId(summoner, { gameName, tagLine }) {
  return (
    summoner.game_name.toLowerCase() === gameName.toLowerCase() &&
    summoner.tag_line.toLowerCase() === tagLine.toLowerCase()
  );
}

function notice(text) {
  const home = el("a", { attrs: { href: "/" } }, "Volver a la portada");
  return el("div", {}, el("p", {}, text), home);
}

export async function renderProfile(content, riotId) {
  try {
    const summoners = await getJson("/summoners");
    // La API solo tiene datos de los invocadores seguidos. Con otro Riot ID
    // enseñaría esos datos debajo de un nombre que no es el suyo
    const summoner = summoners.find((followed) => sameRiotId(followed, riotId));
    if (!summoner) {
      content.replaceChildren(notice("No seguimos a este invocador."));
      return;
    }
    document.title = `${summoner.game_name}#${summoner.tag_line} · Project0`;
    const hero = el("section", { className: "hero" });
    const rank = el("section", { className: "card" });
    const side = el("div", { className: "side" }, rank);
    content.replaceChildren(el("div", { className: "overview" }, hero, side));
    renderHero(hero, summoner);
    renderRank(rank);
  } catch (error) {
    console.error("No se ha podido cargar el perfil.", error);
    content.replaceChildren(notice("No se ha podido cargar el perfil."));
  }
}
