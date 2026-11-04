import { el } from "../dom.js";

// De momento solo el Riot ID. La cabecera completa llega en el 3.3
export function renderProfile(section, { gameName, tagLine }) {
  const tag = el("span", { className: "summoner-tag" }, `#${tagLine}`);
  section.replaceChildren(el("h1", {}, gameName, tag));
  section.hidden = false;
}
