// fetch no tiene límite de tiempo, así que sin esto una petición colgada dejaría
// la página cargando para siempre
const TIMEOUT_MS = 10000;

export class RequestError extends Error {
  constructor(message, status = null) {
    super(message);
    this.name = "RequestError";
    this.status = status;
  }
}

// Pide un JSON a cualquier URL. fetch no falla con un 404 o un 500, solo
// cuando no hay respuesta, así que el código se comprueba a mano.
export async function fetchJson(url, timeoutMs = TIMEOUT_MS) {
  let response;
  try {
    response = await fetch(url, { signal: AbortSignal.timeout(timeoutMs) });
  } catch (error) {
    if (error.name === "TimeoutError") {
      throw new RequestError(`Sin respuesta en ${timeoutMs / 1000} s: ${url}`);
    }
    throw new RequestError(`No se ha podido conectar: ${url}`);
  }

  if (!response.ok) {
    throw new RequestError(`Respuesta ${response.status}: ${url}`, response.status);
  }
  // Una respuesta 200 que no es JSON, por ejemplo una página de error de un proxy
  try {
    return await response.json();
  } catch {
    throw new RequestError(`La respuesta no es JSON: ${url}`, response.status);
  }
}

// Pide algo a la API de project0. La ruta es relativa, así que va al mismo
// origen que la página. URLSearchParams codifica los valores de los filtros.
export function getJson(path, params = {}) {
  const query = new URLSearchParams();
  for (const [name, value] of Object.entries(params)) {
    if (value !== null && value !== undefined && value !== "") query.set(name, value);
  }
  const queryString = query.toString();
  return fetchJson(queryString ? `/api${path}?${queryString}` : `/api${path}`);
}
