"""Suppression complète d'un utilisateur et de ses données (RGPD).

Implémente le « right to be forgotten » de l'art. 17 RGPD : sur demande
de l'utilisateur (ou d'un admin), on supprime :

1. Les fichiers S3 associés à tous ses jobs (inputs + outputs).
2. Les lignes ``jobs`` correspondantes en DB.
3. Les données personnelles du ``User`` (email, name) — la ligne elle-même
   reste pour préserver l'intégrité FK mais est anonymisée et marquée
   ``deleted_at``.
4. Une entrée ``audit_log`` horodatée pour prouver la conformité RGPD.

La suppression S3 peut être lente (N fichiers, latence S3 OVH). L'endpoint
HTTP délègue donc à une tâche Celery pour répondre 202 immédiatement —
l'utilisateur voit son compte disparaître de l'UI sans attendre la purge
des bytes côté bucket.
"""

from __future__ import annotations

import asyncio
import uuid
from datetime import UTC, datetime

from loguru import logger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.audit import AuditAction, record_audit
from app.core.celery import celery_app
from app.core.config import settings
from app.core.dependencies import get_storage
from app.core.storage.interface import StorageBackend
from app.jobs.models import Job
from app.jobs.service import delete_job_files
from app.users.models import User


@celery_app.task(name="users.delete_user_data")
def delete_user_data_task(*, user_id: str, actor_email: str, action: str) -> dict[str, int]:
    """Entry Celery — cascade async de la suppression RGPD.

    Appelée depuis ``DELETE /api/users/me`` et ``DELETE /api/admin/users/{id}``.
    La session DB et le StorageBackend sont créés ici dans le process worker
    plutôt que reçus en paramètre (non-sérialisables via la queue).

    Args:
        user_id: UUID de l'utilisateur cible (format string pour la sérialisation).
        actor_email: Email de la personne qui a demandé la suppression.
        action: Valeur textuelle de ``AuditAction`` (self vs admin).

    Returns:
        ``{"jobs_deleted": N, "files_deleted": M}``.
    """
    logger.info(
        "Purge RGPD démarrée (user={uid}, actor={actor}, action={action})",
        uid=user_id,
        actor=actor_email,
        action=action,
    )
    return asyncio.run(_run_delete_user(uuid.UUID(user_id), actor_email, AuditAction(action)))


async def _run_delete_user(
    user_id: uuid.UUID,
    actor_email: str,
    action: AuditAction,
) -> dict[str, int]:
    """Crée une session DB dédiée et appelle ``delete_user_and_data``."""
    engine = create_async_engine(settings.DATABASE_URL)
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    storage = get_storage()

    try:
        async with session_factory() as session:
            return await delete_user_and_data(
                session, user_id, actor_email=actor_email, action=action, storage=storage
            )
    finally:
        await engine.dispose()


async def delete_user_and_data(
    db: AsyncSession,
    user_id: uuid.UUID,
    *,
    actor_email: str,
    action: AuditAction,
    storage: StorageBackend | None = None,
) -> dict[str, int]:
    """Supprime tous les jobs + fichiers d'un user puis anonymise la ligne.

    Args:
        db: Session SQLAlchemy async.
        user_id: UUID de l'utilisateur cible.
        actor_email: Email déclenchant la suppression (pour l'audit).
        action: ``USER_SELF_DELETED`` ou ``USER_ADMIN_DELETED``.
        storage: Instance ``StorageBackend`` injectable pour les tests.

    Returns:
        ``{"jobs_deleted": N, "files_deleted": M}``.

    Raises:
        ValueError: Si le user n'existe pas ou est déjà supprimé.
    """
    storage = storage if storage is not None else get_storage()

    user = await db.get(User, user_id)
    if user is None or user.deleted_at is not None:
        raise ValueError(f"User introuvable ou déjà supprimé : {user_id}")

    target_email = user.email

    # 1. Fichiers + lignes `jobs`. Best-effort côté S3 — un fichier déjà
    # absent ne doit pas bloquer la purge DB.
    jobs_result = await db.execute(select(Job).where(Job.user_id == user_id))
    jobs = list(jobs_result.scalars().all())

    files_deleted = 0
    for job in jobs:
        files_deleted += await delete_job_files(storage, job)
        await db.delete(job)

    # 2. Anonymisation de la ligne `users`. On préserve la FK (les
    # éventuels audit_log/autres tables référencent toujours cet UUID)
    # mais on efface les données personnelles.
    user.email = f"deleted-{user.id}@deleted.local"
    user.name = None
    user.deleted_at = datetime.now(UTC)

    # 3. Entrée d'audit — écrite dans la même transaction, atomique avec
    # la suppression elle-même.
    await record_audit(
        db,
        actor_email=actor_email,
        action=action,
        target_email=target_email,
        metadata={
            "user_id": str(user_id),
            "jobs_deleted": len(jobs),
            "files_deleted": files_deleted,
        },
    )

    await db.commit()

    logger.info(
        "Purge RGPD terminée — user={uid} jobs={j} files={f}",
        uid=str(user_id),
        j=len(jobs),
        f=files_deleted,
    )
    return {"jobs_deleted": len(jobs), "files_deleted": files_deleted}
