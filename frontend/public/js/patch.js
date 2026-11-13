// El parche elegido va en la URL (?parche=26.21), así que sobrevive a una
// recarga y se puede compartir
const PARAM = "parche";

// Viene de la URL, así que solo vale si es uno de los parches con partidas
export function selectedPatch(patches) {
  const value = new URLSearchParams(location.search).get(PARAM);
  return patches.some((p) => p.patch === value) ? value : null;
}

// replaceState cambia la URL sin recargar y sin añadir una entrada al
// historial, así que el botón de atrás sigue sacando del perfil
export function saveSelectedPatch(patch) {
  const url = new URL(location.href);
  if (patch) url.searchParams.set(PARAM, patch);
  else url.searchParams.delete(PARAM);
  history.replaceState(null, "", url);
}
