# Mejoras

Lo que falta por hacer en project0, ordenado por tema. Cuando una mejora se
hace, se borra de aquí y pasa al README.

## Con fecha

- El token de GHCR con el que el clúster baja las imágenes caduca a mediados
  de enero de 2027. Si la imagen sigue siendo privada, antes hay que crear uno
  nuevo y volver a crear el Secret `ghcr-pull`.
- En enero de 2027, con la temporada nueva, el resumen de la temporada puede
  salir de las partidas guardadas en vez de los totales de Riot de `/rank`.
  Hasta entonces, el héroe y el resto del perfil solo cuentan las partidas que
  tiene project0, así que no tienen por qué cuadrar con la clasificatoria.

## Funcionalidad

- Seguir a varios invocadores, no solo a uno. La API tendrá que recibir el
  invocador en `/rank`, `/rank/history`, `/matches`, `/summary` y
  `/champions`, porque hoy mezclaría los datos de todos.
- Configurar el `collector` con el PUUID en vez del Riot ID. Si el jugador
  cambia de nombre hoy hay que tocar la configuración, y si otro coge el
  nombre antiguo el `collector` seguiría a esa otra persona.
- Guardar la región de cada invocador en `summoners`. Hoy el `collector` solo
  habla con los servidores de EUW (`config.py`) y la página escribe "EUW"
  fijo, así que no se puede seguir a nadie de otro servidor.
- Que el `collector` pida a Riot las partidas desde la última guardada
  (`startTime` en MATCH-V5) en vez de las últimas `MATCH_COUNT`. Hay que
  cuidar las partidas guardadas a medias, la base vacía y `--refetch`.
- Bajar las partidas de toda la temporada y no solo las de los últimos meses,
  para que el resumen de la temporada salga de las partidas guardadas.
- El "+LP" de cada partida. Riot no lo da, así que haría falta una foto de la
  clasificatoria antes y después de cada partida, con el `collector` lanzado
  cada pocos minutos.

## Despliegue

- Despliegue continuo con GitOps. Hoy el CI construye y sube la imagen, pero
  el `helm upgrade` se lanza a mano. Con Argo CD dentro del clúster, el CI
  solo cambiaría el tag de la imagen en el repo y Argo CD lo aplicaría.
  Un runner de GitHub no llega a kind, pero Argo CD sí, porque lee el repo
  desde dentro.
- Los Secrets en Git, cifrados con Sealed Secrets o SOPS, o como referencias
  a un gestor externo con External Secrets. Hoy se crean a mano, y eso choca
  con tener todo en Git para GitOps.
- `paths-ignore` en el workflow, para no construir una imagen igual cuando un
  commit solo toca el README. Con GitOps, el commit del CI que cambia el
  tag tampoco debe lanzar otro build.
- Borrar las imágenes viejas de GHCR. Cada push a `main` sube tres imágenes
  nuevas y no se borra ninguna. Hay que conservar más versiones que las que
  guarda el historial de Helm, para no romper un rollback.
- Instalar el plugin `helm diff` comprobando su firma, para ver qué cambia
  antes de cada `helm upgrade`. Hoy se hace con
  `helm template … | kubectl diff -f -`.
- Desplegarlo en público, en un servidor en la nube con su dominio. Hoy solo
  funciona en local, así que nadie puede abrirlo desde fuera de casa. Haría
  falta HTTPS con un certificado de verdad, que el CI despliegue solo y
  revisar qué queda expuesto, como `/docs`.

## Observabilidad

- Métricas con Prometheus y Grafana, y los logs recogidos con Loki. Hoy solo
  se ven con `kubectl logs`, y se pierden cuando el pod desaparece.
- Logs estructurados en JSON, para poder filtrarlos en Loki por campo.

## Infraestructura y seguridad

- Backup automático de la base de datos, con un CronJob diario y unos siete
  días de backups. Hoy se hace a mano.
- Un CronJob que borre las partidas de hace muchos parches, que ya no sirven
  para analizar nada.
- HTTPS, con un listener HTTPS en el Gateway. En local, el certificado con
  mkcert; en una empresa sería cert-manager con Let's Encrypt.
- Un usuario de PostgreSQL de solo lectura para la API. Hoy usa el mismo
  usuario que crea la base, con todos los permisos.
- Medir cuánto gasta Traefik y ponerle `resources` en sus values, como al
  resto de pods.
- Probar un HorizontalPodAutoscaler en la API, con metrics-server.
- Comprimir en la entrada y no en la API, como se suele hacer en una empresa.
  En el clúster sería un Middleware `compress` de Traefik enganchado a la
  HTTPRoute, y eso pide activar el proveedor `kubernetesCRD`, que hoy está
  apagado porque Traefik solo lee Gateway API. Hoy lo hace el `GZipMiddleware`
  de la API, que vale igual en Compose y en el clúster.

## Deuda técnica

- Un pool de conexiones en la API. Hoy cada petición abre su propia
  conexión a PostgreSQL y la cierra al terminar, con su conexión TCP y su
  autenticación cada vez. Con un usuario no se nota, pero con más tráfico sí.
  `psycopg` trae uno. Aplazado hasta tener tests que comprueben que las
  respuestas no cambian.
- Invalidar la caché desde el `collector` cuando guarde partidas nuevas, en
  vez de esperar a que caduque el TTL.
- Guardar en Redis la ETag del detalle de partida junto a su JSON. Hoy se
  calcula en cada petición, y un 304 obliga a sacar la respuesta entera de
  Redis o PostgreSQL solo para compararla. Con mucho tráfico se notaría.
- Que cada cambio de formato de la API sea compatible con la página anterior,
  añadiendo campos sin quitar los viejos hasta el despliegue siguiente. Durante
  un rolling update conviven páginas y APIs de las dos versiones, y una página
  nueva puede recibir el formato viejo y fallar hasta que se recarga.
- Quitar el `DeprecationWarning` que sale en cada `pytest`. Viene del
  `TestClient` de Starlette, que usa un nombre antiguo de `anyio`, así que se
  arregla actualizando Starlette cuando publique una versión que lo corrija.
- Decidir si `/docs` y `/redoc` se desactivan al desplegar fuera de local.
  Se hace con `docs_url=None` al crear la aplicación.
- Los contenedores del Dockerfile corren como root. La imagen base de Python
  no trae usuario propio y nunca se añadió uno, así que `collector` y `api`
  arrancan con todos los permisos dentro del contenedor.
  Se arregla creando un usuario sin privilegios y poniendo `USER` después del
  `pip install`, que sí necesita root. La del frontend no tiene el problema,
  porque parte de `nginx-unprivileged`, que corre sin root.
- El `collector` no atiende SIGTERM. Es el PID 1 de su contenedor y Python no
  prepara nada para esa señal, así que la ignora. Al pararlo, con
  `kubectl delete`, por el tope de 10 minutos o al vaciar un nodo, espera
  los 30 s de gracia y muere con SIGKILL, con código 137, que se confunde
  con un `OOMKilled`. No se pierden datos, porque la partida a medias se
  deshace. Se arregla saliendo del programa al recibir `signal.SIGTERM`.
