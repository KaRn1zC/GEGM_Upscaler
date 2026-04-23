#!/usr/bin/env bash
#
# Télécharge les 2 poids utilisés par le worker RunPod :
#   - DRCT-L x4 pour l'upscale x4 (modèle principal)
#   - HAT-L  x2 pour l'upscale x2 (HAT a x2, DRCT n'en a pas publié)
#
# Le routage (scale_factor → modèle) est géré côté backend. Le worker
# charge simplement le bon fichier de poids selon (model_name, scale).
#
# Sources officielles :
#   DRCT : https://github.com/ming053l/DRCT#-pretrained-models
#   HAT  : https://github.com/XPixelGroup/HAT#-pretrained-models
#
# Usage :
#   chmod +x runpod-worker/scripts/download_weights.sh
#   ./runpod-worker/scripts/download_weights.sh
#
# Les fichiers sont placés dans runpod-worker/models/ pour être copiés dans
# l'image Docker au build (cf. runpod-worker/Dockerfile couche 5).
#
# Convention de nommage cible :
#   - drct-l_x4.pth        (DRCT-L pour upscale x4, ~460 MB)
#   - hat-l_x2.pth         (HAT-L pour upscale x2,  ~160 MB)
#
# Ces noms sont lus par ``_resolve_weights_path`` dans handler.py.
#
# ⚠️  Les IDs Google Drive peuvent changer entre les releases — vérifier
#     les READMEs officiels avant de lancer le script.

set -euo pipefail

# Répertoire cible — résolu en absolu relativement au script.
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MODELS_DIR="${SCRIPT_DIR}/../models"
mkdir -p "${MODELS_DIR}"

echo "=== Téléchargement des 2 poids (DRCT-L x4 + HAT-L x2) ==="
echo "Destination : ${MODELS_DIR}"
echo ""

# gdown est nécessaire pour tous les poids (hébergés sur Google Drive).
# Préférer ``uv tool install gdown`` si pip n'est pas dans le PATH.
if ! command -v gdown &> /dev/null; then
    echo "Installation de gdown (Google Drive downloader)..."
    if command -v uv &> /dev/null; then
        uv tool install --quiet gdown
        # Ajout du bin uv au PATH pour la suite du script.
        export PATH="${HOME}/.local/bin:${PATH}"
    elif command -v pip &> /dev/null; then
        pip install --quiet gdown
    else
        echo "[fail] Ni uv ni pip disponibles — installer manuellement gdown."
        exit 1
    fi
fi

# Helper : télécharge un fichier depuis Google Drive si absent.
# Args : <gdrive_file_id> <target_path> <label>
#
# Retourne toujours 0 — on ne veut pas qu'un échec de téléchargement d'un
# des fichiers casse l'autre. Le résumé final (ls -lh) montre ce qui manque.
download_if_missing() {
    local gdrive_id="$1"
    local target="$2"
    local label="$3"

    if [ -f "${target}" ]; then
        echo "[skip] $(basename "${target}") déjà présent ($(du -h "${target}" | cut -f1))"
        return 0
    fi

    if [ -z "${gdrive_id}" ]; then
        echo "[warn] ID Google Drive manquant pour ${label} — édite ce script pour le renseigner."
        return 0
    fi

    echo "[dl] ${label} → ${target}"
    if ! gdown "${gdrive_id}" -O "${target}"; then
        echo "[fail] Téléchargement de ${label} échoué — vérifier l'ID Google Drive dans ce script."
        rm -f "${target}"
        return 0
    fi
}

# ──────────────────────────────────────────────────────────────
# DRCT-L x4 — modèle principal pour l'upscale x4
# ──────────────────────────────────────────────────────────────
# ID extrait du README officiel ming053l/DRCT. Les auteurs n'ont PAS
# publié de variante DRCT-L x2 (seule la config de training est fournie).
# Pour l'upscale x2, on utilise HAT-L x2 à la place.

DRCT_L_X4_GDRIVE_ID="${DRCT_L_X4_GDRIVE_ID:-1bVxvA6QFbne2se0CQJ-jyHFy94UOi3h5}"
download_if_missing "${DRCT_L_X4_GDRIVE_ID}" "${MODELS_DIR}/drct-l_x4.pth" "DRCT-L x4"

# ──────────────────────────────────────────────────────────────
# HAT-L x2 — modèle principal pour l'upscale x2
# ──────────────────────────────────────────────────────────────
# Fichier : HAT-L_SRx2_ImageNet-pretrain.pth dans le dossier
# Pretrained Models de XPixelGroup/HAT. ID récupéré manuellement
# via "Obtenir le lien" sur le fichier.

HAT_L_X2_GDRIVE_ID="${HAT_L_X2_GDRIVE_ID:-16xtMezHvckdWEuSiOxcO-dgOlsI0rEUg}"
download_if_missing "${HAT_L_X2_GDRIVE_ID}" "${MODELS_DIR}/hat-l_x2.pth" "HAT-L x2"

# ──────────────────────────────────────────────────────────────
# Migration depuis l'ancienne convention (legacy x4 sans suffixe)
# ──────────────────────────────────────────────────────────────
# Le worker v1.9 utilisait drct-l.pth pour le x4. Si ce fichier existe
# encore mais pas drct-l_x4.pth, on copie. Évite de redownloader 500 MB
# pour rien en dev local.

if [ -f "${MODELS_DIR}/drct-l.pth" ] && [ ! -f "${MODELS_DIR}/drct-l_x4.pth" ]; then
    echo "[migrate] Copie drct-l.pth → drct-l_x4.pth"
    cp "${MODELS_DIR}/drct-l.pth" "${MODELS_DIR}/drct-l_x4.pth"
fi

echo ""
echo "=== Téléchargement terminé ==="
ls -lh "${MODELS_DIR}"
