#!/usr/bin/env bash
#
# Télécharge les poids DRCT-L et HAT-L pour le worker RunPod.
#
# Source officielle DRCT : https://github.com/ming053l/DRCT
#   - drct-l.pth hébergé sur Google Drive (liens dans le README du repo)
# Source officielle HAT : https://github.com/XPixelGroup/HAT
#   - hat-l.pth hébergé sur Google Drive / HuggingFace
#
# Usage :
#   chmod +x runpod-worker/scripts/download_weights.sh
#   ./runpod-worker/scripts/download_weights.sh
#
# Les fichiers sont placés dans runpod-worker/models/ pour être copiés
# dans l'image Docker au build (cf. runpod-worker/Dockerfile couche 4).

set -euo pipefail

# Répertoire cible — résolu en absolu relativement au script.
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MODELS_DIR="${SCRIPT_DIR}/../models"
mkdir -p "${MODELS_DIR}"

echo "=== Téléchargement des poids DRCT-L et HAT-L ==="
echo "Destination : ${MODELS_DIR}"
echo ""

# ──────────────────────────────────────────────────────────────
# DRCT-L — Dense Residual Connected Transformer Large
# ──────────────────────────────────────────────────────────────
# ming053l/DRCT fournit les poids via Google Drive. gdown est le moyen le
# plus fiable pour télécharger depuis Drive en ligne de commande.
#
# ⚠️  Les IDs Google Drive changent entre les releases — vérifier le README
#     officiel avant de lancer le script :
#     https://github.com/ming053l/DRCT#-pretrained-models

DRCT_L_GDRIVE_ID="${DRCT_L_GDRIVE_ID:-REPLACE_ME_AVEC_L_ID_DU_README_DRCT}"
DRCT_L_TARGET="${MODELS_DIR}/drct-l.pth"

if [ -f "${DRCT_L_TARGET}" ]; then
    echo "[skip] drct-l.pth existe déjà"
else
    if ! command -v gdown &> /dev/null; then
        echo "Installation de gdown (Google Drive downloader)..."
        pip install --quiet gdown
    fi
    echo "[1/2] Téléchargement drct-l.pth..."
    gdown --id "${DRCT_L_GDRIVE_ID}" -O "${DRCT_L_TARGET}"
fi

# ──────────────────────────────────────────────────────────────
# HAT-L — Hybrid Attention Transformer Large (fallback)
# ──────────────────────────────────────────────────────────────
# XPixelGroup/HAT fournit les poids sur Google Drive et HuggingFace. On
# préfère HuggingFace pour la stabilité.
#
# Vérifier l'URL exacte sur :
# https://github.com/XPixelGroup/HAT#-pretrained-models

HAT_L_URL="${HAT_L_URL:-https://huggingface.co/spaces/HatL/HAT/resolve/main/HAT-L_SRx4_ImageNet-pretrain.pth}"
HAT_L_TARGET="${MODELS_DIR}/hat-l.pth"

if [ -f "${HAT_L_TARGET}" ]; then
    echo "[skip] hat-l.pth existe déjà"
else
    echo "[2/2] Téléchargement hat-l.pth..."
    curl -L --fail -o "${HAT_L_TARGET}" "${HAT_L_URL}"
fi

echo ""
echo "=== Téléchargement terminé ==="
ls -lh "${MODELS_DIR}"
