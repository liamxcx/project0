# Datos que la API devuelve hoy

Contrato real de `project0`. Cualquier maqueta debe ceñirse a estos campos.
Si hace falta algo que no está aquí, se anota en `FALTAN.md`.

La API se levanta en `http://localhost:8000`. Documentación interactiva
con datos reales en `http://localhost:8000/docs`.

Solo se guardan partidas de **ranked solo** (queueId 420) del propio
jugador. No hay datos de los otros nueve participantes de cada partida.

---

## `GET /health`

```json
{ "estado": "ok" }
```

## `GET /matches`

Las 20 partidas más recientes, de la más nueva a la más vieja.

```json
[
  {
    "champion": "Zeri",
    "position": "BOTTOM",
    "kills": 12,
    "deaths": 4,
    "assists": 7,
    "win": true,
    "played_at": "2026-09-09T22:14:03+02:00",
    "duration_seconds": 1834,
    "game_version": "16.17.810.4348",
    "patch": "26.17"
  }
]
```

| Campo | Tipo | Notas |
|---|---|---|
| `champion` | texto | Nombre interno de Riot: `Zeri`, `MonkeyKing` (Wukong), `Kaisa` |
| `position` | texto o `null` | `TOP`, `JUNGLE`, `MIDDLE`, `BOTTOM`, `UTILITY` |
| `kills` `deaths` `assists` | entero | El KDA como ratio no viene calculado; lo hace el frontend |
| `win` | booleano | |
| `played_at` | fecha ISO | Con zona horaria |
| `duration_seconds` | entero | En segundos; el formato `mm:ss` lo hace el frontend |
| `game_version` | texto | Numeración interna de Riot |
| `patch` | texto | Parche público, el que ve el jugador. Va 10 por delante del interno |

## `GET /champions`

Un agregado por campeón, ordenado por partidas jugadas.

```json
[
  {
    "champion": "Zeri",
    "games": 7,
    "wins": 6,
    "winrate_pct": 85.7,
    "avg_kills": 8.9,
    "avg_deaths": 4.6,
    "avg_assists": 6.9
  }
]
```

| Campo | Tipo | Notas |
|---|---|---|
| `games` `wins` | entero | |
| `winrate_pct` | número | Ya en porcentaje, sin el símbolo. `85.7` es 85,7 % |
| `avg_kills` `avg_deaths` `avg_assists` | número | Medias con un decimal |

## `GET /champions/{champion}`

Lo mismo pero de un solo campeón. No distingue mayúsculas: `zeri`, `Zeri`
y `ZERI` valen igual.

Devuelve `404` con `{"detail": "Sin partidas con X"}` si no hay ninguna.

---

## Imágenes

Los iconos de campeón salen de Data Dragon, el CDN público de Riot:

```
https://ddragon.leagueoflegends.com/cdn/16.17.1/img/champion/Zeri.png
```

El nombre del fichero es el `champion` tal cual lo devuelve la API. La
versión de la URL es la interna (`16.17.1`), no el `patch`.

Está pendiente decidir si se cargan desde ahí o se descargan a la carpeta
`frontend`.
