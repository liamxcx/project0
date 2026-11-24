# Monitorización

[English](../en/monitoring.md) | Español

Prometheus recoge las métricas del clúster y de la API, Grafana las dibuja y
Alertmanager recibe las alertas. Se instalan juntos con el chart
`kube-prometheus-stack` de prometheus-community, como la release
`kube-prometheus-stack` del namespace `monitoring`. La configuración está en
`platform/helm/kube-prometheus-stack-values.yaml`, y la instalación, en
[kubernetes.md](kubernetes.md#instalar-desde-cero).

Va en su propio namespace porque no es parte de la aplicación. Vigila todo el
clúster, y así se puede reinstalar la aplicación sin perder la monitorización,
o al revés.

```
Prometheus ──lee cada 30 s──┬──▶ /metrics de cada pod de la API
                            ├──▶ kube-state-metrics         estado de los objetos
                            └──▶ kubelet y node-exporter    CPU, memoria y disco

Grafana ──consulta──▶ Prometheus ──alertas──▶ Alertmanager
```

## Qué instala

| Pieza | Qué hace | Cómo corre |
|---|---|---|
| Prometheus Operator | Convierte los objetos `Prometheus`, `Alertmanager`, `ServiceMonitor` y `PrometheusRule` en pods y configuración | Deployment |
| Prometheus | Lee las métricas, las guarda en su disco y evalúa las reglas de alerta | StatefulSet, creado por el operator |
| Alertmanager | Recibe las alertas disparadas, junta las repetidas y decide a quién avisar | StatefulSet, creado por el operator |
| Grafana | Los dashboards | Deployment |
| kube-state-metrics | Publica como métricas el estado de los objetos de Kubernetes, como las réplicas, los reinicios o cómo acabó cada Job | Deployment |
| node-exporter | Publica la CPU, la memoria, el disco y la red de su nodo | DaemonSet, uno por nodo |

El chart trae además los tipos nuevos (CRDs), los ServiceMonitor de cada
pieza de Kubernetes, y dashboards y reglas de alerta ya hechos para
Kubernetes, que mantiene la comunidad (kubernetes-mixin y otros parecidos).

Grafana lleva dos sidecars, contenedores auxiliares en el mismo pod. Buscan
en todo el clúster ConfigMaps con dashboards y fuentes de datos y se los
cargan a Grafana, que por sí solo no sabe leer nada de Kubernetes.

## Configuración

En kind, etcd, el scheduler, el controller-manager y kube-proxy solo escuchan
en `127.0.0.1` dentro del nodo, y Prometheus no llega a ellos. Por eso están
apagados en los values. Así no se crean sus objetivos ni sus alertas, que
saltarían siempre como caídos, ni sus dashboards, que saldrían vacíos.

También está apagada la alerta `NodeClockNotSynchronising`
(`defaultRules.disabled`). Los nodos de kind usan el reloj de la máquina
virtual de Docker, que no sincroniza por NTP, así que salta siempre aunque
la hora sea correcta. `NodeClockSkewDetected` sigue activa y avisa si el
reloj se desvía de verdad.

La contraseña de Grafana está en el Secret `grafana-admin`, creado a mano
como el resto (`grafana.admin.existingSecret`). Si la generara el chart,
cambiaría en cada `helm template` y el `kubectl diff` lo daría siempre por
modificado.

Prometheus guarda las métricas en un PVC de 5 GiB de la StorageClass
`standard`, así que el historial sobrevive a los reinicios. Usa `standard` y
no `standard-retain` porque perder las métricas no es grave. Borra lo más
viejo a los 10 días o al pasar de 4 GB, lo que llegue antes. El límite va un
20% por debajo del disco porque Prometheus escribe los bloques nuevos antes
de borrar los viejos, y necesita ese margen.

Prometheus lee los ServiceMonitor y las PrometheusRule de todos los
namespaces, no solo los que llevan la etiqueta `release` del chart
(`serviceMonitorSelectorNilUsesHelmValues` y `ruleSelectorNilUsesHelmValues`
en `false`). Así el chart de project0 no tiene que saber cómo se llama esta
release.

## Entrar

Los tres entran por Traefik, cada uno con su nombre:

| Pieza | Dirección |
|---|---|
| Grafana | `http://grafana.localhost` |
| Prometheus | `http://prometheus.localhost` |
| Alertmanager | `http://alertmanager.localhost` |

Un nombre `.localhost` apunta siempre a la propia máquina, y Chrome, Firefox
y `curl` lo resuelven sin tocar nada. Cada pieza tiene su HTTPRoute, que crea
su chart a partir de `route.main` en los values, colgada del Gateway
`public`. El Gateway acepta rutas del namespace `monitoring` además del de
project0 (ver [kubernetes.md](kubernetes.md#entrada-al-clúster)).

Prometheus y Alertmanager no tienen login. Aquí no es un problema, porque
kind solo publica el 80 en `127.0.0.1` y no se llega desde otra máquina,
pero no se pueden publicar así en un clúster al que se llegue desde fuera.

Con el nombre de la ruta, el chart pone también la dirección externa de
cada uno (`externalUrl` en Prometheus y Alertmanager, `domain` en Grafana),
así que los enlaces que generan, como el Source de una alerta en
Alertmanager, llevan a esas direcciones.

En Prometheus, Status → Target health enseña todo lo que lee y si responde,
y Query sirve para probar consultas de PromQL.

Grafana entra con el usuario `admin`. La contraseña se copia al portapapeles
sin que salga por pantalla:

```bash
kubectl get secret grafana-admin -n monitoring -o jsonpath="{.data.admin-password}" | base64 -d | pbcopy
```

`pbcopy` es de macOS. En Linux, `xclip -selection clipboard` hace lo mismo.

Si Traefik no funciona, se puede entrar igual con un port-forward, que se
queda corriendo en la terminal. Por ejemplo, Grafana en
`http://localhost:3000`:

```bash
kubectl port-forward -n monitoring service/kube-prometheus-stack-grafana 3000:80
```

## Métricas de la API

La API publica `/metrics` con `prometheus_client`, la librería oficial de
Prometheus para Python. Además de las del propio proceso (memoria, CPU,
recolector de basura), un middleware cuenta cada petición y mide cuánto
tarda:

| Métrica | Tipo | Etiquetas |
|---|---|---|
| `http_requests_total` | Contador | `method`, `route`, `status` |
| `http_request_duration_seconds` | Histograma | `method`, `route` |

`route` es la plantilla de la ruta y no la URL, así que `/matches/EUW1_1` y
`/matches/EUW1_2` suman en `/matches/{match_id}`. Cada valor distinto de una
etiqueta crea una serie nueva en Prometheus, y con la URL habría una por
partida. Por lo mismo, las URL que no existen suman todas en `unmatched`, y
nadie puede crear series nuevas pidiendo URL inventadas.

Una serie aparece la primera vez que se usa, ya con valor 1, y `increase()` no
cuenta ese primer 1, porque no tiene un valor anterior con el que comparar.
Con mucho tráfico no se nota, pero el botón de actualizar se pulsa pocas
veces, y además cada despliegue empieza con pods nuevos. Por eso la API crea
al arrancar, con 0, las series de los resultados de `POST /refresh`.

El histograma reparte cada tiempo en tramos, de 5 ms a 10 s, y con ellos
Prometheus estima los percentiles. El p95 de una ruta es el tiempo que no
supera el 95% de sus peticiones. Es una estimación dentro del tramo, y con
poco tráfico salta mucho, porque lo deciden muy pocas peticiones.

`/metrics` es una ruta interna, como `/health` y `/ready`. Ni Traefik ni el
nginx de Compose la publican, y no sale en `/docs`.

Las lee Prometheus gracias al ServiceMonitor `api` del chart. Usa el Service
`api` solo para encontrar los pods, y luego pregunta a cada uno por su IP,
porque cada réplica tiene sus propios contadores. En Target health sale como
`serviceMonitor/project0/api/0`, con un objetivo por pod.

El ServiceMonitor y las alertas son tipos del Prometheus Operator, así que
en un clúster sin él harían fallar la instalación del chart. Se apagan con
`monitoring.enabled: false` en los values.

## Dashboard

El dashboard `project0 / API` está en `charts/project0/dashboards/api.json`.
El chart lo mete en el ConfigMap `grafana-dashboard-api`, con la etiqueta
`grafana_dashboard: "1"`, y el sidecar de Grafana lo carga solo. Se despliega
con la aplicación, sin tocar Grafana.

Sigue el método RED, el habitual para un servicio que recibe peticiones:

- **Peticiones por segundo** (rate), por ruta.
- **Errores**, el porcentaje de respuestas 5xx. Los 404 no cuentan, porque
  una partida que no existe es una respuesta correcta.
- **Tiempo de respuesta** (duration), el p95 por ruta.

Además lleva el tiempo desde la última ejecución correcta del collector, que
se pone en rojo a partir de dos horas, y las veces que se ha pulsado el botón
de actualizar en el rango elegido, según lo que respondió la API. Ese panel
sale de `http_requests_total` y no de una métrica propia, porque el código de
respuesta ya dice si se lanzó, si tocaba esperar o si falló.

Los tres paneles de la API dejan fuera `/health`, `/ready` y `/metrics`,
porque son las sondas de Kubernetes y Prometheus, y taparían el tráfico de
verdad. Usan `$__rate_interval`, que ajusta la ventana de `rate()` al zoom.

Grafana no deja guardar encima un dashboard cargado así, y no tiene disco,
así que lo que se cambie en la web se pierde. Para cambiarlo, se prueba en la
web, se exporta el JSON (Export → Export as JSON), se copia en `api.json` y
se despliega con `helm upgrade`.

## Alertas

Las propias de project0 están en
`charts/project0/templates/monitoring/prometheusrule.yaml`:

| Alerta | Cuándo salta | Gravedad |
|---|---|---|
| `CollectorNotSucceeding` | Más de dos horas sin una ejecución correcta del collector, durante 5 minutos | `warning` |
| `ApiHighErrorRate` | Más del 5% de respuestas 5xx en los últimos 5 minutos, durante 10 minutos | `critical` |

Prometheus evalúa cada regla cada 30 segundos. Si se cumple, la alerta pasa
a `pending`, y si sigue cumpliéndose todo el tiempo del `for`, a `firing`, y
se la manda a Alertmanager. El `for` sirve para que un pico suelto no la
dispare.

Las del chart cubren lo general de Kubernetes, y estas no las repiten.
`KubeJobFailed` salta con cualquier Job fallido, aunque el siguiente vaya
bien. `CollectorNotSucceeding` salta solo si el collector sigue fallando, y
también si el CronJob no llega a lanzarse, que `KubeJobFailed` no ve. Un
fallo suelto del collector no necesita nada, porque la ejecución siguiente
pide lo que falte. `TargetDown` salta si Prometheus no puede leer la API.

`KubeJobFailed` sigue disparada mientras exista el Job fallido, aunque el
fallo fuera hace días. Por eso los Jobs del collector se borran tres días
después de acabar (`ttlSecondsAfterFinished` en el CronJob).

Una regla se prueba copiando su `expr` en Query de Prometheus, con el
namespace ya puesto. Si sale algún resultado, la alerta se está cumpliendo.
Para verla saltar de verdad, se baja el umbral y el `for`, se despliega y,
después de verla en `firing` y en Alertmanager, se vuelve a dejar como
estaba.

En Prometheus, Alerts enseña todas las reglas y su estado. El buscador
filtra por el nombre de la regla y sus etiquetas, no por el del grupo.
Alertmanager enseña solo las disparadas, y desde ahí se crean los
silencios. La alerta `Watchdog` está siempre disparada a propósito, para
comprobar que la cadena funciona.

Alertmanager manda las alertas a un canal de Discord, con un mensaje cuando
pasan a `firing` y otro cuando se resuelven. Cada alerta va en su propio
grupo (`group_by: ["..."]`), así que cada mensaje habla de una sola y nunca
se mezclan disparadas y resueltas. Si sigue disparada, se repite cada 12
horas. Con la agrupación por namespace que trae el chart, un mensaje
enseñaría el grupo entero, con las disparadas y las resueltas juntas.
`Watchdog` e `InfoInhibitor` van al destino `null`, que no manda nada.

La URL del webhook es secreta, así que va en el Secret `alertmanager-discord`,
creado a mano. Alertmanager la monta como fichero y la lee de ahí
(`webhook_url_file`), y así no está en el repo:

```bash
read -rs DISCORD_WEBHOOK_URL
kubectl create secret generic alertmanager-discord -n monitoring \
  --from-literal=webhook-url="$DISCORD_WEBHOOK_URL"
```

La URL se copia del webhook del canal, en la configuración del servidor de
Discord. `read -rs` la pide sin enseñarla en pantalla, así que no queda ni
en la terminal ni en el historial.

La configuración que ha cargado Alertmanager se ve en su web, en Status. Si
una configuración nueva tiene un error, sigue con la anterior. Para probar el
envío sin esperar a una alerta, se le puede mandar una a mano por su API:

```bash
curl -s -X POST -H "Host: alertmanager.localhost" -H "Content-Type: application/json" \
  http://localhost/api/v2/alerts \
  -d '[{"labels":{"alertname":"PruebaDiscord","severity":"warning","namespace":"project0"},"annotations":{"summary":"Prueba de aviso a Discord"}}]'
```

Llega unos 30 segundos después, y unos 5 minutos más tarde llega como
resuelta.

El clúster corre en kind, así que con el ordenador en reposo no se evalúa
nada y no llega ningún aviso. Al volver, las alertas que se cumplan saltan
de golpe, después de su `for`.

## Actualizar el stack

Para cambiar un value, se edita `kube-prometheus-stack-values.yaml` y se
compara con el clúster antes de aplicarlo:

```bash
helm template kube-prometheus-stack prometheus-community/kube-prometheus-stack \
  --version 93.3.0 --namespace monitoring --skip-tests \
  --values platform/helm/kube-prometheus-stack-values.yaml \
  | kubectl diff -f -

helm upgrade kube-prometheus-stack prometheus-community/kube-prometheus-stack \
  --version 93.3.0 --namespace monitoring \
  --values platform/helm/kube-prometheus-stack-values.yaml \
  --wait --timeout 10m
```

El diff va con `--skip-tests` porque el chart trae un pod de test de
Grafana con una cuenta de servicio que solo existe durante `helm test`, y
sin la opción el diff falla entero. Aun así salen como nuevos los Jobs
`admission-create` y `admission-patch` y sus permisos. Son hooks que Helm
crea y borra en cada upgrade para el certificado del webhook del operator.

`kubectl diff` no enseña los campos que se quitan en los objetos que crea
Helm. Para saber qué quitar necesita la anotación
`kubectl.kubernetes.io/last-applied-configuration`, que solo pone
`kubectl apply`, y sin ella mezcla lo nuevo sobre lo que hay en el clúster.
Cuando un cambio consiste en quitar algo, hay que comprobarlo después del
upgrade, por ejemplo con
`kubectl get prometheus -n monitoring kube-prometheus-stack-prometheus -o yaml`.
