#!/usr/bin/env bash
#
# Wrapper autour de scripts/convert_to_coreml.py qui gère les dépendances
# d'architecture : clone DRCT et HAT dans vendor/ (gitignoré) puis lance
# la conversion avec le bon PYTHONPATH (shim basicsr + repos clonés).
#
# Prérequis :
#   - macOS (Core ML)
#   - `uv sync --group coreml` (installe torch + timm + einops)
#   - Les poids .pth dans runpod-worker/models/ (via download_weights.sh)
#
# Usage :
#   ./scripts/convert_coreml.sh [drct-l|hat-l|all]
#   ./scripts/convert_coreml.sh all   # défaut : convertit les deux

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
VENDOR_DIR="${REPO_ROOT}/vendor"
MODELS_OUT="${REPO_ROOT}/models"
WEIGHTS_DIR="${REPO_ROOT}/runpod-worker/models"

MODE="${1:-all}"

mkdir -p "${VENDOR_DIR}" "${MODELS_OUT}"

# ── Clone des repos d'architecture (si absents) ─────────────────
if [ ! -d "${VENDOR_DIR}/drct-repo" ]; then
    echo "=== Clone DRCT depuis ming053l/DRCT ==="
    git clone --depth 1 https://github.com/ming053l/DRCT.git "${VENDOR_DIR}/drct-repo"
fi
if [ ! -d "${VENDOR_DIR}/hat-repo" ]; then
    echo "=== Clone HAT depuis XPixelGroup/HAT ==="
    git clone --depth 1 https://github.com/XPixelGroup/HAT.git "${VENDOR_DIR}/hat-repo"
fi

# ── PYTHONPATH : shim basicsr + repos d'archis ─────────────────
# Le shim (runpod-worker/basicsr_shim/) fournit les utilitaires basicsr
# minimaux (ARCH_REGISTRY, to_2tuple, trunc_normal_) utilisés par DRCT/HAT
# sans avoir à installer le package complet (lourd + incompatible).
export PYTHONPATH="${REPO_ROOT}/runpod-worker/basicsr_shim:${VENDOR_DIR}/drct-repo:${VENDOR_DIR}/hat-repo"

# ── Lancement de la conversion ─────────────────────────────────
cd "${REPO_ROOT}"

if [ "${MODE}" = "drct-l" ] || [ "${MODE}" = "all" ]; then
    echo ""
    echo "=== Conversion DRCT-L → Core ML ==="
    uv run python scripts/convert_to_coreml.py \
        --model drct-l \
        --weights "${WEIGHTS_DIR}/drct-l.pth" \
        --output "${MODELS_OUT}/drct-l.mlpackage" \
        --tile-size 512 \
        --precision fp16 \
        --scale 4
fi

if [ "${MODE}" = "hat-l" ] || [ "${MODE}" = "all" ]; then
    echo ""
    echo "=== Conversion HAT-L → Core ML ==="
    uv run python scripts/convert_to_coreml.py \
        --model hat-l \
        --weights "${WEIGHTS_DIR}/hat-l.pth" \
        --output "${MODELS_OUT}/hat-l.mlpackage" \
        --tile-size 512 \
        --precision fp16 \
        --scale 4
fi

echo ""
echo "=== Fait ==="
ls -lh "${MODELS_OUT}/"
