"""Shim minimal de basicsr pour l'inférence DRCT/HAT.

Fournit uniquement les utilitaires nécessaires aux fichiers
d'architecture (ARCH_REGISTRY, to_2tuple, trunc_normal_) sans
embarquer les dépendances lourdes de training de basicsr.
"""
