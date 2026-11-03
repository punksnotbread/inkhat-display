#!/usr/bin/env python3
"""
Basketball schedule display for Inky pHAT on Raspberry Pi Zero.
Fetches basketnews.lt schedule and shows the next match for
Kauno Žalgiris or Vilniaus Rytas.

Cron setup (run every 30 min):
  */30 * * * * /usr/bin/python3 /home/pi/inkhat-display/basketball_display.py
"""

from __future__ import annotations

import logging
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests
from PIL import Image, ImageDraw, ImageFont

# ── Configuration ─────────────────────────────────────────────────────────────
SCHEDULE_URL = "https://www.basketnews.lt/rungtynes.json"
SCHEDULE_PARAMS = {"team": 265}
SCHEDULE_CACHE_SCOPE = "team-265-all-leagues-v1"
TARGET_TEAMS = {"Kauno Žalgiris"}
LOG_FILE   = Path(__file__).parent / "basketball.log"
CACHE_FILE = Path(__file__).parent / "basketball_cache.json"

TEAM_NAMES: dict[str, str] = {
    # LKL
    "Kauno Žalgiris":            "Žalgiris",
    "Vilniaus Rytas":            "Rytas",
    "Jonavos Jonava Hipocredit": "Jonavos Jonava",
    # Euroleague
    "Tel Avivo Maccabi":         "Maccabi Tel Aviv",
    "Tel Avivo Hapoel":          "Hapoel Tel Aviv",
    "Madrido Real":              "Real Madrid",
    "Barselonos Barcelona":      "Barcelona",
    "Monako Monaco":             "Monaco",
    "Miuncheno Bayern":          "Bayern Munich",
    "Milanos Olimpia":           "Olimpia Milano",
    "Stambulo Fenerbahče":       "Fenerbahče Istanbul",
    "Stambulo Anadolu Efes":     "Anadolu Efes",
    "Belgrado Partizan":         "Partizan Belgrade",
    "Belgrado Crvena Zvezda":    "Crvena Zvezda",
    "Atėnų Panathinaikos":       "Panathinaikos",
    "Paryžiaus Paris":           "Paris Basketball",
    "Bolonijos Virtus":          "Virtus Bologna",
    "Berlyno Alba":              "Alba Berlin",
    "Vitorijos Baskonia":        "Baskonia",
}
# ──────────────────────────────────────────────────────────────────────────────

FONT_PATHS = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/freefont/FreeSansBold.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
]


def setup_logging() -> logging.Logger:
    log = logging.getLogger("basketball_display")
    log.setLevel(logging.WARNING)
    fmt = logging.Formatter(
        "%(asctime)s  %(levelname)-8s  %(message)s", datefmt="%Y-%m-%d %H:%M:%S"
    )

    from logging.handlers import RotatingFileHandler

    fh = RotatingFileHandler(LOG_FILE, maxBytes=500_000, backupCount=1)
    fh.setFormatter(fmt)
    log.addHandler(fh)

    ch = logging.StreamHandler(sys.stdout)
    ch.setFormatter(fmt)
    log.addHandler(ch)

    return log


def fetch_schedule() -> dict[str, Any]:
    today = datetime.now().date()
    cached_payload: dict[str, Any] | None = None
    if CACHE_FILE.exists():
        try:
            cached_payload = json.loads(CACHE_FILE.read_text(encoding="utf-8"))
            if not isinstance(cached_payload, dict) or not isinstance(cached_payload.get("upcoming"), list):
                raise ValueError("cache does not contain an upcoming match list")
            cache_date = datetime.fromtimestamp(CACHE_FILE.stat().st_mtime).date()
            if cache_date == today and cached_payload.get("_cache_scope") == SCHEDULE_CACHE_SCOPE:
                log.info("Using today's cached schedule from %s", CACHE_FILE)
                return cached_payload
        except (OSError, json.JSONDecodeError, ValueError) as e:
            log.warning("Ignoring invalid schedule cache: %s", e)
            cached_payload = None

    now_ms = int(time.time() * 1000)
    params = {**SCHEDULE_PARAMS, "_t": now_ms, "_": now_ms}
    log.info("Fetching schedule from %s", SCHEDULE_URL)
    try:
        resp = requests.get(
            SCHEDULE_URL,
            params=params,
            headers={
                "User-Agent": "Mozilla/5.0 (compatible; basketball-display/1.0)",
                "Accept": "application/json, text/javascript, */*; q=0.01",
                "Referer": "https://www.basketnews.lt/rungtynes.html?league=25&team=265",
                "X-Requested-With": "XMLHttpRequest",
            },
            timeout=15,
        )
        resp.raise_for_status()
        payload = resp.json()
        if not isinstance(payload, dict) or not isinstance(payload.get("upcoming"), list):
            raise ValueError("schedule API response does not contain an upcoming match list")
        payload["_cache_scope"] = SCHEDULE_CACHE_SCOPE
        temp_file = CACHE_FILE.with_suffix(".json.tmp")
        temp_file.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        temp_file.replace(CACHE_FILE)
        log.info("Schedule cached to %s", CACHE_FILE)
        return payload
    except (requests.RequestException, ValueError, OSError) as e:
        if cached_payload is not None:
            log.warning("Schedule API failed; using previous cached schedule: %s", e)
            return cached_payload
        raise


def parse_matches(payload: dict[str, Any]) -> list[dict[str, str | int]]:
    """Return all matches as a list of dicts with keys: team_a, team_b, timestamp, time, league."""
    games = payload.get("upcoming", [])
    if not isinstance(games, list):
        log.warning("Schedule API response has no upcoming match list")
        return []

    matches: list[dict[str, str | int]] = []

    for game in games:
        if not isinstance(game, dict):
            continue
        try:
            timestamp = int(game["rec_time"])
            team_a = str(game["team_name_1"] or "").strip()
            team_b = str(game["team_name_2"] or "").strip()
        except (KeyError, TypeError, ValueError):
            continue
        if not team_a or not team_b:
            continue
        time_str = str(game.get("time_label") or "").strip()
        league = str(game.get("league_name") or "").strip()

        matches.append(
            {
                "team_a": team_a,
                "team_b": team_b,
                "timestamp": timestamp,
                "time": time_str,
                "league": league,
            }
        )

    log.info("Parsed %d total matches", len(matches))
    return matches


def find_next_target_match(
    matches: list[dict[str, str | int]],
) -> dict[str, str | int] | None:
    """Return the soonest upcoming match involving a target team.

    Walks days chronologically. Skips any day where no target team plays.
    Returns the first match on the first day a target team appears.
    """
    now_ts = int(datetime.now(tz=timezone.utc).timestamp())

    # Filter to future matches (or currently ongoing) involving target teams.
    target_matches = [
        m
        for m in matches
        if int(m["timestamp"]) >= now_ts
        and (m["team_a"] in TARGET_TEAMS or m["team_b"] in TARGET_TEAMS)
    ]

    if not target_matches:
        log.info("No upcoming target-team matches found")
        return None

    # Find the one with the smallest timestamp (chronologically first).
    target_matches.sort(key=lambda m: int(m["timestamp"]))
    return target_matches[0]


def format_match(match: dict[str, str | int]) -> str:
    ts = int(match["timestamp"])
    dt = datetime.fromtimestamp(ts)
    date_str = dt.strftime("%Y-%m-%d")
    return f"{match['team_a']} vs {match['team_b']} @ {date_str} {match['time']}, {match['league']}"


def short_name(team: str) -> str:
    return TEAM_NAMES.get(team, team)


def load_font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    for path in FONT_PATHS:
        try:
            return ImageFont.truetype(path, size)
        except (IOError, OSError):
            continue
    log.warning("No TrueType font found, falling back to default bitmap font")
    return ImageFont.load_default()


def centered_x(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.ImageFont, width: int) -> int:
    bbox = draw.textbbox((0, 0), text, font=font)
    return (width - (bbox[2] - bbox[0])) // 2


def render(match: dict[str, str | int] | None) -> None:
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
    RED   = display.RED

    font_team = load_font(18)
    font_vs   = load_font(11)
    font_info = load_font(12)

    if match is None:
        no_match = "No upcoming match"
        draw.text((centered_x(draw, no_match, font_team, W), H // 2 - 7), no_match, BLACK, font=font_team)
    else:
        ts = int(match["timestamp"])
        dt = datetime.fromtimestamp(ts)
        date_str = dt.strftime("%Y-%m-%d")
        weekday = dt.strftime("%A")
        team_a = short_name(str(match["team_a"]))
        team_b = short_name(str(match["team_b"]))

        game_day = dt.date() == datetime.now().date()

        # Date, weekday, and start time make it easy to see how soon the game is.
        top_str = f"{date_str}  {weekday}  {match['time']}"
        draw.text((centered_x(draw, top_str, font_info, W), 5), top_str, BLACK, font=font_info)
        # separator
        draw.line([(8, 22), (W - 8, 22)], fill=BLACK, width=1)
        # vertically center the team block in the space below the separator
        sep_y = 22
        def text_h(text: str, font: ImageFont.ImageFont) -> int:
            bb = draw.textbbox((0, 0), text, font=font)
            return bb[3] - bb[1]

        gap = 4
        h_a  = text_h(team_a, font_team)
        h_vs = text_h("vs", font_vs)
        h_b  = text_h(team_b, font_team)
        block_h = h_a + gap + h_vs + gap + h_b
        start_y = sep_y + (H - sep_y - block_h) // 2

        draw.text((centered_x(draw, team_a, font_team, W), start_y), team_a, BLACK, font=font_team)
        draw.text((centered_x(draw, "vs", font_vs, W), start_y + h_a + gap), "vs", BLACK, font=font_vs)
        draw.text((centered_x(draw, team_b, font_team, W), start_y + h_a + gap + h_vs + gap), team_b, BLACK, font=font_team)

        if game_day:
            font_bang = load_font(48)
            bang_y = sep_y + (H - sep_y - text_h("!", font_bang)) // 2
            draw.text((7, bang_y - 2), "!", RED, font=font_bang)
            draw.text((W - text_h("!", font_bang) + 4, bang_y - 2), "!", RED, font=font_bang)

    log.info("Pushing image to display")
    display.set_image(img)
    display.show()
    log.info("Display updated successfully")


def main() -> None:
    try:
        payload = fetch_schedule()
    except requests.RequestException as e:
        log.error("Schedule fetch failed: %s", e)
        sys.exit(1)

    matches = parse_matches(payload)
    match = find_next_target_match(matches)

    if match is None:
        log.info("No upcoming match found for target teams")
    else:
        log.info("Next match: %s", format_match(match))

    try:
        render(match)
    except Exception as e:
        log.error("Render failed: %s", e, exc_info=True)
        sys.exit(1)


log = setup_logging()

if __name__ == "__main__":
    main()
