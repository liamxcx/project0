import { el } from "../dom.js";
import { dropdown } from "../dropdown.js";
import { formatGames } from "../format.js";
import { seasonOf } from "../season.js";

export async function renderPatchSelect(container, patches, rankData, selected, onChange) {
  // Con la B, "General" son los totales de Riot, así que cuenta sus partidas
  const rank = await rankData.catch(() => null);
  const season = seasonOf(patches);
  const options = [
    {
      value: null,
      label: season ? `General · Temporada ${season}` : "General",
      meta: rank ? formatGames(rank.games) : "",
    },
    ...patches.map((p) => ({ value: p.patch, label: p.patch, meta: formatGames(p.games) })),
  ];

  const current = el("span", { className: "patch-current" });
  const caret = el("span", { className: "patch-caret", attrs: { "aria-hidden": "true" } });
  const button = el(
    "button",
    { className: "patch-button", attrs: { type: "button" } },
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
  const select = dropdown("patch-select", button, caret, menu);

  function show(value) {
    current.textContent = value ?? "General";
    options.forEach((option, i) => items[i].classList.toggle("is-selected", option.value === value));
  }

  function choose(value) {
    select.close();
    show(value);
    onChange(value);
  }

  show(selected);
  container.replaceChildren(select.element);
}
