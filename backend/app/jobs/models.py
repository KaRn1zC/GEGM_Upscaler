"""Modèle SQLAlchemy pour la table des jobs d'upscaling."""

import uuid
from datetime import datetime
from enum import StrEnum
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base

if TYPE_CHECKING:
    from app.users.models import User


class JobStatus(StrEnum):
    """États du cycle de vie d'un job d'upscaling.

    Flux nominal : PENDING → QUEUED → PROCESSING → COMPLETED.
    Flux d'erreur : tout état → FAILED.
    Annulation : PENDING | QUEUED → CANCELLED.
    """

    PENDING = "pending"
    QUEUED = "queued"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class Job(Base):
    """Représente un job d'upscaling d'image soumis par un utilisateur.

    Contient les paramètres de traitement, les clés de stockage des fichiers
    d'entrée/sortie, les dimensions, la progression et les métadonnées de
    routage GPU.

    Attributes:
        id: Identifiant unique UUID v4.
        user_id: Référence vers l'utilisateur ayant soumis le job.
        status: État courant du cycle de vie (voir ``JobStatus``).
        input_key: Clé de stockage de l'image source.
        output_key: Clé de stockage du résultat (renseigné après traitement).
        scale_factor: Facteur de multiplication des dimensions (2 ou 4).
        model_name: Modèle SR utilisé. Dérivé du ``scale_factor`` côté
            serveur (``x4 → drct-l``, ``x2 → hat-l``) — le client ne
            choisit pas ce champ. Stocké pour affichage et audit.
        input_width: Largeur de l'image source en pixels.
        input_height: Hauteur de l'image source en pixels.
        output_width: Largeur du résultat (renseigné après traitement).
        output_height: Hauteur du résultat (renseigné après traitement).
        gpu_backend: Backend d'inférence utilisé (``local`` ou ``cloud``).
        gpu_run_id: Identifiant du job côté backend GPU (ex. ``run_id`` RunPod),
            utilisé pour cancel upstream en cas d'annulation utilisateur.
        progress: Avancement du traitement, de 0.0 à 1.0.
        error_message: Détail de l'erreur en cas d'échec.
        created_at: Horodatage de soumission du job.
        updated_at: Horodatage de dernière mise à jour.
        completed_at: Horodatage de fin de traitement (succès ou échec).
        user: Relation many-to-one vers l'utilisateur propriétaire.
    """

    __tablename__ = "jobs"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), index=True)
    status: Mapped[str] = mapped_column(String(20), default=JobStatus.PENDING, index=True)

    # -- Fichiers --
    input_key: Mapped[str] = mapped_column(String(500))
    output_key: Mapped[str | None] = mapped_column(String(500))

    # -- Paramètres d'upscaling --
    scale_factor: Mapped[int] = mapped_column(Integer, default=4)
    model_name: Mapped[str] = mapped_column(String(50), default="drct-l")

    # -- Dimensions (pixels) --
    input_width: Mapped[int] = mapped_column(Integer)
    input_height: Mapped[int] = mapped_column(Integer)
    output_width: Mapped[int | None] = mapped_column(Integer)
    output_height: Mapped[int | None] = mapped_column(Integer)

    # -- Routage GPU --
    gpu_backend: Mapped[str | None] = mapped_column(String(20))
    # Identifiant du job côté backend GPU (ex. ``run_id`` RunPod retourné par
    # ``submit_job``). Stocké pour permettre un cancel ciblé upstream : quand
    # l'utilisateur annule en cours de traitement, on appelle
    # ``RunPodBackend.cancel(gpu_run_id)`` pour stopper la facturation
    # serverless au lieu de laisser le job tourner pour rien.
    gpu_run_id: Mapped[str | None] = mapped_column(String(100))
    # Préférence frontend : ``True`` → tenter le local si image ≤ 5 MP ;
    # ``False`` → forcer le cloud même pour les petites images ; ``None``
    # → le routeur décide selon les dimensions seules (comportement legacy).
    # Renseigné côté frontend via ``canRunLocalStrict()`` avant soumission.
    prefer_local: Mapped[bool | None] = mapped_column(Boolean)

    # -- Progression --
    progress: Mapped[float] = mapped_column(Float, default=0.0)
    error_message: Mapped[str | None] = mapped_column(Text)

    # -- Timestamps --
    # ``created_at`` est indexé pour optimiser l'``ORDER BY created_at DESC``
    # de ``list_user_jobs`` (la requête la plus chaude — appelée à chaque
    # refresh de l'UI). PostgreSQL scanne un index B-tree dans les deux sens,
    # l'index ASC est donc aussi efficace qu'un DESC pour ce cas.
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    user: Mapped["User"] = relationship(back_populates="jobs")

    def __repr__(self) -> str:
        """Représentation lisible pour le debug et les logs."""
        return f"<Job {self.id} status={self.status}>"
