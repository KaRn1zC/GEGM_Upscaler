"""Découpage et réassemblage d'images en tuiles pour la super-résolution.

Les modèles SR ont une empreinte mémoire GPU proportionnelle aux
dimensions de l'entrée. Pour traiter des images dépassant la capacité
du modèle, on les découpe en tuiles avec chevauchement (overlap), on
traite chaque tuile individuellement, puis on réassemble le résultat
avec un blending linéaire dans les zones de recouvrement pour éviter
les artefacts de couture.
"""

import numpy as np
from numpy.typing import NDArray


def compute_tile_grid(
    width: int,
    height: int,
    tile_size: int,
    overlap: int,
) -> list[tuple[int, int, int, int]]:
    """Calcule les coordonnées de chaque tuile sur la grille.

    Génère une grille régulière de tuiles couvrant intégralement
    l'image, en ajustant la dernière tuile de chaque rangée/colonne
    pour ne pas dépasser les bords.

    Args:
        width: Largeur de l'image en pixels.
        height: Hauteur de l'image en pixels.
        tile_size: Dimension carrée de chaque tuile (pixels).
        overlap: Chevauchement entre tuiles adjacentes (pixels).

    Returns:
        Liste de tuples ``(x, y, w, h)`` — coin supérieur gauche et
        dimensions de chaque tuile.

    Raises:
        ValueError: Si le tile_size ou l'overlap sont incohérents.
    """
    if tile_size <= 0:
        raise ValueError(f"tile_size doit être > 0, reçu {tile_size}")
    if overlap < 0 or overlap >= tile_size:
        raise ValueError(f"overlap doit être dans [0, tile_size[, reçu {overlap}")

    step = tile_size - overlap
    tiles: list[tuple[int, int, int, int]] = []

    y = 0
    while y < height:
        x = 0
        tile_h = min(tile_size, height - y)

        while x < width:
            tile_w = min(tile_size, width - x)
            tiles.append((x, y, tile_w, tile_h))

            if x + tile_size >= width:
                break
            x += step

        if y + tile_size >= height:
            break
        y += step

    return tiles


def split_into_tiles(
    image: NDArray[np.uint8],
    tile_size: int,
    overlap: int,
) -> list[tuple[tuple[int, int, int, int], NDArray[np.uint8]]]:
    """Découpe une image en tuiles avec chevauchement.

    Args:
        image: Image source au format ``(H, W, C)`` en uint8.
        tile_size: Dimension carrée de chaque tuile.
        overlap: Chevauchement entre tuiles adjacentes.

    Returns:
        Liste de paires ``(coords, tile_array)`` où coords est
        ``(x, y, w, h)`` et tile_array est le crop correspondant.
    """
    h, w = image.shape[:2]
    grid = compute_tile_grid(w, h, tile_size, overlap)

    tiles: list[tuple[tuple[int, int, int, int], NDArray[np.uint8]]] = []
    for x, y, tw, th in grid:
        tile = image[y : y + th, x : x + tw].copy()
        tiles.append(((x, y, tw, th), tile))

    return tiles


def _build_blend_mask(
    tile_w: int,
    tile_h: int,
    overlap: int,
    *,
    has_left: bool,
    has_top: bool,
    has_right: bool,
    has_bottom: bool,
) -> NDArray[np.float32]:
    """Construit un masque de blending pour une tuile.

    Le masque vaut 1.0 au centre et décroît linéairement vers 0.0
    dans les zones de chevauchement, sauf sur les bords de l'image
    où il reste à 1.0.

    Args:
        tile_w: Largeur de la tuile.
        tile_h: Hauteur de la tuile.
        overlap: Taille de la zone de chevauchement.
        has_left: La tuile a un voisin à gauche.
        has_top: La tuile a un voisin en haut.
        has_right: La tuile a un voisin à droite.
        has_bottom: La tuile a un voisin en bas.

    Returns:
        Masque ``(tile_h, tile_w)`` en float32 dans [0, 1].
    """
    mask = np.ones((tile_h, tile_w), dtype=np.float32)

    if overlap > 0:
        ramp = np.linspace(0.0, 1.0, overlap, dtype=np.float32)

        if has_left and overlap <= tile_w:
            mask[:, :overlap] *= ramp[np.newaxis, :]
        if has_right and overlap <= tile_w:
            mask[:, -overlap:] *= ramp[np.newaxis, ::-1]
        if has_top and overlap <= tile_h:
            mask[:overlap, :] *= ramp[:, np.newaxis]
        if has_bottom and overlap <= tile_h:
            mask[-overlap:, :] *= ramp[::-1, np.newaxis]

    return mask


def merge_tiles(
    tiles: list[tuple[tuple[int, int, int, int], NDArray[np.uint8]]],
    output_width: int,
    output_height: int,
    overlap: int,
    channels: int = 3,
) -> NDArray[np.uint8]:
    """Réassemble des tuiles traitées en une image complète.

    Utilise un blending linéaire dans les zones de chevauchement pour
    des transitions imperceptibles entre tuiles adjacentes.

    Args:
        tiles: Paires ``(coords, tile_array)`` issues du traitement SR.
            Les coords ``(x, y, w, h)`` doivent correspondre aux
            positions dans l'espace de sortie (déjà mis à l'échelle).
        output_width: Largeur totale de l'image de sortie.
        output_height: Hauteur totale de l'image de sortie.
        overlap: Chevauchement dans l'espace de sortie.
        channels: Nombre de canaux (3 pour RGB, 4 pour RGBA).

    Returns:
        Image réassemblée ``(H, W, C)`` en uint8.
    """
    # Accumulateurs float pour le blending pondéré.
    canvas = np.zeros((output_height, output_width, channels), dtype=np.float64)
    weights = np.zeros((output_height, output_width), dtype=np.float64)

    for (x, y, tw, th), tile in tiles:
        has_left = x > 0
        has_top = y > 0
        has_right = x + tw < output_width
        has_bottom = y + th < output_height

        mask = _build_blend_mask(
            tw,
            th,
            overlap,
            has_left=has_left,
            has_top=has_top,
            has_right=has_right,
            has_bottom=has_bottom,
        )

        # Ajuster si la tuile ne fait pas exactement (th, tw).
        actual_h, actual_w = tile.shape[:2]
        mask = mask[:actual_h, :actual_w]

        region = (slice(y, y + actual_h), slice(x, x + actual_w))
        canvas[region] += tile.astype(np.float64) * mask[:, :, np.newaxis]
        weights[region] += mask

    # Normalisation — éviter la division par zéro.
    weights = np.maximum(weights, 1e-8)
    canvas /= weights[:, :, np.newaxis]

    return canvas.clip(0, 255).astype(np.uint8)
