# Monitoring

English | [Español](../es/monitorizacion.md)

Prometheus collects the metrics from the cluster and the API, Grafana graphs
them and Alertmanager receives the alerts. They are installed together with
the `kube-prometheus-stack` chart from prometheus-community, as the
`kube-prometheus-stack` release in the `monitoring` namespace. The
configuration is in `platform/helm/kube-prometheus-stack-values.yaml`, and
the installation in [kubernetes.md](kubernetes.md#install-from-scratch).

It has its own namespace because it is not part of the application. It
watches the whole cluster, and this way the application can be reinstalled
without losing the monitoring, or the other way round.

```
Prometheus ──scrapes every 30 s──┬──▶ /metrics of each API pod
                                 ├──▶ kube-state-metrics         state of the objects
                                 └──▶ kubelet and node-exporter  CPU, memory and disk

Grafana ──queries──▶ Prometheus ──alerts──▶ Alertmanager
```

## What it installs

| Component | What it does | How it runs |
|---|---|---|
| Prometheus Operator | Turns the `Prometheus`, `Alertmanager`, `ServiceMonitor` and `PrometheusRule` objects into pods and configuration | Deployment |
| Prometheus | Scrapes the metrics, stores them on its disk and evaluates the alerting rules | StatefulSet, created by the operator |
| Alertmanager | Receives the firing alerts, groups the repeated ones and decides who to notify | StatefulSet, created by the operator |
| Grafana | The dashboards | Deployment |
| kube-state-metrics | Publishes the state of Kubernetes objects as metrics, such as replicas, restarts or how each Job ended | Deployment |
| node-exporter | Publishes the CPU, memory, disk and network of its node | DaemonSet, one per node |

The chart also installs the custom resource types (CRDs), the
ServiceMonitors for each Kubernetes component, and ready-made dashboards and
alerting rules for Kubernetes, maintained by the community (kubernetes-mixin
and similar projects).

Grafana has two sidecars, helper containers in the same pod. They look
across the whole cluster for ConfigMaps with dashboards and data sources
and load them into Grafana, which cannot read anything from Kubernetes on
its own.

## Configuration

In kind, etcd, the scheduler, the controller-manager and kube-proxy only
listen on `127.0.0.1` inside the node, and Prometheus cannot reach them.
That is why they are turned off in the values. This way their targets and
alerts are not created, since they would always fire as down, and neither
are their dashboards, which would be empty.

The `NodeClockNotSynchronising` alert is also turned off
(`defaultRules.disabled`). The kind nodes use the clock of Docker's virtual
machine, which does not sync over NTP, so it always fires even when the
time is correct. `NodeClockSkewDetected` is still active and warns if the
clock really drifts.

The Grafana password is in the `grafana-admin` Secret, created by hand like
the others (`grafana.admin.existingSecret`). If the chart generated it, it
would change on every `helm template` and `kubectl diff` would always show
it as modified.

Prometheus stores the metrics on a 5 GiB PVC with the `standard`
StorageClass, so the history survives restarts. It uses `standard` and not
`standard-retain` because losing the metrics is not serious. It deletes the
oldest data after 10 days or once it goes over 4 GiB, whichever comes first.
The limit is 20% below the disk size because Prometheus writes the new
blocks before deleting the old ones, and it needs that margin.

Prometheus reads the ServiceMonitors and PrometheusRules from every
namespace, not only the ones with the chart's `release` label
(`serviceMonitorSelectorNilUsesHelmValues` and
`ruleSelectorNilUsesHelmValues` set to `false`). This way the project0
chart does not need to know the name of this release.

## Access

All three are reached through Traefik, each with its own hostname:

| Component | Address |
|---|---|
| Grafana | `http://grafana.localhost` |
| Prometheus | `http://prometheus.localhost` |
| Alertmanager | `http://alertmanager.localhost` |

A `.localhost` name always points to the local machine, and Chrome,
Firefox and `curl` resolve it without any setup. Each component has its own
HTTPRoute, which its chart creates from `route.main` in the values,
attached to the `public` Gateway. The Gateway accepts routes from the
`monitoring` namespace as well as from project0's (see
[kubernetes.md](kubernetes.md#cluster-ingress)).

Prometheus and Alertmanager have no login. That is not a problem here,
because kind only publishes port 80 on `127.0.0.1` and they cannot be
reached from another machine, but they should not be published like this on a
cluster that is reachable from outside.

From the route's hostname, the chart also sets the external address of
each one (`externalUrl` in Prometheus and Alertmanager, `domain` in
Grafana), so the links they generate, such as an alert's Source in
Alertmanager, point to those addresses.

In Prometheus, Status → Target health shows everything it scrapes and
whether it responds, and Query is for trying out PromQL queries.

Log in to Grafana as the `admin` user. The password is copied to the
clipboard without being shown on screen:

```bash
kubectl get secret grafana-admin -n monitoring -o jsonpath="{.data.admin-password}" | base64 -d | pbcopy
```

`pbcopy` is from macOS. On Linux, `xclip -selection clipboard` does the
same.

If Traefik is not working, they can still be reached with a port-forward,
which keeps running in the terminal. For example, Grafana at
`http://localhost:3000`:

```bash
kubectl port-forward -n monitoring service/kube-prometheus-stack-grafana 3000:80
```

## API metrics

The API publishes `/metrics` with `prometheus_client`, the official
Prometheus library for Python. Besides the metrics of the process itself
(memory, CPU, garbage collector), a middleware counts every request and
measures how long it takes:

| Metric | Type | Labels |
|---|---|---|
| `http_requests_total` | Counter | `method`, `route`, `status` |
| `http_request_duration_seconds` | Histogram | `method`, `route` |

`route` is the route template and not the URL, so `/matches/EUW1_1` and
`/matches/EUW1_2` are both counted under `/matches/{match_id}`. Each
distinct value of a label creates a new series in Prometheus, and with the
URL there would be one per game. For the same reason, all URLs that do not
exist are counted under `unmatched`, and nobody can create new series by
requesting made-up URLs.

A series appears the first time it is used, already with a value of 1, and
`increase()` does not count that first 1, because it has no previous value
to compare against. With a lot of traffic this goes unnoticed, but the
refresh button is pressed rarely, and every deployment also starts with new
pods. That is why the API creates the series for the `POST /refresh`
results at startup, with 0.

The histogram sorts each duration into buckets, from 5 ms to 10 s, and
Prometheus uses them to estimate percentiles. The p95 of a route is the time
that 95% of its requests do not exceed. It is an estimate within the bucket,
and with little traffic it jumps around a lot, because it depends on very
few requests.

`/metrics` is an internal route, like `/health` and `/ready`. Neither
Traefik nor the Compose nginx publishes it, and it does not appear in
`/docs`.

Prometheus scrapes them thanks to the chart's `api` ServiceMonitor. It uses
the `api` Service only to find the pods, and then asks each one by its IP,
because each replica has its own counters. In Target health it shows up as
`serviceMonitor/project0/api/0`, with one target per pod.

The ServiceMonitor and the alerts are Prometheus Operator types, so on a
cluster without it they would make the chart installation fail. They are
turned off with `monitoring.enabled: false` in the values.

## Dashboard

The `project0 / API` dashboard is in `charts/project0/dashboards/api.json`.
The chart puts it in the `grafana-dashboard-api` ConfigMap, with the
`grafana_dashboard: "1"` label, and the Grafana sidecar loads it
automatically. It is deployed with the application, without touching
Grafana.

It follows the RED method, the usual one for a service that receives
requests:

- **Requests per second** (rate), per route.
- **Errors**, the percentage of 5xx responses. 404s do not count, because a
  game that does not exist is a correct response.
- **Response time** (duration), the p95 per route.

It also shows the time since the collector's last successful run, which
turns red after two hours, and how many times the refresh button has been
pressed in the selected range, broken down by the API's response code. That
panel comes from `http_requests_total` and not from a custom metric,
because the response code already says whether a run was started, whether
it had to wait or whether it failed.

The three API panels leave out `/health`, `/ready` and `/metrics`, because
they are called by the Kubernetes probes and the Prometheus scrapes, and
would drown out the real traffic. They use `$__rate_interval`, which adjusts
the `rate()` window to the zoom level.

Grafana does not allow a dashboard loaded this way to be saved over, and it
has no disk, so whatever is changed in the web interface is lost. To change
it, try it out in the web interface, export the JSON (Export → Export as
JSON), copy it into `api.json` and deploy it with `helm upgrade`.

## Alerts

The project0 alerts are in
`charts/project0/templates/monitoring/prometheusrule.yaml`:

| Alert | When it fires | Severity |
|---|---|---|
| `CollectorNotSucceeding` | More than two hours without a successful collector run, for 5 minutes | `warning` |
| `ApiHighErrorRate` | More than 5% of 5xx responses in the last 5 minutes, for 10 minutes | `critical` |

Prometheus evaluates each rule every 30 seconds. If its condition is met,
the alert moves to `pending`, and if it keeps being met for the whole `for`
period, to `firing`, and it is sent to Alertmanager. The `for` is there so
that a single spike does not trigger it.

The chart's alerts cover Kubernetes in general, and these do not repeat
them. `KubeJobFailed` fires on any failed Job, even if the next one
succeeds. `CollectorNotSucceeding` only fires if the collector keeps
failing, and also if the CronJob never gets to start, which `KubeJobFailed`
does not see. A single collector failure needs no action, because the next
run requests whatever is missing. `TargetDown` fires if Prometheus cannot
scrape the API.

`KubeJobFailed` keeps firing for as long as the failed Job exists, even if
the failure was days ago. That is why the collector Jobs are deleted three
days after they finish (`ttlSecondsAfterFinished` in the CronJob).

A rule is tested by copying its `expr` into Prometheus's Query page, with
the namespace already filled in. If any result comes back, the alert
condition is being met. To see it really fire, lower the threshold and the
`for`, deploy, and after seeing it as `firing` and in Alertmanager, put it
back the way it was.

In Prometheus, Alerts shows every rule and its state. The search box
filters by the rule name and its labels, not by the group name.
Alertmanager only shows the firing ones, and silences are created from
there. The `Watchdog` alert is always firing on purpose, to check that the
whole chain works.

Alertmanager sends the alerts to a Discord channel, with one message when
they move to `firing` and another when they are resolved. Each alert goes
in its own group (`group_by: ["..."]`), so each message is about a single
alert and firing and resolved ones are never mixed. If it keeps firing, it
is repeated every 12 hours. With the grouping by namespace that the chart
comes with, a message would show the whole group, with the firing and the
resolved ones together. `Watchdog` and `InfoInhibitor` go to the `null`
receiver, which sends nothing.

The webhook URL is secret, so it goes in the `alertmanager-discord` Secret,
created by hand. Alertmanager mounts it as a file and reads it from there
(`webhook_url_file`), and this way it is not in the repo:

```bash
read -rs DISCORD_WEBHOOK_URL
kubectl create secret generic alertmanager-discord -n monitoring \
  --from-literal=webhook-url="$DISCORD_WEBHOOK_URL"
```

The URL is copied from the channel's webhook, in the Discord server
settings. `read -rs` asks for it without showing it on screen, so it is
left neither in the terminal nor in the history.

The configuration Alertmanager has loaded can be seen in its web
interface, under Status. If a new configuration has an error, it keeps the
previous one. To test delivery without waiting for an alert, one can be sent
by hand through its API:

```bash
curl -s -X POST -H "Host: alertmanager.localhost" -H "Content-Type: application/json" \
  http://localhost/api/v2/alerts \
  -d '[{"labels":{"alertname":"PruebaDiscord","severity":"warning","namespace":"project0"},"annotations":{"summary":"Prueba de aviso a Discord"}}]'
```

It arrives about 30 seconds later, and about 5 minutes after that it
arrives as resolved.

The cluster runs on kind, so with the computer asleep nothing is evaluated
and no notifications arrive. When it wakes up, the alerts whose conditions
are met all fire at once, after their `for`.

## Upgrading the stack

To change a value, edit `kube-prometheus-stack-values.yaml` and compare it
with the cluster before applying it:

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

The diff uses `--skip-tests` because the chart includes a Grafana test pod
with a service account that only exists during `helm test`, and without
the option the whole diff fails. Even so, the `admission-create` and
`admission-patch` Jobs and their permissions show up as new. They are hooks
that Helm creates and deletes on every upgrade for the operator's webhook
certificate.

`kubectl diff` does not show the fields removed from objects created by
Helm. To know what to remove it needs the
`kubectl.kubernetes.io/last-applied-configuration` annotation, which only
`kubectl apply` sets, and without it, it merges the new configuration over
what is in the cluster. When a change consists of removing something, it
has to be checked after the upgrade, for example with
`kubectl get prometheus -n monitoring kube-prometheus-stack-prometheus -o yaml`.
