# Collector

English | [Español](../es/collector.md)

`collector.py` starts, requests what it is missing from Riot, stores it in
PostgreSQL and exits. In the cluster a CronJob runs it every hour (see
[kubernetes.md](kubernetes.md#collector)), and so does the page's refresh
button. In Compose it runs once on `up`, and after that by hand with
`docker compose run --rm collector`.

When it finishes it clears the API cache, so the page shows the new data
right away (see [api.md](api.md#redis-cache)). It does this even when there
are no new games, because the ranked standing is stored on every run.

## What it requests from Riot

Given a Riot ID, on each run:

| Riot API | What for |
|---|---|
| ACCOUNT-V1 | The summoner's PUUID |
| SUMMONER-V4 | Their profile icon and level |
| LEAGUE-V4 | A snapshot of their solo/duo ranked standing and the rank of the other nine players in each game |
| MATCH-V5 | The list of their latest games and, for each one, the details and the timeline |

Before downloading, it checks which games in the list are already in the
database and skips them, so it only requests what it is missing from Riot.
Each game is stored in its own transaction. If one fails, it is skipped, the
others are stored, and the next run tries it again.

The routes use different hosts depending on the API. ACCOUNT-V1 and
MATCH-V5 go through the regional host, `europe.api.riotgames.com`.
LEAGUE-V4 and SUMMONER-V4 go through the platform host,
`euw1.api.riotgames.com`.

Getting each player's rank takes one request per player. That is nine more per
game, because the followed summoner's rank is already requested for
`ranked_snapshots`. Within a single run it is reused if the player appears
in several games. It is the rank at the moment the game is stored, because
Riot does not give the rank the player had when the game was played. It is
requested with the player's PUUID, but only the rank is stored.

The three Riot variables (`RIOT_API_KEY`, `RIOT_GAME_NAME` and
`RIOT_TAG_LINE`) are read in `collector.py` and not in `config.py`.
Importing `config.py` runs the whole file, so if they were there the API
would not start without them even though it does not use them, and the
tests could not run without a `.env` either.

## Ranked solo/duo only

The collector only requests the IDs of that queue from Riot (`queue=420` in
the MATCH-V5 list). The filter is applied in the request, not when storing,
so games from other modes are never downloaded. Without it, Riot returns the
latest games of any type, and normal and Swiftplay games end up mixed in
with ranked ones, skewing every average.

`RANKED_SOLO_QUEUE` is in `config.py` and not in the `.env` because it is
not configuration that changes between environments. The whole project is
built around that queue, and changing it would make what is already stored
meaningless.

`matches.queue_id` is still stored even though it is always 420 today,
because it is the value as Riot sends it. The API does not expose it.

## The timeline

The final items (`item0`…`item6`) show how the build ended up, not the
order it was put together in. The order is in another endpoint, the
*timeline*, which is one more request per game:

```
/lol/match/v5/matches/{id}          details    → matches, participants
/lol/match/v5/matches/{id}/timeline events     → item_purchases, skill_levelups
```

It comes split into frames, one per minute, and each frame carries its
events: purchases, kills, towers, wards. Only two event types are stored,
`ITEM_PURCHASED` and `SKILL_LEVEL_UP`, for all ten players. That is about
300 and 180 rows per game respectively.

The response is close to 1 MB, so it is not stored whole. Extracting the
four fields that matter brings it down to about 19 KB per game, fifty times
smaller.

Three things the collector does when processing it:

- **It discards events with `participantId` 0.** Players go from 1 to 10,
  and the ones with 0 are artifacts from the start of the game.
- **It applies the `ITEM_UNDO` events.** Buying something and undoing it in
  the shop produces a purchase event and an undo event. Without this, the
  first item of a build could be one that was returned.
- **It deletes before inserting.** The key of these tables is an
  auto-generated id, so a `--refetch` would duplicate the rows instead of
  replacing them.

Players are identified by their number within the game (1-10), not by
PUUID. That is enough to analyze builds, and this way nobody else's
identity is stored. `participants.participant_id` is that same number, so
the purchases of any of the ten players come from joining the two tables.

## Inserting without duplicates

The inserts use `ON CONFLICT ... DO UPDATE`. If the row is not there it is
inserted, and if it is, it is updated with the new values, so the collector
can run as many times as needed and the result is always the same.
`DO NOTHING` would not work, because it would ignore the whole row and
columns added later could never be filled in.

The values that come from Riot are passed to the query as parameters (`%s`
and a tuple), never interpolated into the SQL text.

## Backfilling data

The collector skips the games it already has, so it does not waste
requests. With `--refetch` it requests them again and rewrites the rows:

```bash
docker compose run --rm collector python collector.py --refetch
```

This is needed when adding a new column (old games would have it as
`NULL`) and when fixing a collector bug that stored something wrong.

It only re-requests the games in the list Riot returns, whose length is
set by `MATCH_COUNT` (20 by default). To go further back, raise it for that
run only, without touching the `.env`:

```bash
docker compose run --rm -e MATCH_COUNT=70 collector python collector.py --refetch
```

This also downloads games that were never stored. In Compose the collector
only runs on `up`, and if more than `MATCH_COUNT` games are played between
two runs, the oldest ones in that stretch are not downloaded.

The Riot list returns at most a hundred games per request and the collector
does not ask for more, so older games cannot be requested again, and a
column added later stays `NULL` forever for those.

In the cluster, `--refetch` is run with a Job started by hand (see
[kubernetes.md](kubernetes.md#collector)).

## Rate limit and errors

Every request goes through `fetch()`, with a 15-second timeout each. On a
network error, a 5xx or a 429, the request is tried up to three times.
Between attempts it waits 1, 2 and 4 seconds, or whatever the `Retry-After`
header says if it is a 429.

Common Riot error codes:

- `401` / `403`: the key is not valid
- `404`: wrong Riot ID
- `429`: rate limit exceeded, the collector waits and retries

After regenerating the key, it can take a few seconds to become valid.
