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
let runes = new Map();

async function load() {
  try {
    const versions = await fetchJson(`${BASE_URL}/api/versions.json`, TIMEOUT_MS);
    const latest = versions[0];
    const data = (file) =>
      fetchJson(`${BASE_URL}/cdn/${latest}/data/${LANGUAGE}/${file}.json`, TIMEOUT_MS);
    const [championData, itemData, spellData, runeData] = await Promise.all([
      data("champion"),
      data("item"),
      data("summoner"),
      data("runesReforged"),
    ]);

    // MATCH-V5 y Data Dragon no siempre escriben igual la clave, por ejemplo
    // FiddleSticks y Fiddlesticks, así que se buscan en minúsculas
    champions = new Map(
      Object.values(championData.data).map((champion) => [champion.id.toLowerCase(), champion]),
    );
    items = new Map(Object.entries(itemData.data));
    // Los hechizos vienen por nombre (SummonerFlash) y la API los da por número (4)
    spells = new Map(Object.values(spellData.data).map((spell) => [spell.key, spell]));
    // Los árboles y sus runas van en el mismo mapa, porque sus números no se repiten
    const runeList = runeData.flatMap((style) => [
      style,
      ...style.slots.flatMap((slot) => slot.runes),
    ]);
    runes = new Map(runeList.map((rune) => [rune.id, rune]));
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

// La imagen grande del campeón. No lleva versión, pero la clave tiene que ir
// escrita como en Data Dragon. Si no ha cargado, se prueba con la de la API
export function championSplashUrl(key) {
  const id = champions.get(String(key).toLowerCase())?.id ?? key;
  return `${BASE_URL}/cdn/img/champion/splash/${encodeURIComponent(id)}_0.jpg`;
}

// Los iconos pequeños sí llevan versión, así que sin Data Dragon devuelven null
// y quien los pida deja la casilla vacía
function iconUrl(folder, file) {
  if (version === null || file === undefined) return null;
  return `${BASE_URL}/cdn/${version}/img/${folder}/${encodeURIComponent(file)}.png`;
}

export function championIconUrl(key) {
  return iconUrl("champion", champions.get(String(key).toLowerCase())?.id ?? key);
}

export function itemIconUrl(id) {
  return iconUrl("item", id);
}

// La API da el hechizo por número (4) y la imagen va por nombre (SummonerFlash)
export function spellIconUrl(id) {
  return iconUrl("spell", spells.get(String(id))?.id);
}

export function runeName(id) {
  return runes.get(id)?.name ?? String(id);
}

// Las imágenes de runas y árboles no llevan versión, pero la ruta de cada una
// solo viene en runesReforged.json, así que sin Data Dragon no hay imagen
export function runeIconUrl(id) {
  const icon = runes.get(id)?.icon;
  return icon === undefined ? null : `${BASE_URL}/cdn/img/${icon}`;
}
