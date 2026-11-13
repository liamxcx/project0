// Crea un elemento con sus hijos. Los textos entran siempre como nodos de texto,
// nunca como HTML, así que un "<" en un dato se ve tal cual y no se ejecuta.
export function el(tag, options = {}, ...children) {
  const node = document.createElement(tag);
  const { className, attrs = {}, style = {}, on = {} } = options;

  if (className) node.className = className;
  for (const [name, value] of Object.entries(attrs)) node.setAttribute(name, value);
  // Los estilos que dependen de los datos van por aquí y no en un atributo
  // style, porque la CSP de la página bloquea ese atributo
  for (const [name, value] of Object.entries(style)) node.style.setProperty(name, value);
  for (const [event, handler] of Object.entries(on)) node.addEventListener(event, handler);

  const present = children.flat().filter((child) => child != null && child !== false);
  node.append(...present);
  return node;
}
