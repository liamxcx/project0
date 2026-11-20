# Kubernetes

Clúster local con kind, definido en `kind-config.yaml`: un control plane y
dos workers.

```bash
kind create cluster --config kind-config.yaml   # crearlo
kubectl get nodes                               # los tres nodos en Ready
kind delete cluster --name project0             # borrarlo
```

El primer worker publica el 80 y el 443 en `127.0.0.1` para Traefik (ver
[Entrada al clúster](#entrada-al-clúster)).
Los puertos solo se fijan al crear el clúster, así que cambiar
`kind-config.yaml` obliga a borrarlo y crearlo otra vez, y se pierde lo que
haya dentro.

La aplicación se instala con un chart de Helm propio, en `charts/project0`,
como la release `project0` del namespace `project0`. Lo que va fuera del
chart, como los namespaces, la StorageClass y el Gateway, está en `platform/`.
Prometheus, Grafana y Alertmanager van aparte, en el namespace `monitoring`
(ver [monitorizacion.md](monitorizacion.md)).

## Instalar desde cero

En un clúster recién creado, en este orden:

```bash
# 1. Los tipos de Gateway API, que no vienen con Kubernetes
kubectl apply -f https://github.com/kubernetes-sigs/gateway-api/releases/download/v1.6.3/standard-install.yaml

# 2. Traefik, la entrada al clúster
helm repo add traefik https://traefik.github.io/charts
helm install traefik traefik/traefik --version 42.1.3 \
  --namespace traefik --create-namespace \
  --values platform/helm/traefik-values.yaml

# 3. Los namespaces, la StorageClass y el Gateway
kubectl apply -f platform/

# 4. Los Secrets, que no están en el repo
read -rs GHCR_TOKEN
kubectl create secret docker-registry ghcr-pull -n project0 \
  --docker-server=ghcr.io --docker-username=<usuario de GitHub> \
  --docker-password="$GHCR_TOKEN"

kubectl create secret generic db-credentials -n project0 \
  --from-literal=POSTGRES_PASSWORD="$(grep '^POSTGRES_PASSWORD=' .env | cut -d= -f2-)"

kubectl create secret generic riot-credentials -n project0 \
  --from-literal=RIOT_API_KEY="$(grep '^RIOT_API_KEY=' .env | cut -d= -f2-)" \
  --from-literal=RIOT_GAME_NAME="$(grep '^RIOT_GAME_NAME=' .env | cut -d= -f2-)" \
  --from-literal=RIOT_TAG_LINE="$(grep '^RIOT_TAG_LINE=' .env | cut -d= -f2-)"

kubectl create secret generic grafana-admin -n monitoring \
  --from-literal=admin-user=admin \
  --from-literal=admin-password="$(openssl rand -hex 24)"

read -rs DISCORD_WEBHOOK_URL
kubectl create secret generic alertmanager-discord -n monitoring \
  --from-literal=webhook-url="$DISCORD_WEBHOOK_URL"

# 5. Prometheus, Grafana y Alertmanager
helm repo add prometheus-community https://prometheus-community.github.io/helm-charts
helm install kube-prometheus-stack prometheus-community/kube-prometheus-stack \
  --version 93.3.0 --namespace monitoring \
  --values platform/helm/kube-prometheus-stack-values.yaml \
  --wait --timeout 10m

# 6. La aplicación
helm install project0 charts/project0 -n project0 --wait --timeout 5m
```

El token de GHCR es un token classic de GitHub con solo el permiso
`read:packages`. Lo demás sale del `.env`. El Riot ID no es secreto, pero va
en el Secret de Riot para que no esté en el repo. La contraseña de Grafana
no sale del `.env`, porque solo la usa el clúster. Se genera al crear el
Secret y se lee de él cuando hace falta. La URL del webhook de Discord
tampoco está en el `.env`, y se pega a mano como el token de GHCR.

La monitorización va antes que la aplicación porque el chart de project0 crea
un ServiceMonitor y una PrometheusRule, que son tipos del Prometheus Operator.
En un clúster sin él, la aplicación se instala con
`--set monitoring.enabled=false`.

El namespace y los Secrets van fuera del chart. Helm guarda la release
dentro del namespace, y `helm uninstall` lo borraría con todo lo que tiene
dentro. Y si los Secrets fueran templates del chart, sus valores
acabarían en el historial de cada revisión.

En un clúster nuevo PostgreSQL arranca vacío. Al instalar, las migraciones
crean el esquema, y los datos se traen restaurando un backup (ver
[base-de-datos.md](base-de-datos.md#backups)).

Para llamar a las rutas de la API que no se publican, como `/ready` (el 8000
lo ocupa Compose):

```bash
kubectl get pods -n project0                          # api y frontend (dos de cada), redis y postgres-0 en 1/1
kubectl port-forward -n project0 service/api 8001:80  # y en otra terminal:
curl localhost:8001/ready
```

## El chart

`charts/project0` tiene cuatro partes:

- `Chart.yaml` — el nombre y dos versiones. `version` es la del chart y se
  sube a mano cuando cambian los templates o lo que se puede configurar.
  `appVersion` es el tag de las imágenes que despliega.
- `values.yaml` — lo que puede cambiar de un clúster a otro o con el
  tiempo, como el tag, las réplicas, los recursos, el horario del
  collector, la configuración de la API, el disco de PostgreSQL, y el
  Gateway del que cuelga la ruta y el nombre por el que se entra.
- `templates/` — un template por objeto de la aplicación.
- `templates/_helpers.tpl` — los labels comunes y la regla del tag, que
  usan varios templates.

En el clúster, la configuración que no es secreta no sale del `.env`, sino
de los ConfigMaps del chart, que se rellenan con `values.yaml`. El template
de los pods de la API lleva un checksum de los `data` de cada ConfigMap que
lee, así que si un `helm upgrade` cambia uno de esos valores, cambia el
checksum y Kubernetes recrea los pods con el valor nuevo. Se calcula solo
sobre los `data` para que subir la versión del chart, que cambia el label
`helm.sh/chart` de todos los objetos, no reinicie la API. El collector no lo
necesita, porque cada ejecución es un pod nuevo.

Las migraciones las aplica un hook de Helm, un Job que no se instala con lo
demás sino en el momento que marca su anotación. En la primera instalación
corre después de crearlo todo, porque necesita PostgreSQL, y en cada
upgrade corre antes de tocar la API. El Job se queda hasta el siguiente
upgrade, con sus logs.

El disco de PostgreSQL (`postgres.storage`) solo se elige al crear el
StatefulSet. Kubernetes no deja cambiar `volumeClaimTemplates` después, así
que cambiarlo en una instalación que ya existe hace fallar el upgrade.

Para revisar el chart y ver qué cambiaría antes de desplegar:

```bash
helm lint --strict charts/project0                                                 # lo mismo que hace el CI
helm template project0 charts/project0 -n project0 --no-hooks | kubectl diff -f -  # la diferencia con el clúster
```

## Desplegar una versión nueva

Cada push a `main` sube las tres imágenes con el SHA corto del commit. Para
desplegarlas, se pone ese tag en `appVersion`, en
`charts/project0/Chart.yaml`, y:

```bash
helm template project0 charts/project0 -n project0 --no-hooks | kubectl diff -n project0 -f -
helm upgrade project0 charts/project0 -n project0 --wait --timeout 5m
helm history project0 -n project0                     # la revisión nueva, en deployed
```

El `kubectl diff` enseña qué va a cambiar, sin aplicar nada. Va con
`--no-hooks` porque el Job de migraciones de la vez anterior sigue en el
clúster, y Kubernetes no deja cambiar su `template`. Con una imagen nueva,
el `diff` fallaría entero, y Helm recrea el Job en cada upgrade de todos
modos. Si el despliegue trae migraciones, antes se hace un backup (ver
[base-de-datos.md](base-de-datos.md#backups)), porque un rollback no las
deshace.

Helm lanza primero las migraciones y espera a que acaben, porque el código
nuevo puede necesitar una columna nueva. Si fallan, el upgrade se para, la
versión anterior sigue atendiendo y el motivo está en
`kubectl logs job/migrations -n project0`. Después Helm aplica lo demás, y
Kubernetes sustituye los pods de la API y del frontend de uno en uno. Con
`--wait`, Helm no da el despliegue por bueno hasta que los nuevos están
listos.

El CronJob usa la imagen nueva desde su siguiente ejecución.

Si en un upgrade anterior se pasó `--set image.tag=...` para probar una rama,
Helm lo guarda en la release y lo vuelve a usar en los siguientes, por encima
de `appVersion`. `helm get values project0 -n project0` enseña lo que quedó
guardado, y `--reset-values` en el upgrade lo borra.

Un cambio en `values.yaml` o en un template se despliega igual.

El commit se hace después de comprobar que funciona, para que lo que hay en
`main` coincida siempre con lo desplegado.

Los cambios se hacen siempre en el chart. Aplicar un manifiesto suelto con
`kubectl apply` sobre la aplicación haría a `kubectl` dueño de esos campos,
y el siguiente `helm upgrade` fallaría por conflicto.

## Volver atrás

Si el despliegue no termina, los pods viejos siguen atendiendo hasta que el
nuevo pasa la readiness. Para ver qué falla:

```bash
kubectl get pods -n project0
kubectl describe pod <pod nuevo> -n project0          # los eventos, al final
```

Para volver a una revisión anterior:

```bash
helm history project0 -n project0
helm rollback project0 <revisión> -n project0 --wait --timeout 5m
```

El rollback crea una revisión nueva con lo que tenía la elegida. No vuelve a
lanzar las migraciones ni deshace las que ya se aplicaron, porque solo van
hacia delante. Tampoco toca el repo, así que después hay que dejar los
ficheros como el clúster, por ejemplo con `git restore`, o el siguiente
`upgrade` volvería a traer lo que falló.

Un upgrade que falla puede dejar aplicada una parte de los objetos. Si un
ConfigMap ya cambió en el upgrade fallido, el que lo arregla no cambia el
checksum y no recrea los pods, así que conviene comprobar que tienen la
configuración nueva, por ejemplo con
`kubectl exec -n project0 deploy/api -- printenv CACHE_TTL_SECONDS`.

## PostgreSQL

Corre en un StatefulSet con una réplica, y no en un Deployment, porque
necesita un disco propio que vuelva con él. El pod se llama siempre
`postgres-0` y su disco es el PVC `datos-postgres-0`, que el StatefulSet
crea a partir de `volumeClaimTemplates`. Si se borra el pod, vuelve con el
mismo nombre y el mismo disco, aunque con otra IP.

El disco usa la StorageClass `standard-retain`, definida en
`platform/storageclass.yaml`. Es igual que la `standard` de kind, pero con
`reclaimPolicy: Retain`. Con la de kind, borrar el PVC borraría también los
datos. Con esta, el PV queda en `Released` y los datos siguen en el nodo
hasta que alguien los borre a mano. Ninguna de las dos sobrevive a
`kind delete cluster`, y para eso está el backup.

El Service `postgres` es headless (`clusterIP: None`), así que el DNS
devuelve directamente la IP del pod.

Con una sola réplica, cada reinicio del pod es un corte. Al borrar
`postgres-0` con la API sirviendo, `/ready` respondió 503 durante unos dos
segundos y luego volvió solo.

## Collector

Lo lanza el CronJob `collector` cada hora en punto, en hora de Madrid. Cada
ejecución es un Job con su pod, que descarga las partidas nuevas, las guarda
y termina. Una hora basta porque las partidas no aparecen más rápido, y como
el collector no vuelve a pedir las que ya tiene, ejecutarlo más a menudo
tampoco gastaría peticiones de más. Qué pide a Riot está en
[collector.md](collector.md).

```bash
kubectl get cronjob collector -n project0     # horario y última ejecución
kubectl get jobs -n project0                  # una por hora, Complete o Failed
kubectl logs -n project0 -l app.kubernetes.io/name=collector --prefix --tail=-1
kubectl create job collector-manual -n project0 --from=cronjob/collector   # ejecutarlo ya
```

Se guardan los Jobs, con sus logs, de las 3 últimas ejecuciones buenas y de
las 3 últimas fallidas, y cada uno se borra tres días después de acabar. Un
Job fallido mantiene disparada la alerta `KubeJobFailed`, y así no se queda
para siempre (ver [monitorizacion.md](monitorizacion.md#alertas)).

Un Job `Complete` no asegura que se guardaran todas las partidas. Si una
falla, el collector la salta, termina bien y la vuelve a intentar en la
ejecución siguiente, así que el fallo solo queda en los logs.

Cuando algo va mal:

- No corren dos a la vez. Si una ejecución sigue en marcha a la hora
  siguiente, la nueva se lanza cuando acabe la anterior, o se salta si han
  pasado más de 30 minutos.
- Si el clúster estuvo parado, al arrancar lanza solo la última ejecución
  perdida, y solo si no han pasado más de 30 minutos desde su hora.
- Si termina con error se reintenta una vez, y si pasa de 10 minutos se
  corta.
- Si el clúster se para con una ejecución a medias, por ejemplo con el
  ordenador en reposo, al volver lleva más de 10 minutos y acaba `Failed`
  con `DeadlineExceeded`. No se pierde nada, porque la siguiente vuelve a
  pedir lo que falte.

Cada ejecución mira las últimas `MATCH_COUNT` partidas (20, en
`collector.matchCount` de `values.yaml`). Si se juegan más con el clúster
parado, las más antiguas se recuperan lanzándolo a mano con un
`MATCH_COUNT` más alto.

Un `--refetch` no cabe en esos 10 minutos, porque con el rate limit 70
partidas tardan unos 12. Se lanza con un Job a mano, generado a partir del
CronJob y con tres cambios en el fichero: `--refetch` en `command`,
`MATCH_COUNT` en `env` y `activeDeadlineSeconds: 1800`.

```bash
kubectl create job collector-refetch -n project0 --from=cronjob/collector \
  --dry-run=client -o yaml > backups/collector-refetch.yaml
kubectl apply -f backups/collector-refetch.yaml        # después de editarlo
kubectl logs -f job/collector-refetch -n project0
kubectl delete job collector-refetch -n project0       # cuando acabe
```

El `MATCH_COUNT` de `env` gana al del ConfigMap. El Job queda a nombre del
CronJob, así que si se alarga, la ejecución de la hora siguiente espera a que
acabe.

## Permisos de la API

La API lanza el collector cuando se pide una actualización desde la web, y
para eso crea un Job a partir del CronJob. Usa su propia ServiceAccount,
`api`, con un Role que solo le deja leer el CronJob `collector` y crear y
listar Jobs. El resto de pods usan la `default`, que no tiene permisos.

Quien puede crear Jobs puede crear uno con cualquier imagen, y su pod puede
montar cualquier Secret del namespace, como la clave de Riot. Por eso la
ValidatingAdmissionPolicy `project0-collector-trigger` solo deja pasar los
Jobs de `api` cuyo dueño es el CronJob `collector` y cuyo pod es idéntico al
de su plantilla. Las ValidatingAdmissionPolicy vienen con Kubernetes desde la
1.30, así que no hay que instalar nada.

Se comprueba haciéndose pasar por la ServiceAccount, con `--dry-run=server`
para que no se guarde nada. La copia del collector se crea, y la misma copia
con otra imagen se rechaza:

```bash
kubectl create job prueba-ok --from=cronjob/collector -n project0 \
  --as=system:serviceaccount:project0:api --dry-run=server

kubectl create job prueba-cambiada --from=cronjob/collector -n project0 --dry-run=client -o yaml \
  | sed "s#image: .*#image: busybox#" \
  | kubectl create -f - -n project0 --as=system:serviceaccount:project0:api --dry-run=server
```

Con `refresh.enabled: false` en los values no se crean los permisos ni la
política, la API usa la `default` y la página no enseña el botón. Qué hace la
API con estos permisos está en
[api.md](api.md#actualizar-desde-la-web).

## Frontend

En el clúster la página va dentro de su propia imagen, construida con
`frontend/Dockerfile`: nginx sin root, que escucha en el 8080, con
`frontend/public/` copiada. Así que un cambio en la página necesita una imagen
nueva, como el resto del código. La sirven dos réplicas detrás del Service
`frontend`, y desde fuera se llega por Traefik (ver
[Entrada al clúster](#entrada-al-clúster)). Cómo es la página está en
[frontend.md](frontend.md).

La imagen lleva tres ficheros de nginx. `nginx-cluster.conf` sustituye el
`server` de ejemplo de la imagen y trae las reglas de `nginx-common.conf`,
igual que en Compose pero sin el proxy de la API, que aquí hace Traefik.
`nginx.conf` es el de la imagen con un solo cambio, `worker_processes 2`, y
hay que compararlo con el suyo al subir de versión la imagen. Con `auto`,
nginx arrancaría un worker por cada CPU del nodo, no del contenedor, y en un
nodo grande no cabrían en el límite de memoria.

## Entrada al clúster

El tráfico de fuera entra por Traefik, que lee los `Gateway` y `HTTPRoute`
de Gateway API. Su configuración está en `platform/`, aparte de la de la
aplicación, y se instala una vez por clúster (ver
[Instalar desde cero](#instalar-desde-cero)).

En kind, Traefik escucha en el 80 de `project0-worker`, que kind une con el
80 de la máquina. En un clúster real iría detrás de un Service
`LoadBalancer`.

Para cambiar un value de Traefik, se edita `traefik-values.yaml` y se
ejecuta el comando de la instalación con `upgrade` en vez de `install`,
siempre con `--values`.

Las reglas de project0 van en la HTTPRoute `project0`, un template más del
chart, colgada del Gateway `public` (`gateway` en `values.yaml`):

```
/api/health, /api/ready, /api/docs…  →  Service frontend, que da 404
/api/…                               →  Service api, sin el /api
/                                    →  Service frontend
```

La API tiene sus rutas sin prefijo, así que la HTTPRoute lo quita con un
filtro `URLRewrite`. Las rutas internas no se publican, como en Compose.
Gateway API no tiene una acción de responder 404, así que van al frontend,
que no las tiene. Cuando varias reglas encajan, gana el prefijo más largo.

El Gateway lo comparten project0 y la monitorización, y solo acepta rutas de
sus dos namespaces (`allowedRoutes` en `platform/gateway.yaml`). Cada ruta
atiende un nombre:

```
localhost               →  HTTPRoute project0
grafana.localhost       →  Grafana
prometheus.localhost    →  Prometheus
alertmanager.localhost  →  Alertmanager
```

El nombre de project0 está en `hostnames`, en `values.yaml`. Sin él, la ruta
acepta cualquier nombre, y su regla de `/api` se quedaba con las peticiones
a `/api/...` de Grafana, Prometheus y Alertmanager, que es donde sus páginas
piden los datos. Las páginas cargaban, pero sin datos. Con el nombre, la
página solo responde en `http://localhost`, y por `http://127.0.0.1` da 404.

```bash
helm list -n traefik                              # la release y su revisión
kubectl get gateway -n traefik                    # public, con PROGRAMMED True
kubectl get httproute -A                          # las cuatro, con su nombre en HOSTNAMES
kubectl describe httproute project0 -n project0   # Accepted y ResolvedRefs en True
curl -s -o /dev/null -w '%{http_code}\n' http://localhost/api/patches   # 200, la API
curl -s -o /dev/null -w '%{http_code}\n' http://localhost/api/health    # 404, interna
curl -s -H 'Host: grafana.localhost' http://localhost/api/health        # el JSON de Grafana
```

Con `-H 'Host: ...'`, `curl` prueba cada nombre sin depender de cómo lo
resuelva el sistema.
