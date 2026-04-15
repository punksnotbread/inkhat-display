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
import sys
from datetime import datetime, timezone
from pathlib import Path

import requests
from lxml import html as lxml_html
from PIL import Image, ImageDraw, ImageFont

# ── Configuration ─────────────────────────────────────────────────────────────
SCHEDULE_URL = "https://www.basketnews.lt/rungtynes/tvarkarastis/lietuva.html"
TARGET_TEAMS = {"Kauno Žalgiris", "Vilniaus Rytas"}
LOG_FILE   = Path(__file__).parent / "basketball.log"
CACHE_FILE = Path(__file__).parent / "basketball_cache.html"

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


def fetch_schedule() -> str:
    if CACHE_FILE.exists():
        age_days = (datetime.now() - datetime.fromtimestamp(CACHE_FILE.stat().st_mtime)).days
        if age_days < 7:
            log.info("Loading schedule from cache (%s)", CACHE_FILE)
            return CACHE_FILE.read_text(encoding="utf-8")

    log.info("Fetching schedule from %s", SCHEDULE_URL)
    resp = requests.get(
        SCHEDULE_URL,
        headers={"User-Agent": "Mozilla/5.0 (compatible; basketball-display/1.0)"},
        timeout=15,
    )
    resp.raise_for_status()
    html = resp.text
    CACHE_FILE.write_text(html, encoding="utf-8")
    log.info("Schedule cached to %s", CACHE_FILE)
    return html


def parse_matches(raw_html: str) -> list[dict[str, str | int]]:
    """Return all matches as a list of dicts with keys: team_a, team_b, timestamp, time, league."""
    tree = lxml_html.fromstring(raw_html)

    games = tree.cssselect("#game-schedule .game")
    if not games:
        log.warning("Could not find #game-schedule .game elements in HTML")
        return []

    matches: list[dict[str, str | int]] = []

    for game in games:
        t1_links = game.cssselect(".team-1 > a")
        t2_links = game.cssselect(".team-2 > a")
        if not t1_links or not t2_links:
            continue

        team_a = (t1_links[0].text_content() or "").strip()
        team_b = (t2_links[0].text_content() or "").strip()

        ts_str = game.get("data-time", "")
        if not ts_str:
            continue
        try:
            timestamp = int(ts_str)
        except ValueError:
            continue

        time_els = game.cssselect(".game-time a")
        time_str = (time_els[0].text_content() or "").strip() if time_els else ""

        league_els = game.cssselect(".league a")
        league = (league_els[0].text_content() or "").strip() if league_els else ""

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
        league_str = str(match["league"])
        team_a = short_name(str(match["team_a"]))
        team_b = short_name(str(match["team_b"]))

        game_day = dt.date() == datetime.now().date()
        team_color = RED if game_day else BLACK

        # date + time + league on one row
        top_str = f"{date_str}  {match['time']}  {league_str}"
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
        html = fetch_schedule()
    except requests.RequestException as e:
        log.error("Schedule fetch failed: %s", e)
        sys.exit(1)

    matches = parse_matches(html)
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
