"""Couche d'abstraction pour l'authentification."""

from app.core.auth.interface import AuthBackend, AuthenticatedUser

__all__ = ["AuthBackend", "AuthenticatedUser"]
