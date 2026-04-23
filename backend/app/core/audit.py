"""Journal d'audit pour les actions sensibles (GDPR, admin, suppressions).

Conservé **séparément** des données métier (jobs, users) pour survivre à
une purge RGPD : quand on supprime un utilisateur, on supprime ses données
mais on garde une trace horodatée *de la suppression elle-même*. Le RGPD
autorise explicitement ce log si les données conservées sont strictement
nécessaires à prouver la conformité (qui a supprimé quoi et quand).

Le champ ``metadata_json`` permet d'enregistrer des détails structurés
(nombre de fichiers supprimés, raison, etc.) sans exploser le schéma.
"""

import uuid
from datetime import datetime
from enum import StrEnum
from typing import Any

from sqlalchemy import JSON, DateTime, String, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class AuditAction(StrEnum):
    """Types d'actions traçables dans le journal d'audit.

    Volontairement restreint — on ne log que les actions irréversibles ou
    à implication RGPD/sécurité. Les lectures et CRUD normaux n'ont pas
    vocation à apparaître ici (trop bruyant, peu d'intérêt légal).
    """

    USER_SELF_DELETED = "user_self_deleted"
    USER_ADMIN_DELETED = "user_admin_deleted"


class AuditLog(Base):
    """Une entrée immuable du journal d'audit.

    Attributes:
        id: UUID de l'entrée.
        actor_email: Email de la personne qui a déclenché l'action (pour
            un self-delete : actor == target).
        action: Type d'action — voir ``AuditAction``.
        target_email: Email de la cible (conservé au moment T, même si le
            user est ensuite purgé côté ``users``).
        metadata_json: Détails structurés (ex: ``{"jobs_deleted": 12,
            "files_deleted": 24}``).
        created_at: Horodatage serveur.
    """

    __tablename__ = "audit_log"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    actor_email: Mapped[str] = mapped_column(String(255), index=True)
    action: Mapped[str] = mapped_column(String(64), index=True)
    target_email: Mapped[str | None] = mapped_column(String(255), index=True)
    metadata_json: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )


async def record_audit(
    db: AsyncSession,
    *,
    actor_email: str,
    action: AuditAction,
    target_email: str | None,
    metadata: dict[str, Any] | None = None,
) -> None:
    """Ajoute une entrée au journal d'audit.

    Ne commit pas — l'appelant est responsable du commit pour que l'audit
    soit atomique avec l'action elle-même. Sur rollback, l'entrée n'est
    pas écrite (c'est voulu : on n'audite pas une action qui n'a pas eu
    lieu).

    Args:
        db: Session SQLAlchemy async.
        actor_email: Email de la personne déclenchant l'action.
        action: Type d'action — une valeur de ``AuditAction``.
        target_email: Email de la cible (peut être égal à actor_email
            pour un self-delete).
        metadata: Détails structurés optionnels.
    """
    entry = AuditLog(
        actor_email=actor_email,
        action=action.value,
        target_email=target_email,
        metadata_json=metadata,
    )
    db.add(entry)
