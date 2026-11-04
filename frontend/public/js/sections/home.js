import { getJson } from "../api.js";
import { dataDragonReady, profileIconUrl } from "../ddragon.js";
import { el } from "../dom.js";
import { profilePath } from "../routes.js";

// "Charli xcx" → "CX". Es lo que se ve en lugar del icono si no se puede cargar
function initials(name) {
  const words = name.trim().split(/\s+/);
  const letters = words.length > 1 ? words[0][0] + words[1][0] : name.slice(0, 2);
  return letters.toUpperCase();
}

function placeholder(name) {
  return el("span", { className: "summoner-initials" }, initials(name));
}

function icon(summoner) {
  const url = profileIconUrl(summoner.profile_icon_id);
  if (url === null) return placeholder(summoner.game_name);

  const image = el("img", {
    className: "summoner-icon",
    attrs: { src: url, alt: "", width: "36", height: "36" },
  });
  // Si Data Dragon contestó pero ese icono no existe, también van las iniciales
  const fallBack = () => image.replaceWith(placeholder(summoner.game_name));
  image.addEventListener("error", fallBack, { once: true });
  return image;
}

function row(summoner) {
  const href = profilePath(summoner.game_name, summoner.tag_line);
  const tag = el("span", { className: "summoner-tag" }, `#${summoner.tag_line}`);
  return el(
    "a",
    { className: "summoner-row", attrs: { href } },
    icon(summoner),
    el("span", { className: "summoner-name" }, summoner.game_name, tag),
    el("span", { className: "row-arrow", attrs: { "aria-hidden": "true" } }, "→"),
  );
}

export async function renderHome(list) {
  const message = (text) => el("p", { className: "list-message" }, text);
  try {
    const [summoners] = await Promise.all([getJson("/summoners"), dataDragonReady]);
    if (summoners.length === 0) {
      list.replaceChildren(message("Todavía no se sigue a ningún invocador."));
      return;
    }
    list.replaceChildren(...summoners.map(row));
  } catch (error) {
    console.error("No se ha podido cargar la lista de invocadores.", error);
    list.replaceChildren(message("No se ha podido cargar la lista de invocadores."));
  }
}
