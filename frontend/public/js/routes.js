const PROFILE_PREFIX = "/invocador/";

// Las URL de la página. El Riot ID va como nombre-tag, igual que en
// op.gg, y el tag no lleva guiones, así que se puede separar por el último.
export function profilePath(gameName, tagLine) {
  return `${PROFILE_PREFIX}${encodeURIComponent(`${gameName}-${tagLine}`)}`;
}

// Lo contrario de profilePath. Devuelve null si la URL no es de un
// perfil o está mal escrita, y entonces se enseña la portada.
export function parseProfilePath(pathname) {
  if (!pathname.startsWith(PROFILE_PREFIX)) return null;
  let riotId;
  try {
    riotId = decodeURIComponent(pathname.slice(PROFILE_PREFIX.length));
  } catch {
    return null;
  }
  const dash = riotId.lastIndexOf("-");
  if (dash <= 0 || dash === riotId.length - 1) return null;
  return { gameName: riotId.slice(0, dash), tagLine: riotId.slice(dash + 1) };
}
