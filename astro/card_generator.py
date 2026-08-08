"""
Генератор графических карточек гороскопа 1080×1080 px (Pillow).
Сохраняет карточки в output_cards/YYYY-MM-DD/<знак>.png
"""
import os
import math
import random
import logging
import urllib.request
from pathlib import Path
from typing import Optional

from PIL import Image, ImageDraw, ImageFont

from config import OUTPUT_CARDS_DIR, FONTS_DIR
from astrology import SIGN_META, SIGN_COLORS

logger = logging.getLogger(__name__)

SIZE = 1080
HALF = SIZE // 2

# ── Шрифты ────────────────────────────────────────────────────────────────────

FONT_URLS = {
    "NotoSans-Regular.ttf": (
        "https://github.com/googlefonts/noto-fonts/raw/main/"
        "hinted/ttf/NotoSans/NotoSans-Regular.ttf"
    ),
    "NotoSans-Bold.ttf": (
        "https://github.com/googlefonts/noto-fonts/raw/main/"
        "hinted/ttf/NotoSans/NotoSans-Bold.ttf"
    ),
}


def ensure_fonts() -> None:
    """Скачать шрифты если их нет локально."""
    os.makedirs(FONTS_DIR, exist_ok=True)
    for name, url in FONT_URLS.items():
        path = os.path.join(FONTS_DIR, name)
        if not os.path.exists(path):
            logger.info("Загружаю шрифт %s ...", name)
            try:
                urllib.request.urlretrieve(url, path)
                logger.info("Шрифт %s загружен", name)
            except Exception as e:
                logger.warning("Не удалось загрузить %s: %s", name, e)


def _load_font(filename: str, size: int) -> ImageFont.FreeTypeFont:
    path = os.path.join(FONTS_DIR, filename)
    if os.path.exists(path):
        try:
            return ImageFont.truetype(path, size)
        except Exception:
            pass
    # Fallback — встроенный шрифт PIL (только ASCII, маленький)
    return ImageFont.load_default()


# ── Рисование фона ────────────────────────────────────────────────────────────

def _draw_background(draw: ImageDraw.ImageDraw, sign: str) -> None:
    """Тёмный космический градиент с мерцающими звёздами."""
    accent = SIGN_COLORS.get(sign, (120, 120, 200))

    # Основной градиент — от глубокого тёмно-синего до фиолетово-чёрного
    for y in range(SIZE):
        t = y / SIZE
        r = int(6  + (16 - 6)  * t + accent[0] * 0.04 * (1 - t))
        g = int(6  + (6  - 6)  * t + accent[1] * 0.02 * (1 - t))
        b = int(18 + (32 - 18) * t + accent[2] * 0.06 * (1 - t))
        draw.line([(0, y), (SIZE, y)], fill=(min(r, 40), min(g, 30), min(b, 60)))

    # Звёзды
    rng = random.Random(hash(sign))
    for _ in range(350):
        sx  = rng.randint(0, SIZE - 1)
        sy  = rng.randint(0, SIZE - 1)
        br  = rng.randint(80, 255)
        rad = rng.choices([0, 1, 2], weights=[6, 3, 1])[0]
        col = (br, br, min(br + 40, 255))
        if rad == 0:
            draw.point((sx, sy), fill=col)
        else:
            draw.ellipse([sx - rad, sy - rad, sx + rad, sy + rad], fill=col)

    # Слабое свечение в центре от цвета знака
    for r_glow in range(320, 100, -20):
        alpha = int(12 * (1 - r_glow / 320))
        col_g = (
            int(accent[0] * alpha / 255),
            int(accent[1] * alpha / 255),
            int(accent[2] * alpha / 255),
        )
        draw.ellipse(
            [HALF - r_glow, HALF - r_glow, HALF + r_glow, HALF + r_glow],
            fill=col_g,
        )


def _draw_decorative_ring(draw: ImageDraw.ImageDraw, sign: str) -> None:
    """Декоративное кольцо вокруг символа знака."""
    accent = SIGN_COLORS.get(sign, (120, 120, 200))
    r = 200

    # Внешнее кольцо
    draw.ellipse(
        [HALF - r - 6, HALF - r - 6, HALF + r + 6, HALF + r + 6],
        outline=(*accent, 80), width=2,
    )
    # Внутреннее кольцо
    draw.ellipse(
        [HALF - r + 14, HALF - r + 14, HALF + r - 14, HALF + r - 14],
        outline=(*accent, 50), width=1,
    )

    # Маленькие точки по кругу (созвездие)
    rng = random.Random(hash(sign) + 1)
    n_dots = 12
    for i in range(n_dots):
        angle = 2 * math.pi * i / n_dots
        dx = int((r + 22) * math.cos(angle))
        dy = int((r + 22) * math.sin(angle))
        size_d = rng.choice([2, 3, 4])
        brightness = rng.randint(150, 255)
        draw.ellipse(
            [HALF + dx - size_d, HALF + dy - size_d,
             HALF + dx + size_d, HALF + dy + size_d],
            fill=(brightness, brightness, min(brightness + 50, 255)),
        )


def _wrap_text(text: str, font: ImageFont.FreeTypeFont, max_width: int) -> list[str]:
    """Перенос текста по словам."""
    words  = text.split()
    lines  = []
    current = ""
    for word in words:
        test = (current + " " + word).strip()
        bbox = font.getbbox(test)
        if bbox[2] - bbox[0] <= max_width:
            current = test
        else:
            if current:
                lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines


def generate_card(
    sign: str,
    date_str: str,
    general: str,
    love: str,
    finance: str,
    health: str,
) -> str:
    """
    Создать карточку гороскопа.

    Возвращает путь к сохранённому файлу.
    """
    ensure_fonts()

    accent = SIGN_COLORS.get(sign, (120, 120, 200))
    meta   = SIGN_META.get(sign, {})
    symbol = meta.get("symbol", "✦")

    img  = Image.new("RGB", (SIZE, SIZE), color=(6, 6, 18))
    draw = ImageDraw.Draw(img)

    # Фон
    _draw_background(draw, sign)

    # Декоративное кольцо
    _draw_decorative_ring(draw, sign)

    # ── Шрифты ──────────────────────────────────────────────────────────────
    f_symbol  = _load_font("NotoSans-Regular.ttf", 160)
    f_sign    = _load_font("NotoSans-Bold.ttf",    56)
    f_date    = _load_font("NotoSans-Regular.ttf", 30)
    f_label   = _load_font("NotoSans-Bold.ttf",    24)
    f_text    = _load_font("NotoSans-Regular.ttf", 22)

    # ── Символ знака (центр) ─────────────────────────────────────────────────
    sym_bbox = f_symbol.getbbox(symbol)
    sym_w = sym_bbox[2] - sym_bbox[0]
    sym_h = sym_bbox[3] - sym_bbox[1]
    sym_x = HALF - sym_w // 2 - sym_bbox[0]
    sym_y = 310 - sym_h // 2 - sym_bbox[1]

    # Тень символа
    draw.text((sym_x + 3, sym_y + 3), symbol, font=f_symbol, fill=(0, 0, 0, 120))
    draw.text((sym_x, sym_y), symbol, font=f_symbol,
              fill=(*accent, 230))

    # ── Название знака ───────────────────────────────────────────────────────
    sign_bbox = f_sign.getbbox(sign.upper())
    sign_w    = sign_bbox[2] - sign_bbox[0]
    sign_x    = HALF - sign_w // 2
    draw.text((sign_x + 2, 478), sign.upper(), font=f_sign,
              fill=(accent[0] // 3, accent[1] // 3, accent[2] // 3))
    draw.text((sign_x, 476), sign.upper(), font=f_sign,
              fill=(*accent, 255))

    # ── Дата ─────────────────────────────────────────────────────────────────
    date_label = f"Гороскоп на {date_str}"
    date_bbox  = f_date.getbbox(date_label)
    date_x     = HALF - (date_bbox[2] - date_bbox[0]) // 2
    draw.text((date_x, 548), date_label, font=f_date,
              fill=(180, 180, 220))

    # ── Разделитель ──────────────────────────────────────────────────────────
    sep_y = 594
    draw.line([(80, sep_y), (SIZE - 80, sep_y)], fill=(*accent, 100), width=1)

    # ── Текст прогноза ───────────────────────────────────────────────────────
    sections = [
        ("◆ ОБЩЕЕ",    general),
        ("◆ ЛЮБОВЬ",   love),
        ("◆ ФИНАНСЫ",  finance),
        ("◆ ЗДОРОВЬЕ", health),
    ]

    margin  = 70
    max_w   = SIZE - margin * 2
    cur_y   = 612
    line_h  = 28
    label_h = 30

    for label, text in sections:
        if cur_y > SIZE - 50:
            break

        # Заголовок секции
        draw.text((margin, cur_y), label, font=f_label, fill=(*accent, 220))
        cur_y += label_h

        # Текст с переносом
        for line in _wrap_text(text, f_text, max_w):
            if cur_y > SIZE - 40:
                break
            draw.text((margin, cur_y), line, font=f_text, fill=(210, 210, 240))
            cur_y += line_h

        cur_y += 10   # отступ между секциями

    # ── Нижняя полоса ────────────────────────────────────────────────────────
    bar_h = 60
    bar_y = SIZE - bar_h
    for y in range(bar_y, SIZE):
        alpha = int(200 * (y - bar_y) / bar_h)
        draw.line([(0, y), (SIZE, y)], fill=(accent[0] // 6, accent[1] // 6, accent[2] // 4))

    planet = meta.get("planet", "")
    tag    = f"Астрология  •  {planet}  •  {symbol}"
    tag_b  = f_date.getbbox(tag)
    tag_x  = HALF - (tag_b[2] - tag_b[0]) // 2
    draw.text((tag_x, bar_y + 18), tag, font=f_date, fill=(150, 150, 190))

    # ── Сохранение ───────────────────────────────────────────────────────────
    folder = os.path.join(OUTPUT_CARDS_DIR, date_str)
    os.makedirs(folder, exist_ok=True)
    out_path = os.path.join(folder, f"{sign}.png")
    img.save(out_path, "PNG", optimize=False)
    logger.debug("Карточка сохранена: %s", out_path)
    return out_path


def generate_all_cards_for_date(date_str: str, horoscopes: dict) -> dict[str, str]:
    """
    Сгенерировать карточки для всех 12 знаков за одну дату.

    horoscopes: {sign: {general, love, finance, health}}
    Возвращает {sign: path}
    """
    paths = {}
    for sign, texts in horoscopes.items():
        try:
            path = generate_card(
                sign=sign,
                date_str=date_str,
                general=texts["general"],
                love=texts["love"],
                finance=texts["finance"],
                health=texts["health"],
            )
            paths[sign] = path
        except Exception as e:
            logger.error("Ошибка создания карточки %s/%s: %s", date_str, sign, e)
    return paths
