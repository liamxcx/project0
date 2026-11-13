# Frontend

Una página en `frontend/public/`, servida por nginx, que pide los datos a la
API y los pinta. Todo lo que hay en esa carpeta es público, y lo que no está
en ella no se sirve. En Compose se abre en `http://localhost:8080`, y en el
clúster en `http://localhost` (ver [kubernetes.md](kubernetes.md#frontend)).

En Compose, nginx hace también de reverse proxy, como Traefik en el
clúster. Pasa todo lo que empieza por `/api/` a la API quitándole el prefijo
(`/api/rank` llega como `/rank`) y sirve lo demás desde el disco. Por eso
levantar el `frontend` levanta también la API, y las respuestas de la API
llegan con `Server: nginx`.

La configuración va en dos ficheros. `frontend/nginx-common.conf` tiene las
reglas de la página, que son las mismas en el clúster, como las rutas, la
caché, la codificación y la CSP. `frontend/nginx-compose.conf` es el `server`
de Compose, con su puerto y el proxy de la API, y trae las comunes con un
`include`.

Las rutas internas de la API (`/health`, `/ready`, `/docs`, `/redoc` y
`/openapi.json`) no se publican, y por el reverse proxy devuelven 404.
Desde la propia máquina siguen en `http://localhost:8000`.

En Compose se montan `frontend/public/` y los dos ficheros de nginx, como
bind mounts de solo lectura. Editar la página y recargar el navegador
basta, sin reconstruir ni reiniciar nada. Si el cambio no se ve, suele ser la
caché del navegador (`Ctrl + Shift + R`, o `Cmd + Shift + R` en Mac).

La configuración de nginx, en cambio, solo se lee al arrancar. Después de
cambiarla se comprueba y se recarga, sin cortar las conexiones abiertas:

```bash
docker compose exec frontend nginx -t          # comprueba la configuración
docker compose exec frontend nginx -s reload   # la vuelve a leer
```

nginx busca la IP de `api` al arrancar y se queda con ella. Cuando Compose
recrea la API, por ejemplo con `up --build`, la API cambia de IP y nginx
respondería 502. Por eso el `frontend` depende de `api` con `restart: true`,
y Compose lo reinicia detrás de ella.

## Rutas del perfil

Cada perfil tiene su URL, `/invocador/Nombre-Tag`. No es un fichero, así
que `nginx-common.conf` devuelve `index.html` para todo lo que empieza por
`/invocador/`, y el JavaScript lee la URL para saber qué perfil enseñar.
Sin esa regla, abrir un perfil desde un enlace o recargarlo daría 404.

El Riot ID se separa por el último guion, porque el tag no lleva guiones. Si
no es de un invocador seguido, la página lo dice y no enseña nada, porque la
API solo tiene datos de los seguidos.

El parche elegido arriba va en la URL, como `?parche=26.21`, así que se
mantiene al recargar y se puede compartir. Se cambia con
`history.replaceState`, que actualiza la URL sin recargar ni añadir una
entrada al historial, así que el botón de atrás sigue sacando del perfil.

## Qué pide la página

Al abrir un perfil, la página pide a la API:

```
/summoners           comprobar que el Riot ID es de un invocador seguido
/rank                el rango y el balance de la temporada
/rank/history        la gráfica de LP
/patches             el selector de parche y el filtro del historial
/summary             el resumen, al elegir un parche
/champions           el héroe, "Más jugados" y el filtro de campeón
/matches             el historial, de 10 en 10
/matches/{match_id}  el detalle, al abrir una partida
```

## Caché de la página

nginx manda un `Cache-Control` distinto según lo que sirve:

| Qué | `Cache-Control` | Por qué |
|---|---|---|
| La página, el JavaScript y el CSS | `no-cache` | Cambian con cada versión. El navegador los guarda, pero pregunta antes de usarlos |
| La fuente y los emblemas | `max-age=86400` | Casi nunca cambian, así que valen un día sin preguntar |
| `/api/matches/{match_id}` | `no-cache`, con ETag | La pone la API, no nginx (ver [api.md](api.md#etag-y-gzip)) |

## La fuente

La fuente, Archivo, va en `frontend/public/fonts/` con su licencia
(`OFL.txt`), y la sirve el mismo nginx. Así la página no le pide nada a
Google Fonts, que vería la IP de cada visita.

## Data Dragon

La API solo da números y claves internas, como el campeón `MonkeyKing`, el
objeto `3089` o el hechizo `4`. Los nombres en español y las imágenes los pide
el navegador a Data Dragon, el CDN público de Riot. No pasa por la API ni gasta
peticiones de la clave de Riot.

Al cargar la página se pide `api/versions.json`, cuya primera versión es la
más reciente, y con ella cuatro ficheros a la vez:

| Fichero | Para qué |
|---|---|
| `champion.json` | El nombre de cada campeón, "Wukong" para `MonkeyKing` |
| `item.json` | El nombre de cada objeto |
| `summoner.json` | Los hechizos de invocador. Vienen por nombre (`SummonerFlash`) y la API los da por número |
| `runesReforged.json` | Los árboles de runas, sus runas y la ruta de cada imagen |

Las habilidades no están en `champion.json`, sino en un fichero por campeón
(`champion/Ahri.json`). Se piden al abrir la pestaña Build, las de los diez
jugadores de la partida, y cada fichero una sola vez mientras la página siga
abierta. Sus imágenes se descargan en ese momento, así que al elegir a otro
jugador el navegador ya las tiene.

Los fragmentos de runas tienen imagen en Data Dragon, pero su nombre no sale
en ningún JSON. Por eso los nombres van escritos a mano en `ddragon.js`, y si
Riot cambia los fragmentos hay que actualizar esa lista.

Si Data Dragon no responde en 5 segundos, la página sigue sin él. Salen las
claves internas en vez de los nombres, y las casillas de las imágenes se
quedan vacías.

## Emblemas de rango

Los emblemas de `frontend/public/emblems/` son los oficiales de Riot, de
`ranked-emblems-latest.zip`, en la sección *Icons and Emblems* de la
documentación de League of Legends del portal de desarrolladores. Data
Dragon no los tiene. nginx los sirve en `/emblems/`, montados en Compose y
copiados dentro de la imagen en el clúster.

Vienen a 1000 × 1000 píxeles y unos 500 KB cada uno, así que se reducen a
256 y se renombran como el `tier` de `/rank` en minúsculas (`master.png`).
Para rehacerlos si Riot los cambia, con ImageMagick:

```bash
unzip -j ranked-emblems-latest.zip "Ranked Emblems Latest/Rank=*" -d /tmp/emblems
for f in /tmp/emblems/Rank=*.png; do
  name=$(basename "$f" .png | sed 's/^Rank=//' | tr '[:upper:]' '[:lower:]')
  magick "$f" -resize 256x256 "frontend/public/emblems/$name.png"
done
```

En macOS también vale `sips -Z 256 "$f" --out ...`, que viene con el sistema.

## Sin CORS

La página pide `/api/matches` con una ruta relativa, así que la petición va
al mismo sitio del que salió la página: mismo protocolo, host y puerto.
Para el navegador, la página y la API son el mismo origen, y puede leer sus
respuestas sin pedir permiso.

Si algún día una página de otro origen necesita leer la API, habrá que
añadir `CORSMiddleware` en `api.py`.

Data Dragon sí es otro origen. Sus JSON se leen con `fetch`, y el navegador
solo los deja leer porque Data Dragon responde con
`Access-Control-Allow-Origin: *`. Las imágenes no necesitan ese permiso,
porque un `<img>` puede enseñar una imagen de cualquier origen.

## La codificación

Si no se le pide, nginx manda el CSS sin decir en qué codificación está, y el
navegador la adivina. Si adivina mal, los caracteres que no son ASCII, como
la flecha `›` que separa los minutos de la build, salen rotos. `charset` y
`charset_types`, en `nginx-common.conf`, añaden `; charset=utf-8` al
`Content-Type` del CSS y del JavaScript.

## La CSP

Con la página, nginx manda la cabecera `Content-Security-Policy`, que le dice
al navegador de dónde puede cargar cada cosa. La de project0 solo deja cargar
scripts, estilos y fuentes del propio origen, e imágenes y peticiones con
`fetch` del propio origen y de Data Dragon. Si alguien consiguiera colar un
`<script>` en la página, el navegador no lo ejecutaría.

La política está en `nginx-common.conf`, en la variable `$csp`, y va dentro de
las dos `location` que devuelven `index.html`. No puede ir fuera, porque una
`location` con su propio `add_header` ignora los de fuera, y todas tienen el
suyo.

Una CSP así también bloquea los estilos escritos en el HTML, incluido el
atributo `style`. Por eso la página pone los que dependen de los datos desde
JavaScript, con `style.setProperty`, que la CSP no bloquea. Si algún día la
página carga algo de otro sitio, hay que añadirlo a la política. Lo que
bloquea sale en la consola del navegador, con el motivo.
