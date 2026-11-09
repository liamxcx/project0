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

// Un árbol de runas con sus filas, o null si no es un árbol o no hay Data Dragon
export function runeTree(id) {
  const tree = runes.get(id);
  return tree?.slots ? tree : null;
}

// Data Dragon sirve las imágenes de los fragmentos, pero no los nombra en ningún
// JSON. Por eso van aquí a mano. Si Riot los cambia, hay que actualizar la lista
const SHARDS = new Map([
  [5008, ["Fuerza adaptable", "StatModsAdaptiveForceIcon.png"]],
  [5005, ["Velocidad de ataque", "StatModsAttackSpeedIcon.png"]],
  [5007, ["Aceleración de habilidades", "StatModsCDRScalingIcon.png"]],
  [5010, ["Velocidad de movimiento", "StatModsMovementSpeedIcon.png"]],
  [5001, ["Vida según el nivel", "StatModsHealthScalingIcon.png"]],
  [5011, ["Vida", "StatModsHealthPlusIcon.png"]],
  [5013, ["Tenacidad y resistencia a ralentizaciones", "StatModsTenacityIcon.png"]],
]);

// Las tres filas de fragmentos, como salen en el juego: ofensiva, flexible y defensiva
export const SHARD_ROWS = [
  [5008, 5005, 5007],
  [5008, 5010, 5001],
  [5011, 5013, 5001],
];

export function shardName(id) {
  return SHARDS.get(id)?.[0] ?? String(id);
}

export function shardIconUrl(id) {
  const file = SHARDS.get(id)?.[1];
  return file === undefined ? null : `${BASE_URL}/cdn/img/perk-images/StatMods/${file}`;
}

// Las habilidades de cada campeón van en su propio fichero, así que se piden al
// verlo por primera vez y se guarda la promesa para no repetir la petición
const championSpellRequests = new Map();

// Imágenes que se están descargando por adelantado. Se guardan hasta que
// terminan para que el navegador no las descarte a medias
const warming = new Set();

function warmUp(url) {
  const image = new Image();
  warming.add(image);
  image.addEventListener("load", () => warming.delete(image), { once: true });
  image.addEventListener("error", () => warming.delete(image), { once: true });
  image.src = url;
}

export function championSpells(key) {
  const id = champions.get(String(key).toLowerCase())?.id ?? key;
  if (version === null) return Promise.resolve(null);
  if (!championSpellRequests.has(id)) {
    const url = `${BASE_URL}/cdn/${version}/data/${LANGUAGE}/champion/${encodeURIComponent(id)}.json`;
    const request = fetchJson(url, TIMEOUT_MS)
      .then((data) => {
        const spells = data.data[id].spells.map((spell) => ({
          name: spell.name,
          icon: `${BASE_URL}/cdn/${version}/img/spell/${encodeURIComponent(spell.image.full)}`,
        }));
        // Las imágenes se piden ya, sin esperar a que alguien las enseñe. Cuando
        // el icono las pida, el navegador las tendrá en su caché
        spells.forEach((spell) => warmUp(spell.icon));
        return spells;
      })
      .catch((error) => {
        // Sin guardar el fallo, para que se pueda volver a intentar
        championSpellRequests.delete(id);
        console.warn("Sin las habilidades del campeón, se quedan las letras.", error);
        return null;
      });
    championSpellRequests.set(id, request);
  }
  return championSpellRequests.get(id);
}
