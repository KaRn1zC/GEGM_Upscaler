"""Logique métier pour la gestion des utilisateurs.

Ce module centralise les opérations DB liées aux utilisateurs. Il est
appelé par ``dependencies.get_current_user`` lors de l'authentification
(auto-provisioning) et pourrait être étendu par de futurs endpoints
CRUD si besoin.
"""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.users.models import User


async def get_or_create_by_email(
    db: AsyncSession,
    email: str,
    name: str | None = None,
) -> User:
    """Retourne l'utilisateur correspondant à l'email, le crée s'il n'existe pas.

    Pattern *auto-provisioning* : à la première authentification d'un nouvel
    utilisateur (OIDC ou token statique), on crée son enregistrement DB
    à la volée à partir de l'identité fournie par l'``AuthBackend``.

    Args:
        db: Session de base de données async.
        email: Adresse email (identifiant fonctionnel unique).
        name: Nom d'affichage optionnel. Ignoré si l'utilisateur existe déjà
            — on ne met pas à jour le nom automatiquement pour éviter
            d'écraser une valeur custom en DB.

    Returns:
        Instance ``User`` existante ou nouvellement créée.
    """
    result = await db.execute(select(User).where(User.email == email))
    user = result.scalar_one_or_none()

    if user is None:
        user = User(email=email, name=name)
        db.add(user)
        await db.commit()
        await db.refresh(user)

    return user
