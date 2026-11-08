// Números con coma decimal, como se escriben en español
export function formatNumber(value, decimals) {
  return Number(value).toLocaleString("es-ES", {
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals,
  });
}

// "1 partida", "12 partidas"
export function formatGames(games) {
  return `${formatNumber(games, 0)} ${games === 1 ? "partida" : "partidas"}`;
}

const RELATIVE = new Intl.RelativeTimeFormat("es", { numeric: "always" });

// "hace 5 minutos", "hace 32 horas", "hace 3 días". Con el reloj del ordenador
// adelantado no debe salir "dentro de", así que nunca baja de 0
export function formatTimeAgo(date) {
  const minutes = Math.max(0, Math.round((Date.now() - new Date(date)) / 60000));
  if (minutes < 1) return "ahora";
  if (minutes < 60) return RELATIVE.format(-minutes, "minute");
  const hours = Math.round(minutes / 60);
  if (hours < 48) return RELATIVE.format(-hours, "hour");
  return RELATIVE.format(-Math.round(hours / 24), "day");
}
