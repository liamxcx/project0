import { getJson } from "../api.js";
import { el } from "../dom.js";

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
    const tag = el("span", { className: "summoner-tag" }, `#${summoner.tag_line}`);
    document.title = `${summoner.game_name}#${summoner.tag_line} · Project0`;
    content.replaceChildren(el("h1", {}, summoner.game_name, tag));
  } catch (error) {
    console.error("No se ha podido cargar el perfil.", error);
    content.replaceChildren(notice("No se ha podido cargar el perfil."));
  }
}
