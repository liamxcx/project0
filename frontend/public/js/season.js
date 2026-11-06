// El parche público empieza por el año: 26.21 es de la temporada 2026
export function seasonOf(patches) {
  if (patches.length === 0) return null;
  return 2000 + Number(patches[0].patch.split(".")[0]);
}
