# inkhat-display

Scripts for a Raspberry Pi Zero with an Inky pHAT e-ink display. Alternates between weather and basketball schedules every 5 minutes via cron.

## Scripts

### `weather_display.py`
Fetches current temperature, feels-like, and daily high/low from [Open-Meteo](https://open-meteo.com/) and renders it on the display.

### `basketball_display.py`
Fetches all upcoming league schedules for **Kauno Žalgiris** from Basketnews' JSON schedule API and shows the next upcoming match.

- The API response is cached once per day; if fetching fails, the last cached schedule is used
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
