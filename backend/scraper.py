"""
StreetSense — background data scraper
Runs forever as an asyncio task started by FastAPI's lifespan.

Sources (all free, no API keys):
  • UK Police API    https://data.police.uk        — real crime incidents
  • Open-Meteo       https://open-meteo.com        — real-time weather
  • OSM Overpass     https://overpass-api.de       — road surface & lighting
  • Reddit JSON      https://reddit.com            — community safety posts

Intervals:
  weather  → every 30 min
  crimes   → every 6 h
  roads    → every 24 h
  reddit   → every 15 min
"""

import asyncio
import hashlib
import json
import logging
from datetime import datetime, timezone, timedelta

import httpx

log = logging.getLogger("streetsense.scraper")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")

# ── Scrape targets ─────────────────────────────────────────────────────────

# Grid of London points for police + road scraping
LONDON_GRID = [
    (51.5074, -0.1278),  # Central
    (51.5200, -0.0900),  # East Central
    (51.4800, -0.1100),  # South Central
    (51.5400, -0.1400),  # North Central
    (51.4900, -0.2000),  # West London
    (51.4613, -0.1156),  # Brixton
    (51.5431, -0.0559),  # Hackney
    (51.4958, -0.1002),  # Elephant & Castle
    (51.5308, -0.1238),  # Kings Cross
    (51.4740, -0.0551),  # Peckham
    (51.5233, -0.0777),  # Shoreditch
    (51.5459, -0.0751),  # Dalston
    (51.5390, -0.1426),  # Camden
]

LONDON_BBOX = "51.35,-0.50,51.65,0.20"

# Known London areas → coordinates (for Reddit geocoding)
LONDON_AREAS = {
    "brixton": (51.4613, -0.1156),
    "hackney": (51.5431, -0.0559),
    "elephant and castle": (51.4958, -0.1002),
    "elephant": (51.4958, -0.1002),
    "kings cross": (51.5308, -0.1238),
    "peckham": (51.4740, -0.0551),
    "bethnal green": (51.5200, -0.0800),
    "whitechapel": (51.5074, -0.0680),
    "shepherds bush": (51.4893, -0.1774),
    "shepherd's bush": (51.4893, -0.1774),
    "tottenham": (51.5588, -0.0744),
    "new cross": (51.4816, -0.0072),
    "camden": (51.5390, -0.1426),
    "islington": (51.5362, -0.1033),
    "shoreditch": (51.5233, -0.0777),
    "dalston": (51.5459, -0.0751),
    "clapham": (51.4613, -0.1383),
    "stockwell": (51.4721, -0.1222),
    "waterloo": (51.5036, -0.1138),
    "london bridge": (51.5080, -0.0879),
    "stratford": (51.5416, -0.0014),
    "croydon": (51.3762, -0.0982),
    "lewisham": (51.4613, -0.0133),
    "woolwich": (51.4892, 0.0648),
    "greenwich": (51.4769, 0.0012),
    "canary wharf": (51.5054, -0.0235),
    "bank": (51.5134, -0.0886),
    "soho": (51.5130, -0.1340),
    "hoxton": (51.5295, -0.0809),
    "walthamstow": (51.5880, -0.0197),
    "ilford": (51.5590, 0.0680),
    "barking": (51.5396, 0.0798),
}

# Crime severity weights by police category
CRIME_SEVERITY = {
    "violence-and-sexual-offences": 1.00,
    "robbery":                       0.90,
    "theft-from-the-person":         0.75,
    "criminal-damage-arson":         0.60,
    "burglary":                      0.55,
    "anti-social-behaviour":         0.50,
    "drugs":                         0.40,
    "public-order":                  0.40,
    "other-theft":                   0.35,
    "vehicle-crime":                 0.30,
    "bicycle-theft":                 0.25,
    "shoplifting":                   0.20,
    "other-crime":                   0.30,
}

# WMO weather codes → (label, safety modifier)
WMO = {
    0:  ("Clear sky",           0.00),
    1:  ("Mainly clear",        0.00),
    2:  ("Partly cloudy",       0.00),
    3:  ("Overcast",            0.00),
    45: ("Fog",                -0.14),
    48: ("Icy fog",            -0.18),
    51: ("Light drizzle",      -0.05),
    53: ("Drizzle",            -0.08),
    55: ("Heavy drizzle",      -0.10),
    61: ("Light rain",         -0.08),
    63: ("Rain",               -0.12),
    65: ("Heavy rain",         -0.17),
    71: ("Light snow",         -0.15),
    73: ("Snow",               -0.22),
    75: ("Heavy snow",         -0.28),
    77: ("Snow grains",        -0.18),
    80: ("Rain showers",       -0.09),
    81: ("Heavy showers",      -0.14),
    82: ("Violent showers",    -0.20),
    85: ("Snow showers",       -0.18),
    86: ("Heavy snow showers", -0.23),
    95: ("Thunderstorm",       -0.26),
    96: ("Thunderstorm+hail",  -0.28),
    99: ("Severe thunderstorm",-0.32),
}

ROAD_SURFACE_MOD = {
    "asphalt":   0.00, "concrete":  0.00, "paved": 0.00, "tarmac": 0.00,
    "cobblestone":-0.04, "sett":   -0.04,
    "unpaved":   -0.08, "gravel":  -0.07, "dirt":  -0.09,
    "grass":     -0.10, "ground":  -0.08, "mud":   -0.14, "sand": -0.12,
    "compacted": -0.03,
}

NEG_WORDS = {"mugged","robbery","stabbed","unsafe","avoid","attack","crime","theft",
             "assault","threatening","dangerous","scared","police","arrested","gang"}
POS_WORDS = {"safe","lovely","fine","great","recommend","quiet","peaceful","nice","friendly"}

# ── Individual scrapers ────────────────────────────────────────────────────

async def scrape_crimes(client: httpx.AsyncClient, db) -> int:
    """Fetch street-level crimes from UK Police API (no key required)."""
    from database import CrimeRecord
    new = 0
    for lat, lng in LONDON_GRID:
        try:
            r = await client.get(
                f"https://data.police.uk/api/crimes-street/all-crime?lat={lat}&lng={lng}",
                timeout=20,
            )
            if r.status_code != 200:
                continue
            for c in r.json():
                pid = c.get("persistent_id", "")
                clat = float(c["location"]["latitude"])
                clng = float(c["location"]["longitude"])
                cat  = c.get("category", "other-crime")
                month = c.get("month", "")
                key = pid or hashlib.md5(f"{clat:.4f}{clng:.4f}{cat}{month}".encode()).hexdigest()

                if not db.query(CrimeRecord).filter_by(crime_key=key).first():
                    db.add(CrimeRecord(
                        crime_key=key, lat=clat, lng=clng,
                        category=cat, month=month,
                        severity=CRIME_SEVERITY.get(cat, 0.35),
                    ))
                    new += 1
            db.commit()
            await asyncio.sleep(0.7)   # polite — police API allows 15 req/s
        except Exception as exc:
            log.warning(f"[Police] {lat},{lng}: {exc}")
            db.rollback()

    log.info(f"[Police] +{new} crime records  (total scraped grid: {len(LONDON_GRID)} points)")
    return new


async def scrape_weather(client: httpx.AsyncClient, db) -> dict | None:
    """Fetch London weather from Open-Meteo (no key required)."""
    from database import WeatherRecord
    try:
        r = await client.get(
            "https://api.open-meteo.com/v1/forecast"
            "?latitude=51.5074&longitude=-0.1278"
            "&current_weather=true"
            "&forecast_days=1",
            timeout=10,
        )
        r.raise_for_status()
        cw = r.json().get("current_weather", {})

        code     = int(cw.get("weathercode", 0))
        text, mod = WMO.get(code, ("Unknown", 0.0))
        wind     = float(cw.get("windspeed", 0))
        temp     = float(cw.get("temperature", 15))

        # Additional wind penalty
        if wind > 40:
            mod -= 0.06
        mod = round(max(-0.45, mod), 3)

        if db:
            db.add(WeatherRecord(
                condition_code=code, condition_text=text,
                temp_c=temp, wind_kmh=wind,
                safety_modifier=mod,
            ))
            db.commit()

        log.info(f"[Weather] {text}, {temp}°C, wind {wind} km/h → modifier {mod:+.2f}")
        return {"code": code, "text": text, "temp": temp, "wind": wind, "mod": mod}

    except Exception as exc:
        log.warning(f"[Weather] {exc}")
        return None


async def scrape_roads(client: httpx.AsyncClient, db) -> int:
    """Query OSM Overpass for unsafe roads (unlit footways, poor surfaces)."""
    from database import RoadSegment
    query = f"""
[out:json][timeout:35];
(
  way[highway~"footway|path|residential|tertiary|unclassified"]
     [surface~"unpaved|gravel|dirt|grass|ground|mud|compacted"]
     ({LONDON_BBOX});
  way[highway~"footway|path|steps"][lit="no"]({LONDON_BBOX});
);
out center 300;
"""
    try:
        r = await client.post(
            "https://overpass-api.de/api/interpreter",
            content=query.encode(),
            timeout=40,
        )
        r.raise_for_status()
        elements = r.json().get("elements", [])
        new = 0

        for el in elements:
            if "center" not in el:
                continue
            osm_id = str(el["id"])
            if db.query(RoadSegment).filter_by(osm_id=osm_id).first():
                continue

            tags    = el.get("tags", {})
            surface = tags.get("surface", "unknown")
            lit     = tags.get("lit", "unknown")
            highway = tags.get("highway", "other")

            mod = ROAD_SURFACE_MOD.get(surface, 0.0)
            if lit == "no" and highway in ("footway", "path", "steps", "cycleway"):
                mod -= 0.09

            db.add(RoadSegment(
                osm_id=osm_id,
                lat=el["center"]["lat"], lng=el["center"]["lon"],
                highway=highway, surface=surface, lit=lit,
                safety_modifier=round(mod, 3),
            ))
            new += 1

        db.commit()
        log.info(f"[OSM] +{new} road segments")
        return new

    except Exception as exc:
        log.warning(f"[OSM] {exc}")
        if db:
            db.rollback()
        return 0


async def scrape_reddit(client: httpx.AsyncClient, db) -> int:
    """Scrape r/london + r/ukcrime for safety-relevant posts."""
    from database import ScrapedIncident
    keywords = "crime+mugged+robbery+unsafe+stabbing+assault+threatening+avoid"
    try:
        r = await client.get(
            f"https://www.reddit.com/r/london+ukcrime+policeuk/search.json"
            f"?q={keywords}&sort=new&t=week&limit=50&restrict_sr=true",
            headers={"User-Agent": "StreetSense/1.0 (safety research app)"},
            timeout=15,
        )
        if r.status_code == 429:
            log.warning("[Reddit] Rate limited, skipping")
            return 0
        r.raise_for_status()

        posts = r.json().get("data", {}).get("children", [])
        new = 0

        for p in posts:
            d    = p["data"]
            key  = f"reddit_{d.get('id','')}"
            if db.query(ScrapedIncident).filter_by(incident_key=key).first():
                continue

            title    = d.get("title", "")[:200]
            body     = (d.get("selftext", "") or "")[:400]
            full     = (title + " " + body).lower()
            url      = f"https://reddit.com{d.get('permalink','')}"

            # Geocode: find known area in text
            lat, lng = None, None
            for area, coords in LONDON_AREAS.items():
                if area in full:
                    lat, lng = coords
                    break

            neg = sum(1 for w in NEG_WORDS if w in full)
            pos = sum(1 for w in POS_WORDS if w in full)
            if neg > pos:
                sentiment, impact = "negative", -12
            elif pos > 0:
                sentiment, impact = "positive", 8
            else:
                sentiment, impact = "neutral", -3

            db.add(ScrapedIncident(
                incident_key=key, source="reddit",
                lat=lat, lng=lng,
                title=title, content=body, url=url,
                sentiment=sentiment, impact=impact,
            ))
            new += 1

        db.commit()
        log.info(f"[Reddit] +{new} incidents")
        return new

    except Exception as exc:
        log.warning(f"[Reddit] {exc}")
        if db:
            db.rollback()
        return 0


# ── Scheduler ──────────────────────────────────────────────────────────────

INTERVALS = {
    "weather": 1800,    # 30 min
    "crimes":  21600,   # 6 h
    "roads":   86400,   # 24 h
    "reddit":  900,     # 15 min
}

_last_run: dict[str, datetime] = {}
scraper_stats: dict = {
    "started_at": None,
    "runs": {},
    "errors": {},
}


async def run_scraper():
    """Main background loop. Started by FastAPI lifespan."""
    from database import DB_AVAILABLE, DBSession

    scraper_stats["started_at"] = datetime.now(timezone.utc).isoformat()
    log.info("[Scraper] Background data collection started")

    async with httpx.AsyncClient() as client:
        while True:
            now = datetime.now(timezone.utc)
            db  = DBSession() if DB_AVAILABLE and DBSession else None

            try:
                for name, interval in INTERVALS.items():
                    last = _last_run.get(name)
                    if last is None or (now - last).total_seconds() >= interval:
                        log.info(f"[Scraper] → {name}")
                        try:
                            if name == "weather":
                                await scrape_weather(client, db)
                            elif name == "crimes":
                                await scrape_crimes(client, db)
                            elif name == "roads":
                                await scrape_roads(client, db)
                            elif name == "reddit":
                                await scrape_reddit(client, db)
                            scraper_stats["runs"][name] = now.isoformat()
                        except Exception as exc:
                            log.error(f"[Scraper] {name} failed: {exc}")
                            scraper_stats["errors"][name] = str(exc)
                        _last_run[name] = now

            finally:
                if db:
                    db.close()

            await asyncio.sleep(60)   # check every minute
