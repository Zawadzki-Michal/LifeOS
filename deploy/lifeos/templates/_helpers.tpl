{{- define "lifeos.labels" -}}
app.kubernetes.io/part-of: lifeos
app.kubernetes.io/managed-by: {{ .Release.Service }}
{{- end -}}
