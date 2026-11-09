import { el } from "./dom.js";

// Un solo tooltip para toda la página, que cambia de texto y de sitio. Sale al
// momento, al contrario que el title del navegador, que tarda y no se cambia
const tip = el("div", { className: "tip", attrs: { role: "tooltip" } });
tip.hidden = true;

let current = null;

// Encima del elemento y centrado. Si no cabe arriba va debajo, y nunca se sale
// por los lados de la ventana
function show(target) {
  current = target;
  tip.textContent = target.dataset.tip;
  tip.hidden = false;
  const box = target.getBoundingClientRect();
  let top = box.top - tip.offsetHeight - 6;
  if (top < 4) top = box.bottom + 6;
  const centered = box.left + box.width / 2 - tip.offsetWidth / 2;
  const left = Math.max(4, Math.min(centered, window.innerWidth - tip.offsetWidth - 4));
  tip.style.setProperty("top", `${top}px`);
  tip.style.setProperty("left", `${left}px`);
}

function hide() {
  current = null;
  tip.hidden = true;
}

// Un solo listener en el documento para todos los elementos con data-tip,
// también los que se crean después, como el marcador al abrir una partida
export function initTooltips() {
  document.body.append(tip);
  document.addEventListener("pointerover", (event) => {
    const target = event.target.closest("[data-tip]");
    if (target === current) return;
    if (target) show(target);
    else hide();
  });
  // Al salir de la ventana no llega ningún pointerover, y al desplazar la
  // página el tooltip se quedaría en un sitio que ya no es el suyo
  document.addEventListener("pointerout", (event) => {
    if (event.relatedTarget === null) hide();
  });
  window.addEventListener("scroll", hide, { passive: true });
}
