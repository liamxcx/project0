# Datos que la maqueta necesita y la API no tiene

Una línea por dato. Cuando uno se implementa, se borra de aquí y se
documenta en `DATOS.md`.

Formato:

- **`nombre_del_dato`** — para qué se usa en la maqueta. De dónde saldría:
  de Riot (MATCH-V5), calculado en SQL, o derivado en el frontend.

Aviso: añadir un dato de Riot suele significar una columna nueva en
`participants` o en `matches`, y hoy cambiar `schema.sql` obliga a
`docker compose down -v`, que borra el historial. Si la lista crece, toca
resolver antes lo de las migraciones.

---

## Pendientes

_(vacío por ahora)_
