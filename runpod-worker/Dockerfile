# Image RunPod avec CUDA 12.4 + PyTorch préinstallé.
# Structure en couches optimisée : deps système → deps Python → code app
# → poids modèle (les couches les plus stables en premier pour le cache).

FROM runpod/pytorch:2.8.0-py3.11-cuda12.8.1-cudnn-devel-ubuntu22.04

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    MODEL_DIR=/models \
    DEFAULT_MODEL=drct-l \
    TILE_SIZE=512 \
    TILE_OVERLAP=32

WORKDIR /workspace

# ── Couche 1 : dépendances système (rarement modifiées) ──
RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    libgl1 \
    libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

# ── Couche 2 : dépendances Python (modifiées occasionnellement) ──
# torch et torchvision sont déjà dans l'image de base — on ne les réinstalle pas.
COPY requirements.txt .
RUN pip install --upgrade pip && pip install -r requirements.txt

# ── Couche 3 : shim basicsr minimal ──
# DRCT_arch.py et hat_arch.py importent 3 utilitaires de basicsr
# (ARCH_REGISTRY, to_2tuple, trunc_normal_). On fournit un shim léger
# au lieu d'installer le package complet (lourd + incompatible).
COPY basicsr_shim/basicsr/ /workspace/basicsr/

# ── Couche 4 : fichiers d'architecture DRCT + HAT ──
# On ne copie que les fichiers nécessaires à l'inférence, pas les modules
# de training/data qui déclenchent des imports en cascade de basicsr.
RUN git clone --depth 1 https://github.com/ming053l/DRCT.git /opt/drct && \
    mkdir -p /workspace/drct/archs && \
    cp /opt/drct/drct/archs/DRCT_arch.py /workspace/drct/archs/ && \
    touch /workspace/drct/__init__.py /workspace/drct/archs/__init__.py && \
    git clone --depth 1 https://github.com/XPixelGroup/HAT.git /opt/hat && \
    mkdir -p /workspace/hat/archs && \
    cp /opt/hat/hat/archs/hat_arch.py /workspace/hat/archs/ && \
    touch /workspace/hat/__init__.py /workspace/hat/archs/__init__.py && \
    rm -rf /opt/drct /opt/hat

# ── Couche 5 : poids modèles (~1.2 Go pour les 4 fichiers) ──
# Les 4 variantes (DRCT-L x2/x4 + HAT-L x2/x4) sont téléchargées par
# ``scripts/download_weights.sh`` dans ``runpod-worker/models/`` avant le
# build. Convention de nommage : ``{model}_x{scale}.pth``. Le runtime
# route via ``handler._resolve_weights_path`` selon le scale_factor demandé.
RUN mkdir -p ${MODEL_DIR}
COPY models/*.pth ${MODEL_DIR}/

# ── Couche 6 : code applicatif (la plus volatile) ──
COPY handler.py .

CMD ["python", "-u", "handler.py"]
