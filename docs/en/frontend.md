# Frontend

English | [Español](../es/frontend.md)

A page in `frontend/public/`, served by nginx, that requests the data from
the API and renders it. Everything in that folder is public, and anything
outside it is not served. In Compose it opens at `http://localhost:8080`,
and in the cluster at `http://localhost` (see
[kubernetes.md](kubernetes.md#frontend)).

In Compose, nginx also acts as the reverse proxy, like Traefik in the
cluster. It passes everything that starts with `/api/` to the API, stripping
the prefix (`/api/rank` arrives as `/rank`), and serves the rest from disk.
That is why starting `frontend` also starts the API, and why the API's
responses arrive with `Server: nginx`.

The configuration is split into two files. `frontend/nginx-common.conf` has
the page's rules shared with the cluster, such as the routes, caching,
encoding and the CSP. `frontend/nginx-compose.conf` is the Compose `server`
block, with its port and the API proxy, and pulls in the common rules with
an `include`.

The API's internal routes (`/health`, `/ready`, `/docs`, `/redoc`,
`/openapi.json` and `/metrics`) are not published, and through the reverse
proxy they return 404. From the local machine they are still available at
`http://localhost:8000`.

In Compose, `frontend/public/` and the two nginx files are mounted as
read-only bind mounts. Editing the page and reloading the browser is
enough, without rebuilding or restarting anything. If the change does not
show up, it is usually the browser cache (`Ctrl + Shift + R`, or
`Cmd + Shift + R` on a Mac).

The nginx configuration, on the other hand, is only read at startup. After
changing it, `nginx -t` checks it and `nginx -s reload` reads it again,
without dropping open connections:

```bash
docker compose exec frontend nginx -t
docker compose exec frontend nginx -s reload
```

nginx looks up the IP of `api` at startup and keeps it. When Compose
recreates the API, for example with `up --build`, the API gets a new IP and
nginx would return 502. That is why `frontend` depends on `api` with
`restart: true`, and Compose restarts it after the API.

## Profile routes

Each profile has its own URL, `/invocador/Name-Tag`. It is not a file, so
`nginx-common.conf` returns `index.html` for everything that starts with
`/invocador/`, and the JavaScript reads the URL to know which profile to
show. Without that rule, opening a profile from a link or reloading it
would give a 404.

The Riot ID is split at the last hyphen, because the tag has no hyphens. If
it does not belong to a followed summoner, the page says so and shows
nothing, because the API only has data for the followed ones.

The patch selected at the top goes in the URL, as `?parche=26.21`, so it is
kept on reload and can be shared. It is changed with
`history.replaceState`, which updates the URL without reloading or adding a
history entry, so the back button still takes you out of the profile.

## What the page requests

When a profile is opened, the page requests from the API:

```
/summoners           check that the Riot ID belongs to a followed summoner
/rank                the rank and the season record
/rank/history        the LP chart
/patches             the patch selector and the match history filter
/summary             the summary, when a patch is selected
/champions           the hero section, "Más jugados" and the champion filter
/matches             the match history, 10 at a time
/matches/{match_id}  the details, when a game is opened
/refresh             the refresh button
```

## The refresh button

It is in the profile's top bar, which stays fixed when scrolling, so it can
be pressed from anywhere on the page. When pressed it sends
`POST /api/refresh` and, while the collector is running, it polls
`GET /api/refresh` every 3 seconds. It only polls during that time, because
each check means two requests to the Kubernetes API. When the collector
finishes, the page renders the profile again, which requests the data
again, and since the collector has cleared the API cache, the new data
arrives without reloading the page. After that it shows the minutes left
before it can be pressed again.

If the status cannot be checked, as in Compose, the button is not shown. An
open page does not find out about the hourly runs, only about the ones it
starts itself or the one that is running when it is opened.

## Page caching

nginx sends a different `Cache-Control` depending on what it serves:

| What | `Cache-Control` | Why |
|---|---|---|
| The page, the JavaScript, the CSS and the favicon | `no-cache` | They change with every version. The browser stores them but checks with the server before using them |
| The font and the emblems | `max-age=86400` | They almost never change, so they are valid for a day without asking |
| `/api/matches/{match_id}` | `no-cache`, with an ETag | Set by the API, not by nginx (see [api.md](api.md#etag-and-gzip)) |

## The font

The font, Archivo, is in `frontend/public/fonts/` with its license
(`OFL.txt`), and the same nginx serves it. This way the page does not
request anything from Google Fonts, which would see the IP of every visitor.

## The favicon

The tab icon is `frontend/public/favicon.svg`, an original drawing of a
three-lane map with a base in each corner, using the colors from
`styles.css`. It is an SVG because it looks sharp at any size, including
the 16 pixels of a tab. `index.html` declares it with `<link rel="icon">`,
and without that line the browser looks for it at `/favicon.ico`.

Browsers store the favicon separately from the rest of the page, so after
changing it the old one may keep showing. Opening `/favicon.svg` directly
and reloading it updates it.

## Data Dragon

The API only returns numbers and internal keys, such as the champion
`MonkeyKing`, the item `3089` or the spell `4`. The browser requests the
names (in Spanish) and the images from Data Dragon, Riot's public CDN. This
does not go through the API or use any requests from the Riot key.

When the page loads it requests `api/versions.json`, whose first entry is
the most recent version, and then uses it to request four files in parallel:

| File | What for |
|---|---|
| `champion.json` | The name of each champion, "Wukong" for `MonkeyKing` |
| `item.json` | The name of each item |
| `summoner.json` | The summoner spells. They come by name (`SummonerFlash`) and the API returns them by number |
| `runesReforged.json` | The rune trees, their runes and the path of each image |

The skills are not in `champion.json` but in a file per champion
(`champion/Ahri.json`). They are requested when the Build tab is opened,
for the ten players in the game, and each file only once while the page
stays open. Their images are downloaded at that moment, so when another
player is selected the browser already has them.

The rune shards have images in Data Dragon, but their names are not in any
JSON. That is why the names are written by hand in `ddragon.js`, and if
Riot changes the shards that list has to be updated.

If Data Dragon does not respond within 5 seconds, the page carries on
without it. The internal keys are shown instead of the names, and the image
slots stay empty.

## Rank emblems

The emblems in `frontend/public/emblems/` are Riot's official ones, from
`ranked-emblems-latest.zip`, in the *Icons and Emblems* section of the
League of Legends documentation on the developer portal. Data Dragon does
not have them. nginx serves them at `/emblems/`, mounted in Compose and
copied into the image in the cluster.

They are 1000 × 1000 pixels and about 500 KB each, so they are scaled down
to 256 × 256 and renamed after the `tier` from `/rank` in lowercase
(`master.png`). To regenerate them if Riot changes them, with ImageMagick:

```bash
unzip -j ranked-emblems-latest.zip "Ranked Emblems Latest/Rank=*" -d /tmp/emblems
for f in /tmp/emblems/Rank=*.png; do
  name=$(basename "$f" .png | sed "s/^Rank=//" | tr "[:upper:]" "[:lower:]")
  magick "$f" -resize 256x256 "frontend/public/emblems/$name.png"
done
```

On macOS, `sips -Z 256 "$f" --out ...`, which comes with the system, also
works.

## No CORS

The page requests `/api/matches` with a relative path, so the request goes
to the same place the page came from, with the same protocol, host and
port. To the browser, the page and the API have the same origin, and it can
read their responses without asking for permission.

If a page from another origin ever needs to read the API,
`CORSMiddleware` will have to be added in `api.py`.

Data Dragon is a different origin. Its JSON files are read with `fetch`,
and the browser only lets them be read because Data Dragon responds with
`Access-Control-Allow-Origin: *`. Images do not need that permission,
because an `<img>` can show an image from any origin.

## Encoding

Unless configured to, nginx sends CSS without declaring its encoding,
and the browser guesses. If it guesses wrong, non-ASCII characters, such as
the `›` arrow that separates the minutes in the build, come out garbled.
`charset` and `charset_types`, in `nginx-common.conf`, add
`; charset=utf-8` to the `Content-Type` of the CSS and the JavaScript.

## The CSP

Along with the page, nginx sends the `Content-Security-Policy` header,
which tells the browser where it may load each type of resource from. The one in
project0 only allows scripts, styles and fonts from the page's own origin,
and images and `fetch` requests from its own origin and from Data Dragon.
If someone managed to inject a `<script>` into the page, the browser would
not run it.

The policy is in `nginx-common.conf`, in the `$csp` variable, and it goes
inside the two `location` blocks that return `index.html`. It cannot go
outside them, because a `location` with its own `add_header` ignores the
ones outside it, and every `location` here has its own.

A CSP like this also blocks styles written in the HTML, including the
`style` attribute. That is why the page sets the data-dependent ones from
JavaScript, with `style.setProperty`, which the CSP does not block. If the
page ever loads something from another site, it has to be added to the
policy. Whatever it blocks shows up in the browser console, with the
reason.
