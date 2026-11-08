import { el } from "./dom.js";

// Junta un botón y su menú. El botón lo abre y lo cierra, y el menú también se
// cierra al pulsar fuera o con Escape. Devuelve el elemento para colocarlo en la
// página y close para cerrarlo después de elegir una opción. onOpen es opcional
// y se llama cada vez que se abre
export function dropdown(className, button, caret, menu, onOpen) {
  const element = el("div", { className }, button, menu);

  function setOpen(open) {
    menu.hidden = !open;
    button.setAttribute("aria-expanded", String(open));
    caret.textContent = open ? "▲" : "▼";
    if (open && onOpen) onOpen();
  }

  button.setAttribute("aria-haspopup", "true");
  button.addEventListener("click", () => setOpen(menu.hidden));
  document.addEventListener("click", (event) => {
    if (!element.contains(event.target)) setOpen(false);
  });
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape") setOpen(false);
  });

  setOpen(false);
  return { element, close: () => setOpen(false) };
}
