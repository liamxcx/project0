import { el } from "../dom.js";
import { formatNumber } from "../format.js";
import { rankName } from "./rank.js";

const DAYS = 30;
const DAY_MS = 24 * 60 * 60 * 1000;
const SVG_NS = "http://www.w3.org/2000/svg";
// La API cuenta los días en UTC, así que aquí también
const DATE_FORMAT = new Intl.DateTimeFormat("es-ES", {
  day: "numeric",
  month: "short",
  timeZone: "UTC",
});

function dayNumber(day) {
  return Date.parse(`${day}T00:00:00Z`) / DAY_MS;
}

function pointDate(point) {
  return DATE_FORMAT.format(new Date(`${point.day}T00:00:00Z`));
}

function pointRank(point) {
  return `${rankName(point.tier, point.division)} · ${formatNumber(point.league_points, 0)} LP`;
}

// La misma escalera que ladder_lp en la API: 400 LP por rango con divisiones, y
// Master, Grandmaster y Challenger siguen la cuenta a partir de Diamante
const DIVISION_TIERS = ["IRON", "BRONZE", "SILVER", "GOLD", "PLATINUM", "EMERALD", "DIAMOND"];
const DIVISIONS = ["IV", "III", "II", "I"];
const APEX_START = DIVISION_TIERS.length * 400;
// Pasos redondos para las líneas horizontales. Se coge el primero que deja
// cuatro líneas o menos
const STEPS = [25, 50, 100, 200, 250, 400, 500, 1000];

// De la escalera a algo legible. Por encima de Diamante solo se escriben los LP,
// porque a la misma altura se puede ser Master, Grandmaster o Challenger
function levelLabel(value) {
  if (value >= APEX_START) return `${formatNumber(value - APEX_START, 0)} LP`;
  const tier = DIVISION_TIERS[Math.floor(value / 400)];
  const division = DIVISIONS[Math.floor((value % 400) / 100)];
  const name = rankName(tier, division);
  // Justo al empezar una división basta con el nombre: "Oro II" y no "Oro II · 0"
  return value % 100 === 0 ? name : `${name} · ${value % 100}`;
}

function tierClass(point) {
  return `tier-${point.tier.toLowerCase()}`;
}

function header(points) {
  const first = points[0];
  const last = points[points.length - 1];
  const peak = points.reduce((best, point) => (point.ladder_lp > best.ladder_lp ? point : best));
  const diff = last.ladder_lp - first.ladder_lp;
  const change = el(
    "span",
    { className: `lp-change ${diff >= 0 ? "lp-up" : "lp-down"}` },
    `${diff >= 0 ? "▲" : "▼"} ${formatNumber(Math.abs(diff), 0)} LP`,
  );
  const peakLp = formatNumber(peak.league_points, 0);
  return [
    el("div", { className: "lp-head" }, el("p", { className: "card-title" }, "LP · Últimos 30 días"), change),
    el("p", { className: "lp-peak" }, `Peak: ${rankName(peak.tier, peak.division)} ${peakLp} LP`),
  ];
}

export async function renderLpChart(card, history) {
  const title = el("p", { className: "card-title" }, "LP · Últimos 30 días");
  const message = (text) => el("p", { className: "card-message" }, text);
  try {
    const points = await history;
    if (points.length < 2) {
      card.replaceChildren(
        title,
        message(
          "Todavía no hay datos suficientes. La gráfica se irá llenando con cada vuelta del collector.",
        ),
      );
      return;
    }

    // El color de la línea es el del rango actual, como en la tarjeta
    const last = points[points.length - 1];
    card.classList.add(`tier-${last.tier.toLowerCase()}`);

    // El eje horizontal va por fechas, así que los días sin foto dejan su hueco
    const end = Math.floor(Date.now() / DAY_MS);
    const start = end - DAYS;
    const x = (point) => ((dayNumber(point.day) - start) / DAYS) * 100;

    // Margen arriba y abajo para que la línea no toque los bordes. Con una racha
    // plana, el margen mínimo la deja en medio en vez de exagerar diferencias
    const values = points.map((point) => point.ladder_lp);
    const min = Math.min(...values);
    const max = Math.max(...values);
    const pad = Math.max(20, (max - min) * 0.1);
    const low = min - pad;
    const high = max + pad;
    const height = (value) => ((value - low) / (high - low)) * 100;
    const y = (point) => height(point.ladder_lp);

    const step = STEPS.find((candidate) => (high - low) / candidate <= 4) ?? STEPS.at(-1);
    // Se cuentan desde el inicio de Master, para que por encima caigan en LP
    // redondos. Por debajo también encajan, porque ahí empieza una división
    const first = APEX_START + Math.ceil((low - APEX_START) / step) * step;
    const levels = [];
    for (let value = first; value < high; value += step) {
      levels.push(
        el(
          "div",
          { className: "lp-level", style: { bottom: `${height(value)}%` } },
          el("span", {}, levelLabel(value)),
        ),
      );
    }

    // Un tramo recto entre foto y foto, del color del rango de la foto a la que
    // llega. Va por el rango y no por la altura, porque Master, Grandmaster y
    // Challenger comparten escala y entre ellos no hay una altura fija
    const top = (point) => (100 - y(point)).toFixed(2);
    const line = document.createElementNS(SVG_NS, "svg");
    line.setAttribute("class", "lp-line");
    line.setAttribute("viewBox", "0 0 100 100");
    line.setAttribute("preserveAspectRatio", "none");
    points.slice(1).forEach((point, i) => {
      const from = points[i];
      const path = document.createElementNS(SVG_NS, "path");
      path.setAttribute("class", tierClass(point));
      path.setAttribute(
        "d",
        `M ${x(from).toFixed(2)} ${top(from)} L ${x(point).toFixed(2)} ${top(point)}`,
      );
      path.setAttribute("vector-effect", "non-scaling-stroke");
      line.append(path);
    });

    // Una línea vertical por semana, contando hacia atrás desde hoy
    const weeks = [0, 7, 14, 21, 28].map((daysAgo) => {
      const day = end - daysAgo;
      const left = ((day - start) / DAYS) * 100;
      const label = daysAgo === 0 ? "Hoy" : DATE_FORMAT.format(new Date(day * DAY_MS));
      return { left, label };
    });
    const weekLines = weeks.map((week) =>
      el("div", { className: "lp-week", style: { left: `${week.left}%` } }),
    );
    const weekLabels = weeks.map((week) =>
      el(
        "span",
        { className: week.left > 95 ? "lp-week-label is-last" : "lp-week-label", style: { left: `${week.left}%` } },
        week.label,
      ),
    );

    // Los puntos van en HTML encima del SVG, porque un círculo dentro de un SVG
    // estirado se deformaría
    const dots = points.map((point) =>
      el("span", {
        className: `lp-dot ${tierClass(point)}`,
        style: { left: `${x(point)}%`, bottom: `${y(point)}%` },
      }),
    );

    // Al pasar el ratón, o el dedo, una línea marca la foto más cercana y un
    // tooltip enseña su día, su rango y sus LP
    const cursor = el("div", { className: "lp-cursor", attrs: { hidden: "" } });
    const tipDate = el("span", { className: "lp-tip-date" });
    const tipRank = el("span", { className: "lp-tip-rank" });
    const tip = el("div", { className: "lp-tip", attrs: { hidden: "" } }, tipDate, tipRank);
    const chart = el("div", { className: "lp-chart" }, weekLines, levels, line, dots, cursor, tip);

    function show(index) {
      const point = points[index];
      const left = x(point);
      cursor.hidden = false;
      tip.hidden = false;
      cursor.style.setProperty("left", `${left}%`);
      tip.style.setProperty("left", `${left}%`);
      // Cerca de los bordes el tooltip se apoya hacia dentro para no salirse
      tip.classList.toggle("is-left", left < 25);
      tip.classList.toggle("is-right", left > 75);
      tipDate.textContent = pointDate(point);
      tipRank.textContent = pointRank(point);
      dots.forEach((dot, i) => dot.classList.toggle("is-active", i === index));
    }

    function hide() {
      cursor.hidden = true;
      tip.hidden = true;
      dots.forEach((dot) => dot.classList.remove("is-active"));
    }

    chart.addEventListener("pointermove", (event) => {
      const box = chart.getBoundingClientRect();
      const at = ((event.clientX - box.left) / box.width) * 100;
      let nearest = 0;
      points.forEach((point, i) => {
        if (Math.abs(x(point) - at) < Math.abs(x(points[nearest]) - at)) nearest = i;
      });
      show(nearest);
    });
    chart.addEventListener("pointerleave", hide);

    card.replaceChildren(
      ...header(points),
      chart,
      el("div", { className: "lp-axis" }, weekLabels),
    );
  } catch (error) {
    console.error("No se ha podido cargar la gráfica de LP.", error);
    card.replaceChildren(title, message("No se ha podido cargar la gráfica de LP."));
  }
}
