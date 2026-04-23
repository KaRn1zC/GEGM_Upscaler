"""Routeur API pour la gestion des utilisateurs.

Expose :
- ``GET  /api/users/me``       — utilisateur courant (auto-provisionné).
- ``DELETE /api/users/me``     — self-delete RGPD (cascade async).
- ``DELETE /api/admin/users/{user_id}`` — admin variant.

Auto-provisioning des users : à la première connexion, ``get_current_user``
appelle ``get_or_create_by_email`` qui insère la ligne si absente.
"""

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit import AuditAction
from app.core.database import get_db
from app.core.dependencies import get_current_user, require_admin
from app.users.deletion import delete_user_data_task
from app.users.models import User
from app.users.schemas import UserResponse

router = APIRouter(tags=["users"])


@router.get("/api/users/me", response_model=UserResponse)
async def get_me(user: User = Depends(get_current_user)) -> UserResponse:
    """Retourne l'utilisateur authentifié courant.

    L'utilisateur est identifié via le token Bearer dans le header
    ``Authorization``, et auto-provisionné s'il n'existe pas encore en DB.
    """
    return UserResponse.model_validate(user)


@router.delete("/api/users/me", status_code=status.HTTP_202_ACCEPTED)
async def delete_me(user: User = Depends(get_current_user)) -> dict[str, str]:
    """Déclenche la suppression complète du compte et des données (RGPD).

    Enqueue une tâche Celery qui :
    1. Supprime tous les fichiers S3 associés (inputs + outputs).
    2. Supprime les lignes ``jobs``.
    3. Anonymise la ligne ``users`` (email + name effacés, ``deleted_at`` posé).
    4. Écrit une entrée ``audit_log``.

    La réponse est immédiate (202 Accepted) — la purge S3 peut prendre
    quelques secondes à minutes selon le volume. Côté client, il faut
    déconnecter le user (``logout`` Keycloak) après l'appel pour qu'il
    ne puisse pas continuer à utiliser son token invalide.
    """
    logger.info("Self-delete demandé (user={email})", email=user.email)
    delete_user_data_task.delay(
        user_id=str(user.id),
        actor_email=user.email,
        action=AuditAction.USER_SELF_DELETED.value,
    )
    return {"status": "accepted", "detail": "Suppression en cours"}


@router.delete(
    "/api/admin/users/{user_id}",
    status_code=status.HTTP_202_ACCEPTED,
)
async def admin_delete_user(
    user_id: uuid.UUID,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> dict[str, str]:
    """Variante admin de la suppression — pour les demandes externes.

    Utile quand un ex-employé fait une demande RGPD par écrit mais n'a
    plus accès à l'app. Même cascade que ``delete_me`` mais avec l'email
    de l'admin comme ``actor_email`` dans l'audit log.

    Raises:
        HTTPException: 403 si le caller n'est pas dans ``ADMIN_EMAILS``,
            404 si l'UUID n'existe pas.
    """
    # Vérif d'existence légère côté endpoint — le worker la refera mais
    # ça permet de renvoyer un 404 propre au lieu d'un 202 suivi d'une
    # task qui plante silencieusement côté Celery.
    target = await db.get(User, user_id)
    if target is None or target.deleted_at is not None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Utilisateur introuvable ou déjà supprimé",
        )

    logger.info(
        "Admin-delete demandé (admin={a}, target={t})",
        a=admin.email,
        t=str(user_id),
    )
    delete_user_data_task.delay(
        user_id=str(user_id),
        actor_email=admin.email,
        action=AuditAction.USER_ADMIN_DELETED.value,
    )
    return {"status": "accepted", "detail": "Suppression en cours"}
