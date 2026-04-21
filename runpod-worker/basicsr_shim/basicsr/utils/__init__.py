"""Shim minimal pour `basicsr.utils`.

Ré-exporte le registre d'architectures et fournit un stub de `scandir`
suffisant pour l'import dynamique de modules d'architecture par DRCT/HAT.
"""

from __future__ import annotations

import os
from collections.abc import Iterator

from basicsr.utils.registry import ARCH_REGISTRY


def scandir(
    dir_path: str,
    suffix: str | tuple[str, ...] | None = None,
    recursive: bool = False,
    full_path: bool = False,
) -> Iterator[str]:
    """Scanne un dossier et retourne les fichiers.

    Réimplémentation minimale de la fonction basicsr d'origine, suffisante
    pour le mécanisme d'auto-import des modules `*_arch.py` par DRCT/HAT.
    """
    root = dir_path

    def _scan(cur_dir: str) -> Iterator[str]:
        for entry in os.scandir(cur_dir):
            if not entry.name.startswith(".") and entry.is_file():
                path = entry.path if full_path else os.path.relpath(entry.path, root)
                if suffix is None or path.endswith(suffix):
                    yield path
            elif recursive and entry.is_dir():
                yield from _scan(entry.path)

    return _scan(dir_path)


__all__ = ["ARCH_REGISTRY", "scandir"]
