{{/* vim: set filetype=mustache: */}}

{{/*
Nom complet de la release — tronqué à 63 chars (limite DNS).
*/}}
{{- define "gegm-upscaler.fullname" -}}
{{- if .Values.fullnameOverride -}}
{{- .Values.fullnameOverride | trunc 63 | trimSuffix "-" -}}
{{- else -}}
{{- $name := default .Chart.Name .Values.nameOverride -}}
{{- if contains $name .Release.Name -}}
{{- .Release.Name | trunc 63 | trimSuffix "-" -}}
{{- else -}}
{{- printf "%s-%s" .Release.Name $name | trunc 63 | trimSuffix "-" -}}
{{- end -}}
{{- end -}}
{{- end -}}

{{/*
Nom court du chart.
*/}}
{{- define "gegm-upscaler.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" -}}
{{- end -}}

{{/*
Labels communs à appliquer sur toutes les ressources (convention Helm).
*/}}
{{- define "gegm-upscaler.labels" -}}
helm.sh/chart: {{ printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" | trunc 63 | trimSuffix "-" }}
{{ include "gegm-upscaler.selectorLabels" . }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
app.kubernetes.io/part-of: gegm-upscaler
{{- end -}}

{{/*
Labels de sélection (stables — ne jamais inclure version/chart pour éviter
de casser les rollouts).
*/}}
{{- define "gegm-upscaler.selectorLabels" -}}
app.kubernetes.io/name: {{ include "gegm-upscaler.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end -}}

{{/*
Nom du ServiceAccount — override possible via values.serviceAccount.name.
*/}}
{{- define "gegm-upscaler.serviceAccountName" -}}
{{- if .Values.serviceAccount.create -}}
{{- default (include "gegm-upscaler.fullname" .) .Values.serviceAccount.name -}}
{{- else -}}
{{- default "default" .Values.serviceAccount.name -}}
{{- end -}}
{{- end -}}

{{/*
Image complète `repo:tag`. Si values.image.tag vide → fallback sur
Chart.AppVersion pour garder un lockstep naturel avec les releases.
*/}}
{{- define "gegm-upscaler.image" -}}
{{- $tag := default .Chart.AppVersion .Values.image.tag -}}
{{- printf "%s:%s" .Values.image.repository $tag -}}
{{- end -}}

{{/*
Nom du ConfigMap de config publique.
*/}}
{{- define "gegm-upscaler.configMapName" -}}
{{- printf "%s-config" (include "gegm-upscaler.fullname" .) -}}
{{- end -}}

{{/*
Nom du Secret synchronisé par ExternalSecret.
*/}}
{{- define "gegm-upscaler.secretName" -}}
{{- printf "%s-secrets" (include "gegm-upscaler.fullname" .) -}}
{{- end -}}
