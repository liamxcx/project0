import { el } from "../dom.js";
import { formatNumber } from "../format.js";
import { seasonOf } from "../season.js";

function gamesLabel(games) {
  return `${formatNumber(games, 0)} ${games === 1 ? "partida" : "partidas"}`;
}

export async function renderPatchSelect(container, patches, rankData, selected, onChange) {
  // Con la B, "General" son los totales de Riot, así que cuenta sus partidas
  const rank = await rankData.catch(() => null);
  const season = seasonOf(patches);
  const options = [
    {
      value: null,
      label: season ? `General · Temporada ${season}` : "General",
      meta: rank ? gamesLabel(rank.games) : "",
    },
    ...patches.map((p) => ({ value: p.patch, label: p.patch, meta: gamesLabel(p.games) })),
  ];

  const current = el("span", { className: "patch-current" });
  const caret = el("span", { className: "patch-caret", attrs: { "aria-hidden": "true" } });
  const button = el(
    "button",
    { className: "patch-button", attrs: { type: "button", "aria-haspopup": "true" } },
    el("span", { className: "patch-eyebrow" }, "Parche"),
    current,
    caret,
  );
  const items = options.map((option) =>
    el(
      "button",
      {
        className: "patch-option",
        attrs: { type: "button" },
        on: { click: () => choose(option.value) },
      },
      el("span", { className: "patch-option-label" }, option.label),
      el("span", { className: "patch-option-meta" }, option.meta),
    ),
  );
  const menu = el("div", { className: "patch-menu" }, items);

  function setOpen(open) {
    menu.hidden = !open;
    button.setAttribute("aria-expanded", String(open));
    caret.textContent = open ? "▲" : "▼";
  }

  function show(value) {
    current.textContent = value ?? "General";
    options.forEach((option, i) => items[i].classList.toggle("is-selected", option.value === value));
  }

  function choose(value) {
    setOpen(false);
    show(value);
    onChange(value);
  }

  button.addEventListener("click", () => setOpen(menu.hidden));
  // El menú se cierra al pulsar fuera o con Escape
  document.addEventListener("click", (event) => {
    if (!container.contains(event.target)) setOpen(false);
  });
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape") setOpen(false);
  });

  setOpen(false);
  show(selected);
  container.replaceChildren(el("div", { className: "patch-select" }, button, menu));
}
