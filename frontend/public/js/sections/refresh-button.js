import { getJson, postJson, RequestError } from "../api.js";
import { el } from "../dom.js";

// Cada cuánto se pregunta si el collector ha terminado. Solo mientras está en
// marcha, porque cada consulta son dos peticiones a la API de Kubernetes
const POLL_MS = 3000;

export function renderRefreshButton(container, onDone) {
  const button = el("button", {
    className: "refresh-button",
    attrs: { type: "button" },
    on: { click: refresh },
  });
  let timer = null;
  let wasRunning = false;

  function show(text, { disabled = false, busy = false } = {}) {
    button.textContent = text;
    button.disabled = disabled;
    button.setAttribute("aria-busy", String(busy));
  }

  function later(next, ms) {
    clearTimeout(timer);
    timer = setTimeout(next, ms);
  }

  // Cuenta atrás en minutos. Al acabar, el botón vuelve a estar activo
  function showWait(until) {
    const seconds = Math.ceil((until - Date.now()) / 1000);
    if (seconds <= 0) {
      show("Actualizar");
      return;
    }
    show(`Actualizar en ${Math.ceil(seconds / 60)} min`, { disabled: true });
    later(() => showWait(until), Math.min(seconds, 60) * 1000);
  }

  async function update() {
    let state;
    try {
      state = await getJson("/refresh");
    } catch (error) {
      // Un fallo suelto mientras corre el collector no lo esconde, se vuelve a probar
      if (wasRunning) {
        later(update, POLL_MS);
        return;
      }
      // Fuera de Kubernetes la API no puede lanzar el collector, así que no se enseña
      console.warn("No se puede consultar la actualización.", error);
      container.replaceChildren();
      return;
    }
    // Se añade cuando ya se sabe su estado, para que no salga vacío un momento
    if (!button.isConnected) container.replaceChildren(button);

    if (state.running) {
      wasRunning = true;
      show("Actualizando…", { disabled: true, busy: true });
      later(update, POLL_MS);
      return;
    }
    if (wasRunning) {
      wasRunning = false;
      onDone();
    }
    showWait(Date.now() + state.retry_after * 1000);
  }

  async function refresh() {
    show("Actualizando…", { disabled: true, busy: true });
    try {
      await postJson("/refresh");
    } catch (error) {
      // Con 409 ya había uno en marcha y con 429 toca esperar. El estado dice cuál
      if (!(error instanceof RequestError && [409, 429].includes(error.status))) {
        console.error("No se ha podido lanzar la actualización.", error);
      }
    }
    update();
  }

  update();
}
