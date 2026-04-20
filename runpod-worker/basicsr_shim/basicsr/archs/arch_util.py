"""Utilitaires d'architecture compatibles avec l'API basicsr.

Fournit to_2tuple et trunc_normal_ utilisés par DRCT_arch.py
et hat_arch.py.
"""

import collections.abc
import math
from itertools import repeat

import torch


def to_2tuple(x):
    """Convertit un scalaire en tuple de 2 éléments."""
    if isinstance(x, collections.abc.Iterable):
        return tuple(x)
    return tuple(repeat(x, 2))


def trunc_normal_(tensor: torch.Tensor, mean: float = 0.0, std: float = 1.0,
                  a: float = -2.0, b: float = 2.0) -> torch.Tensor:
    """Initialisation normale tronquée (in-place)."""
    with torch.no_grad():
        low = (1.0 + math.erf((a - mean) / std / math.sqrt(2.0))) / 2.0
        up = (1.0 + math.erf((b - mean) / std / math.sqrt(2.0))) / 2.0
        tensor.uniform_(low, up)
        tensor.erfinv_()
        tensor.mul_(std * math.sqrt(2.0))
        tensor.add_(mean)
        tensor.clamp_(min=a, max=b)
    return tensor
