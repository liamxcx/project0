# Lo que falta para que la página enseñe la maqueta con datos reales

La API ya tiene todos los endpoints que usa la maqueta. Esto es lo que queda
fuera de ella. Cuando algo se hace, se borra de aquí, y el fichero se borra
cuando quede vacío.

## Nombres e imágenes de Data Dragon

Decidido: la página los pide directamente a Data Dragon, el CDN público de
Riot, que responde con `Access-Control-Allow-Origin: *`. Falta escribirlo en
la página.

- **Versión.** La última de `api/versions.json` (hoy `16.21.1`).
- **Nombre legible del campeón.** La API devuelve `Kaisa` o `MonkeyKing` y la
  página tiene que escribir "Kai'Sa" o "Wukong". Está en
  `data/es_ES/champion.json`.
- **Objetos y hechizos en español.** La API da el número (3089, 4) y la página
  enseña el icono y el nombre ("Destello"). Están en `data/es_ES/item.json` y
  `data/es_ES/summoner.json`.
- **Splash del campeón más jugado**, para el fondo del héroe
  (`img/champion/splash/{clave}_0.jpg`).
- **Icono de perfil.** `/summoners` devuelve `profile_icon_id` y la imagen está
  en `img/profileicon/{id}.png`.

## Región

- **"EUW" junto al nombre.** Es la región que usa el collector. Tiene que salir
  de la configuración y no estar escrita a mano en la página.

## Para después de m5

- **"+LP" de cada partida.** Riot no lo da por partida. Habría que guardar el
  LP antes y después de cada una, así que el collector tendría que tomar una
  foto de la clasificatoria cada pocos minutos.
