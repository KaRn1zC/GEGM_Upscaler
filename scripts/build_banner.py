"""Rasterise la bannière README en chargeant les fontes GEGM directement.

Pourquoi ce script plutôt que rsvg-convert ?
============================================
Les fichiers ``Vanitas-*.ttf`` du projet ont des métadonnées TTF
corrompues (style header contient un caractère ``☞``) qui empêchent
fontconfig de les indexer correctement. ``rsvg-convert`` repose sur
fontconfig et n'applique donc pas Vanitas malgré sa présence dans
``~/Library/Fonts``. Pillow + freetype, eux, prennent le chemin du
fichier ``.ttf`` directement et ignorent fontconfig — le rendu est
identique à ce que le navigateur produit avec ``@font-face``.

Sortie : ``assets/banner.png`` (2400×600).
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

# ─── Constantes design ─────────────────────────────────────────────

REPO = Path(__file__).resolve().parent.parent
FONT_VANITAS = REPO / "frontend/public/fonts/Vanitas-Regular.ttf"
FONT_ROC = REPO / "frontend/public/fonts/RocGrotesk-Regular.ttf"
OUTPUT = REPO / "assets/banner.png"

WIDTH, HEIGHT = 2400, 600

# Palette OLED Luxury × GEGM
BG = (0, 0, 0)
GLOW = (20, 54, 222)         # bleu électrique #1436DE
GLOW_DEEP = (6, 26, 132)     # bleu marine #061A84
WHITE = (255, 255, 255)
WHITE_MUTED = (255, 255, 255, 140)  # ≈ 55 % opacity

# Typo — calquée sur App.tsx:82 (sidebar GEGM) + UpscalePage.tsx:156 (titre).
# `font-display font-light` → Vanitas Regular, `tracking-tight` ≈ -0.025em.
FONT_SIZE = 220
LINE_HEIGHT = 0.95          # leading-[0.95] côté Tailwind
LETTER_SPACING_EM = -0.025  # tracking-tight Tailwind


def draw_glow_radial(img: Image.Image) -> None:
    """Glow ambient bleu marine subtil derrière la composition."""
    overlay = Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    cx, cy = WIDTH // 2, HEIGHT // 2
    # Cercle dégradé du centre vers les bords (radial gradient simulé).
    for radius, alpha in [(900, 22), (700, 30), (500, 38), (300, 42)]:
        draw.ellipse(
            (cx - radius, cy - radius, cx + radius, cy + radius),
            fill=(*GLOW, alpha),
        )
    overlay = overlay.filter(ImageFilter.GaussianBlur(radius=120))
    img.alpha_composite(overlay)


def draw_logo(img: Image.Image, x: int, y: int, total: int = 430) -> None:
    """Logo "Pixel Ascend" — 4 carrés montant en diagonale.

    Args:
        img: Canvas RGBA sur lequel dessiner.
        x, y: Coin haut-gauche du logo.
        total: Taille totale du logo (carré). 430 par défaut pour matcher
            la hauteur visuelle du wordmark.
    """
    # 4 carrés + 3 gaps → s × 4 + g × 3 = total, avec g ≈ 0.357 × s.
    s = round(total / 5.07)         # taille d'un carré
    g = round(s * 0.357)            # gap horizontal/vertical
    r = max(8, s // 9)              # corner radius

    # Couches de glow (bleu derrière les 3 premiers carrés, blanc derrière le 4e).
    for square_idx, color, opacity, glow_radius in [
        (3, WHITE, 240, 28),         # marche 4 (haut-droite, blanc + glow fort)
        (2, (79, 111, 255), 230, 12),  # marche 3 (gradient milieu)
        (1, GLOW, 230, 12),          # marche 2 (bleu)
        (0, GLOW, 195, 12),          # marche 1 (bleu profond, opacity 0.85)
    ]:
        glow_layer = Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 0))
        glow_draw = ImageDraw.Draw(glow_layer)
        col = square_idx
        sx = x + col * (s + g)
        sy = y + (3 - col) * (s + g)
        glow_draw.rounded_rectangle(
            (sx, sy, sx + s, sy + s), radius=r, fill=(*color, opacity)
        )
        glow_layer = glow_layer.filter(ImageFilter.GaussianBlur(radius=glow_radius))
        img.alpha_composite(glow_layer)

    # Carrés solides par-dessus les glows.
    draw = ImageDraw.Draw(img)
    palette = [
        (GLOW, 217),      # marche 1 — bleu profond (opacity 0.85)
        (GLOW, 255),      # marche 2 — bleu électrique
        ((79, 111, 255), 255),  # marche 3 — bleu/blanc transition
        (WHITE, 255),     # marche 4 — blanc pur
    ]
    for col, (color, alpha) in enumerate(palette):
        sx = x + col * (s + g)
        sy = y + (3 - col) * (s + g)
        draw.rounded_rectangle(
            (sx, sy, sx + s, sy + s), radius=r, fill=(*color, alpha)
        )

    # Petit point lumineux signature au coin haut-droite du carré sommet.
    sparkle_x = x + 3 * (s + g) + s - 2
    sparkle_y = y + 3
    draw.ellipse(
        (sparkle_x - 4, sparkle_y - 4, sparkle_x + 4, sparkle_y + 4),
        fill=(*WHITE, 230),
    )


def draw_text_with_tracking(
    draw: ImageDraw.ImageDraw,
    text: str,
    x: int,
    y: int,
    font: ImageFont.FreeTypeFont,
    fill: tuple[int, int, int, int],
    letter_spacing_em: float = 0.0,
) -> None:
    """Écrit un texte lettre par lettre en appliquant un letter-spacing.

    Pillow ne supporte pas nativement letter-spacing donc on compose
    manuellement. ``letter_spacing_em`` s'exprime en em (× font-size).
    """
    spacing_px = int(letter_spacing_em * font.size)
    cursor_x = x
    for ch in text:
        draw.text((cursor_x, y), ch, font=font, fill=fill)
        bbox = draw.textbbox((cursor_x, y), ch, font=font)
        char_width = bbox[2] - bbox[0]
        cursor_x += char_width + spacing_px


def build_banner() -> None:
    """Compose et sauvegarde la bannière."""
    img = Image.new("RGBA", (WIDTH, HEIGHT), (*BG, 255))

    # Fond + glow ambient
    draw_glow_radial(img)

    # Chargement fontes — directement depuis le dépôt, pas via fontconfig.
    font_vanitas = ImageFont.truetype(str(FONT_VANITAS), FONT_SIZE)

    # ─── Wordmark "GEGM" / "Upscaler" ─────────────────────────────
    # Position calculée pour que :
    #   - le HAUT visuel de "GEGM" coïncide avec le HAUT du logo
    #   - le BAS visuel de "Upscaler" (descender du "p") coïncide avec
    #     le BAS du logo
    text_x = 720

    # Anchor "lt" → coin haut-gauche du glyphe ; on calcule la baseline
    # ensuite via la bbox réelle du texte rendu.
    draw = ImageDraw.Draw(img)

    # Mesure de la hauteur visuelle d'une ligne de Vanitas Regular @ 220.
    sample_bbox = draw.textbbox((0, 0), "GEGMUpscaler", font=font_vanitas)
    line_visual_height = sample_bbox[3] - sample_bbox[1]
    line_offset = sample_bbox[1]  # offset négatif typique pour les fontes serif

    # Gap entre les baselines (leading-[0.95]).
    line_gap = int(FONT_SIZE * LINE_HEIGHT)

    # Hauteur totale du bloc texte (du top "G" au bottom du "p" descendu).
    block_height = line_gap + line_visual_height
    text_top_y = (HEIGHT - block_height) // 2

    # Position des 2 lignes — "lt" anchor permet d'utiliser y comme top du glyphe.
    line1_y = text_top_y - line_offset
    line2_y = line1_y + line_gap

    draw_text_with_tracking(
        draw, "GEGM", text_x, line1_y, font_vanitas,
        (*WHITE, 255), LETTER_SPACING_EM,
    )
    draw_text_with_tracking(
        draw, "Upscaler", text_x, line2_y, font_vanitas,
        (*WHITE, 255), LETTER_SPACING_EM,
    )

    # ─── Logo aligné sur la hauteur du bloc texte ─────────────────
    # Hauteur logo = block_height pour que :
    #   top logo = top "GEGM"
    #   bottom logo = bottom descender "Upscaler"
    logo_x = 180
    logo_y = text_top_y
    draw_logo(img, logo_x, logo_y, total=block_height)

    # Sauvegarde finale.
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    img.convert("RGB").save(OUTPUT, "PNG", optimize=True)
    print(f"OK → {OUTPUT.relative_to(REPO)} ({OUTPUT.stat().st_size:,} bytes)")


if __name__ == "__main__":
    build_banner()
