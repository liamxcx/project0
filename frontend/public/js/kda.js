// Redondeado antes de elegir el color, para que un 2,996 que se lee 3,00 no
// salga del color de los que están por debajo de 3. Sin muertes da null
export function ratio({ kills, deaths, assists }) {
  if (deaths === 0) return null;
  return Math.round(((kills + assists) / deaths) * 100) / 100;
}

// Sin muertes cuenta como el ratio más alto
export function ratioClass(value) {
  if (value === null || value >= 4) return "ratio-high";
  if (value >= 3) return "ratio-good";
  if (value >= 2) return "ratio-ok";
  return "ratio-low";
}
