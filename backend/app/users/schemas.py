"""Schemas Pydantic pour le module de gestion des utilisateurs."""

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class UserResponse(BaseModel):
    """Représentation d'un utilisateur en sortie d'API.

    Construite directement depuis l'ORM grâce à ``from_attributes=True``.
    N'inclut que les champs publiquement exposés.
    """

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: str
    name: str | None
    created_at: datetime
