# Kubernetes

English | [Español](../es/kubernetes.md)

A local kind cluster with one control-plane node and two workers. It is
created with `kind create cluster --config kind-config.yaml`, and
`kubectl get nodes` should show the three nodes as `Ready`. It is deleted
with `kind delete cluster --name project0`.

The first worker publishes ports 80 and 443 on `127.0.0.1` for Traefik
(see [Cluster ingress](#cluster-ingress)). The ports can only be set when
the cluster is created, so changing `kind-config.yaml` means deleting the
cluster and creating it again, losing whatever is inside.

The application is installed with a custom Helm chart, in
`charts/project0`, as the `project0` release in the `project0` namespace.
What lives outside the chart, such as the namespaces, the StorageClass and
the Gateway, is in `platform/`. Prometheus, Grafana and Alertmanager are
installed separately, in the `monitoring` namespace (see
[monitoring.md](monitoring.md)).

## Install from scratch

On a newly created cluster, in this order.

**1. The Gateway API types**, which do not come with Kubernetes:

```bash
kubectl apply -f https://github.com/kubernetes-sigs/gateway-api/releases/download/v1.6.3/standard-install.yaml
```

**2. Traefik**, the cluster's entry point:

```bash
helm repo add traefik https://traefik.github.io/charts
helm install traefik traefik/traefik --version 42.1.3 \
  --namespace traefik --create-namespace \
  --values platform/helm/traefik-values.yaml
```

**3. The namespaces, the StorageClass and the Gateway:**

```bash
kubectl apply -f platform/
```

**4. The Secrets**, which are not in the repo. The GHCR images are public,
so the cluster pulls them without credentials.

The PostgreSQL password and the Riot values come from the `.env`. The Riot
ID is not secret, but it goes in the Riot Secret so that it is not in the
repo:

```bash
kubectl create secret generic db-credentials -n project0 \
  --from-literal=POSTGRES_PASSWORD="$(grep "^POSTGRES_PASSWORD=" .env | cut -d= -f2-)"

kubectl create secret generic riot-credentials -n project0 \
  --from-literal=RIOT_API_KEY="$(grep "^RIOT_API_KEY=" .env | cut -d= -f2-)" \
  --from-literal=RIOT_GAME_NAME="$(grep "^RIOT_GAME_NAME=" .env | cut -d= -f2-)" \
  --from-literal=RIOT_TAG_LINE="$(grep "^RIOT_TAG_LINE=" .env | cut -d= -f2-)"
```

The Grafana password does not come from the `.env`, because only the
cluster uses it. It is generated when the Secret is created and read from
it when needed:

```bash
kubectl create secret generic grafana-admin -n monitoring \
  --from-literal=admin-user=admin \
  --from-literal=admin-password="$(openssl rand -hex 24)"
```

The Discord webhook URL is not in the `.env` either. `read -rs` asks for it
without showing it on screen or leaving it in the shell history:

```bash
read -rs DISCORD_WEBHOOK_URL
kubectl create secret generic alertmanager-discord -n monitoring \
  --from-literal=webhook-url="$DISCORD_WEBHOOK_URL"
```

**5. Prometheus, Grafana and Alertmanager:**

```bash
helm repo add prometheus-community https://prometheus-community.github.io/helm-charts
helm install kube-prometheus-stack prometheus-community/kube-prometheus-stack \
  --version 93.3.0 --namespace monitoring \
  --values platform/helm/kube-prometheus-stack-values.yaml \
  --wait --timeout 10m
```

**6. The application:**

```bash
helm install project0 charts/project0 -n project0 --wait --timeout 5m
```

When it finishes, `kubectl get pods -n project0` should show two API pods,
two frontend pods, one Redis pod and `postgres-0`, all at `1/1`.

Monitoring is installed before the application because the project0 chart
creates a ServiceMonitor and a PrometheusRule, which are Prometheus
Operator types. On a cluster without it, the application is installed with
`--set monitoring.enabled=false`.

The namespace and the Secrets live outside the chart. Helm stores the
release inside the namespace, so if the chart owned the namespace, `helm
uninstall` would delete it along with everything in it. And if the Secrets
were chart templates, their values would end up in the history of every
revision.

On a new cluster PostgreSQL starts empty. On install, the migrations create
the schema, and the data is brought in by restoring a backup (see
[database.md](database.md#backups)).

To call the API routes that are not published, such as `/ready`, open a
port-forward in a terminal. It uses 8001 because Compose takes 8000:

```bash
kubectl port-forward -n project0 service/api 8001:80
```

And from another terminal:

```bash
curl localhost:8001/ready
```

## The chart

`charts/project0` has four parts:

- `Chart.yaml`: the name and two versions. `version` is the chart's and is
  bumped by hand when the templates or the configurable options change.
  `appVersion` is the tag of the images it deploys.
- `values.yaml`: what can change from one cluster to another or over time,
  such as the tag, the replicas, the resources, the collector schedule, the
  API configuration, the PostgreSQL disk, and the Gateway the route is
  attached to and the hostname it is reached through.
- `templates/`: one template per application object, in one folder per
  component. `monitoring/` has the Prometheus and Grafana ones, and the
  files outside the folders are the ones they all share, such as the common
  ConfigMap and the route.
- `templates/_helpers.tpl`: the common labels and the tag rule, which
  several templates use.

In the cluster, the non-secret configuration does not come from the `.env`
but from the chart's ConfigMaps, which are filled in from `values.yaml`.
The API pod template has a checksum of the `data` of each ConfigMap it
reads, so if a `helm upgrade` changes one of those values, the checksum
changes and Kubernetes recreates the pods with the new value. It is
calculated only over the `data` so that bumping the chart version, which
changes the `helm.sh/chart` label on every object, does not restart the API.
The collector does not need it, because each run is a new pod.

The migrations are applied by a Helm hook, a Job that is not installed with
everything else but at the moment its annotation specifies. On the first
install it runs after everything has been created, because it needs
PostgreSQL, and on every upgrade it runs before touching the API. The Job
stays until the next upgrade, with its logs.

The PostgreSQL disk (`postgres.storage`) can only be set when the
StatefulSet is created. Kubernetes does not allow `volumeClaimTemplates` to
be changed afterwards, so changing it on an existing installation makes the
upgrade fail.

`helm lint --strict charts/project0` checks the chart the same way the CI
does. The `kubectl diff` in [Deploying a new version](#deploying-a-new-version)
shows what would change in the cluster.

## Deploying a new version

Every push to `main` publishes the three images with the short commit SHA.
To deploy them, put that tag in `appVersion`, in
`charts/project0/Chart.yaml`, and check what is going to change, without
applying anything:

```bash
helm template project0 charts/project0 -n project0 --no-hooks | kubectl diff -n project0 -f -
```

It uses `--no-hooks` because the migrations Job from the previous upgrade is
still in the cluster, and Kubernetes does not allow its `template` to be
changed. With a new image the whole `diff` would fail, and Helm recreates
the Job on every upgrade anyway. If the deployment includes migrations,
take a backup first (see [database.md](database.md#backups)), because a
rollback does not undo them.

If the diff is what you expected, deploy:

```bash
helm upgrade project0 charts/project0 -n project0 --wait --timeout 5m
helm history project0 -n project0
```

`helm history` should show the new revision as `deployed`.

Helm runs the migrations first and waits for them to finish, because the new
code may need a new column. If they fail, the upgrade stops, the previous
version keeps serving and the reason is in `kubectl logs job/migrations -n
project0`. If they succeed, Helm applies the rest, and Kubernetes replaces
the API and frontend pods one at a time. With `--wait`, Helm does not
consider the deployment successful until the new ones are ready.

The CronJob uses the new image from its next run.

If an earlier upgrade was run with `--set image.tag=...` to test a branch,
Helm stores it in the release and uses it again in the following upgrades,
overriding `appVersion`. `helm get values project0 -n project0` shows what
was stored, and `--reset-values` on the upgrade clears it.

A change to `values.yaml` or to a template is deployed the same way.

Commit the change after checking that it works, so that what is in `main`
always matches what is deployed.

Changes are always made in the chart. Applying a separate manifest with
`kubectl apply` on top of the application would make `kubectl` the owner of
those fields, and the next `helm upgrade` would fail with a conflict.

## Rolling back

If the deployment does not finish, the old pods keep serving until the new
one passes its readiness probe. To see what is failing, the new pod's
events are at the end of the `describe` output:

```bash
kubectl get pods -n project0
kubectl describe pod <new pod> -n project0
```

To go back to a previous revision:

```bash
helm history project0 -n project0
helm rollback project0 <revision> -n project0 --wait --timeout 5m
```

The rollback creates a new revision with the contents of the chosen one. It
does not run the migrations again or undo the ones already applied,
because they only go forward. It does not touch the repo either, so
afterwards the files have to be put back to match the cluster, for example
with `git restore`, or the next `upgrade` would bring back what failed.

A failed upgrade can leave some of the objects applied. If a ConfigMap was
already changed in the failed upgrade, the upgrade that fixes things does
not change the checksum and does not recreate the pods, so it is worth
checking that they have the new configuration, for example with
`kubectl exec -n project0 deploy/api -- printenv CACHE_TTL_SECONDS`.

## PostgreSQL

It runs in a StatefulSet with one replica, and not in a Deployment, because
it needs its own disk, which stays attached to it when the pod is recreated.
The pod is always called `postgres-0` and its disk is the `datos-postgres-0`
PVC, which the StatefulSet creates from `volumeClaimTemplates`. If the pod
is deleted, it comes back with the same name and the same disk, although
with a different IP.

The disk uses the `standard-retain` StorageClass, defined in
`platform/storageclass.yaml`. It is the same as kind's `standard`, but with
`reclaimPolicy: Retain`. With kind's `standard`, deleting the PVC would also
delete the data. With this one, the PV is left as `Released` and the data
stays on the node until someone deletes it by hand. Neither of them survives
`kind delete cluster`, which is what the backup is for.

The `postgres` Service is headless (`clusterIP: None`), so DNS returns the
pod's IP directly.

With a single replica, every pod restart is an outage. When `postgres-0`
was deleted with the API serving, `/ready` returned 503 for about two
seconds and then recovered on its own.

## Collector

The `collector` CronJob runs the collector every hour on the hour, Madrid
time. Each run is a Job with its own pod, which downloads the new games,
stores them and exits. One hour is enough because games do not appear any
faster, and since the collector does not request the games it already has,
running it more often would not waste requests either. What it requests from
Riot is in [collector.md](collector.md).

`get cronjob` shows the schedule and the last run. `get jobs` shows one Job
per run, as `Complete` or `Failed`. The last command shows the logs of all
the Jobs that are still kept:

```bash
kubectl get cronjob collector -n project0
kubectl get jobs -n project0
kubectl logs -n project0 -l app.kubernetes.io/name=collector --prefix --tail=-1
```

To run it right away, as the refresh button does:

```bash
kubectl create job collector-manual -n project0 --from=cronjob/collector
```

The Jobs of the last 3 successful runs and the last 3 failed ones are kept,
with their logs, and each one is deleted three days after it finishes. A
failed Job keeps the `KubeJobFailed` alert firing, and deleting it this way
stops the alert from firing forever (see
[monitoring.md](monitoring.md#alerts)).

A `Complete` Job does not guarantee that every game was stored. If one
fails, the collector skips it, finishes successfully and tries it again on
the next run, so the failure only shows up in the logs.

When something goes wrong:

- Two runs never overlap. If a run is still going at the next
  hour, the new one starts when the previous one finishes, or is skipped if
  more than 30 minutes have passed.
- If the cluster was stopped, on startup it only runs the last missed run,
  and only if no more than 30 minutes have passed since its scheduled time.
- If it ends with an error it is retried once, and if it goes over 10
  minutes it is stopped.
- If the cluster stops in the middle of a run, for example with the
  computer asleep, when it comes back the run has been going for more than
  10 minutes and ends as `Failed` with `DeadlineExceeded`. Nothing is lost,
  because the next run requests whatever is missing.

Each run looks at the last `MATCH_COUNT` games (20, in
`collector.matchCount` in `values.yaml`). If more are played while the
cluster is stopped, the oldest ones are recovered by running it by hand
with a higher `MATCH_COUNT`.

A `--refetch` does not fit in those 10 minutes, because with the rate limit
70 games take about 12. It is run with a Job started by hand, generated
from the CronJob:

```bash
kubectl create job collector-refetch -n project0 --from=cronjob/collector \
  --dry-run=client -o yaml > backups/collector-refetch.yaml
```

In the file, add `--refetch` to `command`, `MATCH_COUNT` to `env` and
`activeDeadlineSeconds: 1800`. Then apply it and follow its logs:

```bash
kubectl apply -f backups/collector-refetch.yaml
kubectl logs -f job/collector-refetch -n project0
```

When it finishes, delete it:

```bash
kubectl delete job collector-refetch -n project0
```

The `MATCH_COUNT` in `env` takes precedence over the ConfigMap's. The Job
is owned by the CronJob, so if it runs long, the next hour's run waits for
it to finish.

## API permissions

The API starts the collector when a refresh is requested from the page,
and to do that it creates a Job from the CronJob. It uses its own
ServiceAccount, `api`, with a Role that only lets it read the `collector`
CronJob and create and list Jobs. The other pods use `default`, which has
no permissions.

Anyone who can create Jobs can create one with any image, and its pod can
mount any Secret in the namespace, such as the Riot key. That is why the
`project0-collector-trigger` ValidatingAdmissionPolicy only lets through
Jobs from `api` whose owner is the `collector` CronJob and whose pod is
identical to the one in its template. ValidatingAdmissionPolicy has been
part of Kubernetes since 1.30, so nothing needs to be installed.

It is tested by impersonating the ServiceAccount, with `--dry-run=server`
so that nothing is stored. The copy of the collector is accepted, and the
same copy with a different image is rejected:

```bash
kubectl create job prueba-ok --from=cronjob/collector -n project0 \
  --as=system:serviceaccount:project0:api --dry-run=server

kubectl create job prueba-cambiada --from=cronjob/collector -n project0 --dry-run=client -o yaml \
  | sed "s#image: .*#image: busybox#" \
  | kubectl create -f - -n project0 --as=system:serviceaccount:project0:api --dry-run=server
```

With `refresh.enabled: false` in the values, neither the permissions nor
the policy are created, the API uses `default` and the page does not show
the button. What the API does with these permissions is in
[api.md](api.md#refreshing-from-the-page).

## Frontend

In the cluster the page lives inside its own image, built with
`frontend/Dockerfile`: a non-root nginx listening on 8080, with
`frontend/public/` copied in. So a change to the page needs a new image,
like the rest of the code. Two replicas serve it behind the `frontend`
Service, and from outside it is reached through Traefik (see
[Cluster ingress](#cluster-ingress)). The page itself is described in
[frontend.md](frontend.md).

The image has three nginx files. `nginx-cluster.conf` replaces the image's
example `server` and pulls in the rules from `nginx-common.conf`, the same
as in Compose but without the API proxy, which Traefik handles here.
`nginx.conf` is the image's own with a single change,
`worker_processes 2`, and it has to be compared with the upstream one when
the image version is bumped. With `auto`, nginx would start one worker per
CPU on the node, not in the container, and on a large node they would not
fit in the memory limit.

## Cluster ingress

Traffic from outside comes in through Traefik, which reads the Gateway API
`Gateway` and `HTTPRoute` objects. Its configuration is in `platform/`,
separate from the application's, and it is installed once per cluster (see
[Install from scratch](#install-from-scratch)).

In kind, Traefik listens on port 80 of `project0-worker`, which kind maps
to port 80 on the local machine. In a real cluster it would sit behind a
`LoadBalancer` Service.

To change a Traefik value, edit `traefik-values.yaml` and run the install
command with `upgrade` instead of `install`, always with `--values`.

The project0 rules are in the `project0` HTTPRoute, another template in the
chart, attached to the `public` Gateway (`gateway` in `values.yaml`):

```
/api/health, /api/ready, /api/docs…  →  Service frontend, which returns 404
/api/…                               →  Service api, without the /api
/                                    →  Service frontend
```

The API has its routes without a prefix, so the HTTPRoute strips it with a
`URLRewrite` filter. The internal routes are not published, as in Compose.
Gateway API has no action for returning a 404, so they go to the frontend,
which does not have them. When several rules match, the longest prefix
wins.

The Gateway is shared by project0 and monitoring, and it only accepts
routes from their two namespaces (`allowedRoutes` in
`platform/gateway.yaml`). Each route serves one hostname:

```
localhost               →  HTTPRoute project0
grafana.localhost       →  Grafana
prometheus.localhost    →  Prometheus
alertmanager.localhost  →  Alertmanager
```

The project0 hostname is in `hostnames`, in `values.yaml`. Without it, the
route accepted any hostname, and its `/api` rule captured the `/api/...`
requests for Grafana, Prometheus and Alertmanager, which is the path their
pages use to request data. The pages loaded, but without data. With the
hostname set, the page only responds at `http://localhost`, and through
`http://127.0.0.1` it returns 404.

To check the ingress:

```bash
helm list -n traefik
kubectl get gateway -n traefik
kubectl get httproute -A
kubectl describe httproute project0 -n project0
```

The `public` Gateway should show `PROGRAMMED` as `True`, the four
HTTPRoutes with their hostname in `HOSTNAMES`, and the project0 one with
`Accepted` and `ResolvedRefs` as `True`.

```bash
curl -s -o /dev/null -w "%{http_code}\n" http://localhost/api/patches
curl -s -o /dev/null -w "%{http_code}\n" http://localhost/api/health
curl -s -H "Host: grafana.localhost" http://localhost/api/health
```

The first one returns 200, because it is the API, and the second 404,
because `/health` is internal. The third returns Grafana's JSON. With
`-H "Host: ..."`, `curl` tests each hostname without depending on how the
system resolves it.
