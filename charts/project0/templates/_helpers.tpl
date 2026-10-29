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

{{/*
Tag de las imágenes propias. Si values no dice otro, el appVersion del chart.
*/}}
{{- define "project0.imageTag" -}}
{{ .Values.image.tag | default .Chart.AppVersion }}
{{- end }}
