#!/usr/bin/env python3
"""
Weather display for Inky pHAT on Raspberry Pi Zero.
Shows date, current temp, feels like, high, and low via Open-Meteo.

Cron setup (run every 30 min):
  crontab -e
  */30 * * * * /usr/bin/python3 /home/pi/inkhat-display/weather_display.py
"""

from __future__ import annotations

import logging
import sys
from datetime import datetime
from pathlib import Path

import requests
from PIL import Image, ImageDraw, ImageFont

# ── Configuration ─────────────────────────────────────────────────────────────
LATITUDE  = 54.6872    # Vilnius, Lithuania
LONGITUDE = 25.2797
UNITS     = "celsius"  # "fahrenheit" or "celsius"
LOG_FILE  = Path(__file__).parent / "weather.log"
# ──────────────────────────────────────────────────────────────────────────────

UNIT_SYMBOL = "°C" if UNITS == "celsius" else "°F"

FONT_PATHS = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/freefont/FreeSansBold.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
]


def setup_logging() -> logging.Logger:
    log = logging.getLogger("weather_display")
    log.setLevel(logging.WARNING)
    fmt = logging.Formatter("%(asctime)s  %(levelname)-8s  %(message)s", datefmt="%Y-%m-%d %H:%M:%S")

    # File handler — keeps last ~500 KB then rotates once
    from logging.handlers import RotatingFileHandler
    fh = RotatingFileHandler(LOG_FILE, maxBytes=500_000, backupCount=1)
    fh.setFormatter(fmt)
    log.addHandler(fh)

    # Console handler
    ch = logging.StreamHandler(sys.stdout)
    ch.setFormatter(fmt)
    log.addHandler(ch)

    return log


def load_font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    for path in FONT_PATHS:
        try:
            return ImageFont.truetype(path, size)
        except (IOError, OSError):
            continue
    log.warning("No TrueType font found, falling back to default bitmap font")
    return ImageFont.load_default()


def get_weather() -> dict[str, int]:
    log.info("Fetching weather for %.4f, %.4f", LATITUDE, LONGITUDE)
    resp = requests.get(
        "https://api.open-meteo.com/v1/forecast",
        params={
            "latitude":         LATITUDE,
            "longitude":        LONGITUDE,
            "current":          "temperature_2m,apparent_temperature",
            "daily":            "temperature_2m_max,temperature_2m_min",
            "temperature_unit": UNITS,
            "timezone":         "auto",
            "forecast_days":    1,
        },
        timeout=10,
    )
    resp.raise_for_status()
    data = resp.json()
    weather = {
        "temp":       round(data["current"]["temperature_2m"]),
        "feels_like": round(data["current"]["apparent_temperature"]),
        "high":       round(data["daily"]["temperature_2m_max"][0]),
        "low":        round(data["daily"]["temperature_2m_min"][0]),
    }
    log.info(
        "Weather: %d%s (feels %d%s)  H:%d  L:%d",
        weather["temp"], UNIT_SYMBOL,
        weather["feels_like"], UNIT_SYMBOL,
        weather["high"], weather["low"],
    )
    return weather


def centered_x(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.ImageFont, width: int) -> int:
    bbox = draw.textbbox((0, 0), text, font=font)
    return (width - (bbox[2] - bbox[0])) // 2


def render(weather: dict[str, int]) -> None:
    log.info("Initialising display")
    from inky.auto import auto

    display = auto()
    display.set_border(display.WHITE)

    W, H = display.WIDTH, display.HEIGHT
    log.debug("Display size: %dx%d", W, H)

    img = Image.new("P", (W, H))
    img.putpalette([255, 255, 255,   # 0 = WHITE
                    0,   0,   0,     # 1 = BLACK
                    255, 0,   0,     # 2 = RED
                    ] + [0] * (256 - 3) * 3)
    draw = ImageDraw.Draw(img)
    draw.rectangle([0, 0, W, H], fill=display.WHITE)
    BLACK = display.BLACK

    font_date  = load_font(13)
    font_temp  = load_font(38)
    font_small = load_font(13)

    date_str = datetime.now().strftime("%A, %B %-d")
    temp_str = f"{weather['temp']}° / {weather['feels_like']}°"
    hilo_str = f"H: {weather['high']}{UNIT_SYMBOL}   L: {weather['low']}{UNIT_SYMBOL}"

    # Date — centered
    draw.text((centered_x(draw, date_str, font_date, W), 5), date_str, BLACK, font=font_date)
    draw.line([(8, 22), (W - 8, 22)], fill=BLACK, width=1)

    # Temp / feels like — large, centered
    draw.text((centered_x(draw, temp_str, font_temp, W), 26), temp_str, BLACK, font=font_temp)

    # Unit label below
    unit_label = f"{UNIT_SYMBOL}  real / feels"
    draw.text((centered_x(draw, unit_label, font_small, W), 68), unit_label, BLACK, font=font_small)

    # High / Low
    draw.text((centered_x(draw, hilo_str, font_small, W), 86), hilo_str, BLACK, font=font_small)

    log.info("Pushing image to display")
    display.set_image(img)
    display.show()
    log.info("Display updated successfully")


def main() -> None:
    try:
        weather = get_weather()
    except requests.RequestException as e:
        log.error("Weather fetch failed: %s", e)
        sys.exit(1)

    try:
        render(weather)
    except Exception as e:
        log.error("Render failed: %s", e, exc_info=True)
        sys.exit(1)


log = setup_logging()

if __name__ == "__main__":
    main()
