# Image RunPod avec CUDA 12.1 + PyTorch préinstallé.
# Structure en couches optimisée : deps système → deps Python → code app
# → poids modèle (les couches les plus stables en premier pour le cache).

FROM runpod/pytorch:2.5.1-py3.11-cuda12.1.1-devel-ubuntu22.04

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
COPY requirements.txt .
RUN pip install --upgrade pip && pip install -r requirements.txt

# ── Couche 3 : code d'architecture DRCT + HAT (cloné depuis GitHub) ──
RUN git clone --depth 1 https://github.com/ming053l/DRCT.git /opt/drct && \
    cp -r /opt/drct/drct /workspace/drct && \
    git clone --depth 1 https://github.com/XPixelGroup/HAT.git /opt/hat && \
    cp -r /opt/hat/hat /workspace/hat && \
    rm -rf /opt/drct /opt/hat

# ── Couche 4 : poids modèles (60-200 Mo, à télécharger au build) ──
# Placer drct-l.pth et hat-l.pth dans ce dossier avant de builder,
# ou utiliser une étape de téléchargement (ex: wget depuis un bucket).
RUN mkdir -p ${MODEL_DIR}
COPY models/*.pth ${MODEL_DIR}/

# ── Couche 5 : code applicatif (la plus volatile) ──
COPY handler.py .

CMD ["python", "-u", "handler.py"]
