"""Routeur API pour la gestion des utilisateurs.

Expose uniquement l'endpoint ``/api/users/me`` qui retourne l'utilisateur
actuellement authentifié. La création est automatique à la première
connexion (auto-provisioning dans ``get_current_user``).
"""

from fastapi import APIRouter, Depends

from app.core.dependencies import get_current_user
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
