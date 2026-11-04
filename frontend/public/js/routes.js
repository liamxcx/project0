// Las direcciones de la página. El Riot ID va como nombre-tag, igual que en
// op.gg, y el tag no lleva guiones, así que se puede separar por el último.
export function profilePath(gameName, tagLine) {
  return `/invocador/${encodeURIComponent(`${gameName}-${tagLine}`)}`;
}
