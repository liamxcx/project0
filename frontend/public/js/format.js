// Números con coma decimal, como se escriben en español
export function formatNumber(value, decimals) {
  return Number(value).toLocaleString("es-ES", {
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals,
  });
}
