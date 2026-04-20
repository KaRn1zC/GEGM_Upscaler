"""Registre simplifié compatible avec l'API basicsr.

Seul ARCH_REGISTRY est utilisé par DRCT_arch.py et hat_arch.py
pour décorer les classes d'architecture.
"""


class Registry:
    """Registre clé-valeur pour les classes d'architecture."""

    def __init__(self, name: str) -> None:
        self._name = name
        self._obj_map: dict[str, type] = {}

    def register(self, obj=None, name=None):
        """Décorateur ou appel direct pour enregistrer une classe."""
        if obj is None:
            def decorator(fn):
                key = name if name else fn.__name__
                self._obj_map[key] = fn
                return fn
            return decorator
        key = name if name else obj.__name__
        self._obj_map[key] = obj
        return obj

    def get(self, name: str):
        """Récupère une classe enregistrée par son nom."""
        return self._obj_map.get(name)


ARCH_REGISTRY = Registry("arch")
