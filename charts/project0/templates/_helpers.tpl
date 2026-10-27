{{/*
Etiquetas que llevan todos los objetos del chart, además de su nombre. No van
en el selector ni en los pods, porque cambiarlas ahí recrearía los pods.
*/}}
{{- define "project0.labels" -}}
helm.sh/chart: {{ .Chart.Name }}-{{ .Chart.Version }}
app.kubernetes.io/part-of: {{ .Chart.Name }}
app.kubernetes.io/instance: {{ .Release.Name }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
{{- end }}
