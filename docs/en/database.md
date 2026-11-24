# Database

English | [Español](../es/base-de-datos.md)

PostgreSQL 16, with the schema versioned with Flyway. In Compose the data
lives in the `datos_db` volume, which survives `docker compose down`. In the
cluster, it lives on the disk of `postgres-0` (see
[kubernetes.md](kubernetes.md#postgresql)).

## The tables

Six tables and a view:

- `summoners`: maps each PUUID to a readable Riot ID, with its profile icon
  and level
- `matches`: date, duration, queue type and patch of each game
- `participants`: the ten players of each game: champion, position, KDA,
  result, gold, damage dealt and taken, CS, vision, final items, summoner
  spells, team, level, runes and their solo/duo rank
- `item_purchases`: every purchase by every player, with its minute
- `skill_levelups`: every skill level-up, with its minute
- `ranked_snapshots`: a snapshot of the solo/duo ranked standing on every
  collector run: tier, division, LP, wins, losses and the cutoff for the
  next tier. All of them are kept, and the LP chart for the last 30 days
  comes from them
- `participant_scores`: the view with the score and the badge of each player
  (see [The score and the badges](#the-score-and-the-badges))

The data in `matches` and `participants`, except the rank, comes in the same
MATCH-V5 response, so storing it does not cost any extra requests to Riot.
How the collector requests it is in [collector.md](collector.md).

CS is stored in two columns, `minions_killed` and `neutral_minions_killed`,
because that is how Riot provides it. Adding them up is left to the query:

```sql
SELECT champion, minions_killed + neutral_minions_killed AS cs
FROM participants;
```

Champions are stored by their internal key, and items and spells by their
number. The names and icons come from Data Dragon on the page, so if Riot
renames an item, the history does not keep a name that no longer exists.

To see the stored games without opening a database shell:

```bash
docker compose exec db psql -U loltest -d lolstats -P pager=off \
  -c "SELECT champion, kills, gold_earned, damage_to_champions FROM participants;"
```

## The ten players

`participants` stores the ten players of each game. For the others, all the
game data is stored and **nothing about their identity**, because the PUUID
is only filled in for the followed summoners.

The primary key is `(match_id, participant_id)`, where `participant_id`
is the player's number within
the game (1-10), which always exists. The `puuid` is optional, and its
reference to `summoners` does not get in the way, because in SQL a null
foreign key is not checked. Lookups by `puuid` have their own index,
`idx_participants_puuid`, because the primary key starts with `match_id`.

Showing the scoreboard needs a `LEFT JOIN` with `summoners`, because a
regular join would drop the nine rows without a PUUID. Those players are
shown by their champion's name. When a summoner is added to the followed
ones, their earlier rows are filled in with a `--refetch`.

`team_id` is 100 (blue) or 200 (red), as Riot provides it. It separates
allies from opponents and makes it possible to calculate kill
participation, which needs the kills of the whole team.

## The score and the badges

Every player in every game has a score from 0 to 10, and the best player on
each team gets a badge: **MVP** on the winning team and **BASTION** on the
losing one.

The score comes from four statistics. Each one is divided by the best value
among the ten players of that game, so it ends up between 0 and 1, and a
long game does not give higher scores than a short one.

- KDA, `(kills + assists) / deaths`, counting 0 deaths as 1
- kill participation
- damage to champions
- vision score, which counts for half

```
score = 10 × (kda + participation + damage + 0.5 × vision) / 3.5
```

The 3.5 is the sum of the weights, so whoever is best in all four gets a 10.
Vision counts for half because it can be inflated by placing wards at no
cost. Damage taken was left out, because taking a lot of damage does not by
itself show that someone played well.

It is calculated in the `participant_scores` view (`V8`), which stores no
rows and is computed every time it is read, so it always reflects what is
in `participants`. It is a regular view and not a materialized one, so it
does not have to be refreshed after every collector run.

Badge rules:

- There is only one per team. If two scores tie, the lowest `participant_id`
  wins, so the result does not change from one query to the next.
- No score means no badge. Games stored before the ten players or the damage
  were recorded have `NULL` in those columns, and their score is `NULL` too.
- The score is rounded to one decimal at the end, after the badge is chosen.
  Rounding first, a 7.44 and a 7.36 would tie at 7.4.

`/matches` returns the summoner's badge in each game, and
`/matches/{match_id}` the score and badge of all ten players.

## Deleting games

The foreign keys pointing to `matches` have `ON DELETE CASCADE`, so
deleting a game also deletes its participants, its purchases and its skill
level-ups:

```sql
DELETE FROM matches WHERE queue_id <> 420;
```

The `DELETE` message only counts the rows in `matches`, and each game
carries hundreds of rows in the other three tables, so it is worth counting
before deleting.

The foreign key from `participants` to `summoners` deliberately has no cascade.
Removing a summoner from the followed ones must not delete their rows in
`participants`, because those games still exist.

## The full cycle for adding a field

1. Write the migration with the new column (`V12__...sql`)
2. Add it to the collector's `INSERT`, in the column list, in the `%s`
   placeholders and in the values tuple
3. `docker compose up -d --build`, which applies the migration and rebuilds
4. `--refetch` to fill in the history (see
   [collector.md](collector.md#backfilling-data))
5. Expose it in `api.py` if the page needs it

## Migrations

The schema lives in `migrations/`, one file per change. The name follows
the Flyway convention: `V`, the number, **two** underscores and the
description. With a single underscore the file is ignored.

Each file contains only its own change, not the whole schema. The state of
the database is the result of applying all of them in order.

### How they are applied

In Compose, the `flyway` service runs at startup, applies whatever is
missing and exits. `collector` and `api` wait for it to finish successfully
(`service_completed_successfully`), so if a migration fails the application
does not start, instead of working on a half-migrated database.

In the cluster they are applied by the `migrations` Job, a Helm hook that
runs before each deployment, with a Flyway image that has the `.sql` files
inside (see [kubernetes.md](kubernetes.md#deploying-a-new-version)).

Flyway keeps track of the applied migrations in a table in the database itself,
`flyway_schema_history`, which can be queried like any other.

### Adding a change

Create the file with the next number and start the services:

```bash
docker compose up -d
docker compose logs flyway
```

Flyway can also be run on its own, without starting anything, with
`docker compose run --rm flyway` followed by a command:

- `info` shows which version the database is at.
- `migrate` applies whatever is missing.
- `validate` checks that no migration that was already applied has changed.

### An applied migration is never edited

Flyway stores the checksum of each file it has run and recalculates it on
every startup. Changing a migration that was already applied, even just a
comment, causes an error and nothing runs.

If a migration that has been applied in production for months could be
edited, a new environment would run the corrected version and production
would keep the old one, without anyone being told. To fix something, you
write the next migration.

### Adding Flyway to an existing database

If the database already has the tables, `migrate` would try to run V1 and
fail. That is what `flyway baseline -baselineVersion=1` is for: it creates
the tracking table and marks V1 as applied without running it. From there,
`migrate` continues with V2.

It was used when Flyway was introduced into the project, on the database
that already had games.

## Backups

From Compose:

```bash
mkdir -p backups
docker compose exec -T db sh -c 'pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc' > backups/project0-$(date +%F).dump
```

From the cluster, the same but inside `postgres-0`:

```bash
mkdir -p backups
kubectl exec -n project0 postgres-0 -- sh -c 'pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc' > backups/project0-$(date +%F).dump
```

`kubectl exec` runs without `-t`, just like the `-T` in Compose, because a
terminal would corrupt the binary output of `pg_dump`.

To see which tables a backup contains without restoring it:

```bash
kubectl exec -i -n project0 postgres-0 -- pg_restore --list < backups/<file>.dump | grep "TABLE DATA"
```

To restore it into an empty Compose database:

```bash
docker compose exec -T db sh -c 'pg_restore -U "$POSTGRES_USER" -d <database>' < backups/<file>.dump
```

To restore it in the cluster, replacing whatever is in `postgres-0`, and
then apply the migrations written since the backup:

```bash
kubectl exec -i -n project0 postgres-0 -- sh -c 'pg_restore -U "$POSTGRES_USER" -d "$POSTGRES_DB" --clean --if-exists --single-transaction' < backups/<file>.dump
helm upgrade project0 charts/project0 -n project0 --wait --timeout 5m
```

The `helm upgrade` does not change anything in the application, but it
runs the migrations hook.

`--clean --if-exists` drops each object in the backup before creating it,
and `--single-transaction` makes sure that, if something fails, the
database stays as it was.

The backup uses the `pg_dump` custom format, and the `backups/` folder is
not tracked by Git. It is done by hand, and automatic backups are listed in
[MEJORAS.md](../../MEJORAS.md) (in Spanish).
