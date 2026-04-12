# inkhat-display

Scripts for a Raspberry Pi Zero with an Inky pHAT e-ink display. Alternates between weather and basketball schedules every 5 minutes via cron.

## Scripts

### `weather_display.py`
Fetches current temperature, feels-like, and daily high/low from [Open-Meteo](https://open-meteo.com/) and renders it on the display.

### `basketball_display.py`
Fetches the Lithuanian basketball schedule from [basketnews.lt](https://www.basketnews.lt/rungtynes/tvarkarastis/lietuva.html) and shows the next upcoming match for **Kauno Žalgiris** or **Vilniaus Rytas**. Skips days with no target team playing and finds the next one.

- HTML is cached locally — fetched once per week
- Team names are shortened for display (e.g. "Kauno Žalgiris" → "Žalgiris")
- On game day, red `!` markers appear on both sides of the display

## Cron

```
0,10,20,30,40,50 * * * * python3 /home/pi/inkhat-display/basketball_display.py
5,15,25,35,45,55 * * * * python3 /home/pi/inkhat-display/weather_display.py
```

## Deploy

Sync to the Pi with rsync and run scripts via SSH. Adjust paths to match your setup.

```
rsync -av /path/to/inkhat-display/ pi@raspberrypi:/home/pi/inkhat-display/
```

## Dependencies

Installed on the Pi:
- `inky` — Pimoroni Inky pHAT library
- `Pillow` — image rendering
- `requests` — HTTP fetching
- `lxml`, `cssselect` — HTML parsing
