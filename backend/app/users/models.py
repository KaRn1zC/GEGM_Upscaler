"""Modèle SQLAlchemy pour la table des utilisateurs."""

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base

if TYPE_CHECKING:
    from app.jobs.models import Job


class User(Base):
    """Représente un utilisateur de l'application.

    Chaque utilisateur est identifié par un UUID et associé à ses
    jobs d'upscaling via la relation ``jobs``. L'email sert
    d'identifiant fonctionnel unique.

    Attributes:
        id: Identifiant unique UUID v4, généré automatiquement.
        email: Adresse email unique, indexée pour les recherches.
        name: Nom d'affichage (optionnel, renseigné via OIDC en prod).
        created_at: Horodatage de création, côté serveur PostgreSQL.
        updated_at: Horodatage de dernière modification.
        jobs: Relation one-to-many vers les jobs soumis.
    """

    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    name: Mapped[str | None] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    # ``deleted_at`` est posé lors d'une purge RGPD (cf. ``users.deletion``).
    # ``email`` et ``name`` sont réécrits au même moment avec des valeurs
    # anonymisées pour satisfaire la « right to be forgotten ». La ligne
    # reste en DB pour préserver l'intégrité référentielle (les jobs
    # pointent sur ``user_id`` via FK) mais ne porte plus d'info personnelle.
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    jobs: Mapped[list["Job"]] = relationship(back_populates="user")

    def __repr__(self) -> str:
        """Représentation lisible pour le debug et les logs."""
        return f"<User {self.email}>"
