// Nombres de campeones, objetos y hechizos, sacados de Data Dragon. Si no
// responde, la página sigue funcionando con las claves internas.
import { fetchJson } from "./api.js";

const BASE_URL = "https://ddragon.leagueoflegends.com";
const LANGUAGE = "es_ES";
// Más corto que el de la API, porque las secciones esperan a Data Dragon antes
// de pintarse y no deben quedarse mucho rato en blanco si Riot no responde
const TIMEOUT_MS = 5000;

let version = null;
let champions = new Map();
let items = new Map();
let spells = new Map();

async function load() {
  try {
    const versions = await fetchJson(`${BASE_URL}/api/versions.json`, TIMEOUT_MS);
    const latest = versions[0];
    const data = (file) =>
      fetchJson(`${BASE_URL}/cdn/${latest}/data/${LANGUAGE}/${file}.json`, TIMEOUT_MS);
    const [championData, itemData, spellData] = await Promise.all([
      data("champion"),
      data("item"),
      data("summoner"),
    ]);

    // MATCH-V5 y Data Dragon no siempre escriben igual la clave, por ejemplo
    // FiddleSticks y Fiddlesticks, así que se buscan en minúsculas
    champions = new Map(
      Object.values(championData.data).map((champion) => [champion.id.toLowerCase(), champion]),
    );
    items = new Map(Object.entries(itemData.data));
    // Los hechizos vienen por nombre (SummonerFlash) y la API los da por número (4)
    spells = new Map(Object.values(spellData.data).map((spell) => [spell.key, spell]));
    version = latest;
  } catch (error) {
    console.warn("Data Dragon no está disponible, se usan las claves internas.", error);
  }
}

// Empieza a cargar en cuanto se importa el módulo, en paralelo con lo demás.
// Las secciones esperan esta promesa antes de pintar nombres o imágenes.
export const dataDragonReady = load();

export function championName(key) {
  return champions.get(String(key).toLowerCase())?.name ?? key;
}

export function itemName(id) {
  return items.get(String(id))?.name ?? String(id);
}

export function spellName(id) {
  return spells.get(String(id))?.name ?? String(id);
}

// Sin Data Dragon no hay versión con la que construir la dirección, así que
// devuelve null y quien la pida enseña otra cosa en su lugar
export function profileIconUrl(iconId) {
  if (version === null || iconId === null || iconId === undefined) return null;
  return `${BASE_URL}/cdn/${version}/img/profileicon/${encodeURIComponent(iconId)}.png`;
}
