from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from pydantic import BaseModel
import asyncio
import math
import random
import json
import io
import urllib.request
from datetime import datetime, timezone, timedelta

# ---------------------------------------------------------------------------
# Database models — imported from shared database.py
# ---------------------------------------------------------------------------

from database import (
    DB_AVAILABLE, DBSession,
    PostRecord, CrimeRecord, WeatherRecord, RoadSegment, ScrapedIncident,
)

_in_memory_posts: list[dict] = []
_next_id = 1


# ---------------------------------------------------------------------------
# FastAPI lifespan — starts background scraper
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    from scraper import run_scraper
    task = asyncio.create_task(run_scraper())
    yield
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass


app = FastAPI(title="StreetSense API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# London hotspots / safe zones (base model, enriched by real data below)
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Seeded crime hotspots  (lat, lng, intensity 0-1)
# Based on real MPS crime data patterns — higher intensity = more dangerous
# ---------------------------------------------------------------------------
HOTSPOTS = [
    # ── Tier 1 — Critical risk ──────────────────────────────────────────────
    (51.4613, -0.1156, 0.96),  # Brixton
    (51.4740, -0.0551, 0.94),  # Peckham
    (51.5431, -0.0559, 0.92),  # Hackney / Dalston
    (51.4958, -0.1002, 0.90),  # Elephant & Castle
    (51.5074, -0.0680, 0.88),  # Whitechapel
    (51.5588, -0.0744, 0.87),  # Tottenham
    (51.4816, -0.0072, 0.86),  # New Cross / Deptford

    # ── Tier 2 — High risk ──────────────────────────────────────────────────
    (51.5308, -0.1238, 0.82),  # Kings Cross / St Pancras
    (51.5200, -0.0800, 0.80),  # Bethnal Green
    (51.5233, -0.0777, 0.78),  # Shoreditch
    (51.5459, -0.0751, 0.77),  # Dalston Junction
    (51.4721, -0.1222, 0.76),  # Stockwell
    (51.5295, -0.0809, 0.75),  # Hoxton
    (51.5080, -0.0879, 0.74),  # London Bridge / Borough
    (51.4892,  0.0648, 0.73),  # Woolwich
    (51.5036, -0.1138, 0.72),  # Waterloo
    (51.5396,  0.0798, 0.71),  # Barking
    (51.3762, -0.0982, 0.70),  # Croydon

    # ── Tier 3 — Moderate-high risk ─────────────────────────────────────────
    (51.4893, -0.1774, 0.68),  # Shepherd's Bush
    (51.5362, -0.1033, 0.66),  # Islington / Angel
    (51.5390, -0.1426, 0.65),  # Camden Town
    (51.5416, -0.0014, 0.64),  # Stratford
    (51.5130, -0.1340, 0.63),  # Soho / Oxford St
    (51.4769,  0.0012, 0.62),  # Greenwich
    (51.5590,  0.0680, 0.61),  # Ilford
    (51.5880, -0.0197, 0.60),  # Walthamstow
    (51.4613, -0.0133, 0.59),  # Lewisham
    (51.5054, -0.0235, 0.58),  # Canary Wharf / Poplar
    (51.5134, -0.0886, 0.57),  # Bank / Monument
    (51.4958, -0.1774, 0.55),  # Hammersmith
    (51.5054, -0.1132, 0.54),  # South Bank / Lambeth North
]

# ---------------------------------------------------------------------------
# Seeded safe zones  (lat, lng, pull-down intensity)
# Areas with consistently lower crime — suppresses danger scores nearby
# ---------------------------------------------------------------------------
SAFE_ZONES = [
    # ── Outer west / south-west — traditionally very low crime ───────────────
    (51.5000, -0.1950, 0.10),  # Kensington / Holland Park
    (51.4613, -0.3037, 0.11),  # Richmond
    (51.4241, -0.2054, 0.10),  # Wimbledon
    (51.4862, -0.2408, 0.09),  # Barnes / Mortlake
    (51.5074, -0.2900, 0.10),  # Ealing
    (51.4527, -0.3017, 0.10),  # Kingston upon Thames
    (51.4480, -0.3360, 0.09),  # Twickenham
    (51.4755, -0.2610, 0.09),  # Richmond Park
    (51.5136, -0.2162, 0.09),  # Chiswick
    (51.4161, -0.1865, 0.09),  # Sutton
    (51.4000, -0.1360, 0.08),  # Croydon south / Purley
    (51.4300, -0.2450, 0.08),  # New Malden / Worcester Park
    (51.4000, -0.2850, 0.09),  # Epsom border / Cheam

    # ── North London suburbs ─────────────────────────────────────────────────
    (51.5565, -0.1783, 0.10),  # Hampstead / Golders Green
    (51.6252, -0.1517, 0.09),  # Barnet
    (51.5981, -0.3077, 0.09),  # Harrow
    (51.6538, -0.1798, 0.08),  # Mill Hill / Edgware
    (51.5712, -0.2731, 0.08),  # Wembley / Sudbury
    (51.6050, -0.0780, 0.08),  # Enfield / Southgate
    (51.5800, -0.2200, 0.08),  # Stanmore / Queensbury
    (51.6500, -0.2400, 0.08),  # Edgware / Canons Park

    # ── East / south-east suburbs ────────────────────────────────────────────
    (51.4400,  0.0800, 0.08),  # Bromley
    (51.3700,  0.0600, 0.08),  # Orpington
    (51.4650,  0.1150, 0.08),  # Sidcup / Bexley
    (51.5200,  0.1600, 0.07),  # Romford / Havering border
    (51.5600,  0.1800, 0.07),  # Upminster area

    # ── Inner pockets that feel safer ────────────────────────────────────────
    (51.5150, -0.1420, 0.07),  # Fitzrovia / Marylebone
    (51.5050, -0.1750, 0.07),  # South Kensington
    (51.4950, -0.1750, 0.08),  # Fulham
    (51.4820, -0.1940, 0.07),  # Putney
    (51.5500, -0.1000, 0.07),  # Highbury / Canonbury
]


def haversine(lat1, lon1, lat2, lon2):
    R = 6371
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (math.sin(dlat / 2) ** 2
         + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon / 2) ** 2)
    return R * 2 * math.asin(math.sqrt(a))


def _octave_noise(lat: float, lng: float) -> float:
    """
    Multi-octave deterministic noise that produces realistic street-level variation.
    Three octaves at different spatial scales — coarse neighbourhood, block, street:
      octave 1 ~2 km   amplitude 0.13  — neighbourhood character
      octave 2 ~400 m  amplitude 0.09  — block-by-block variation
      octave 3 ~100 m  amplitude 0.05  — individual street variation
    Values are in [-0.27, +0.27].
    """
    s = math.sin
    c = math.cos
    return (
        s(lat * 312.7) * c(lng * 198.3) * 0.13 +
        s(lat * 1573.1) * c(lng * 991.7) * 0.09 +
        s(lat * 6271.3) * c(lng * 3947.9) * 0.05 +
        # Cross terms for less grid-aligned patterns
        s(lat * 445.1 + lng * 312.9) * 0.04 +
        s(lat * 1821.7 - lng * 1134.3) * 0.03
    )


def get_area_danger(lat: float, lng: float) -> float:
    """
    Returns danger in [0.0, 1.0].

    Gaussian hotspot influence + safe-zone suppression + multi-octave noise.
    The noise component creates meaningful score differences between streets
    that are only 100-200 m apart, avoiding the uniform-blob problem.

    Baseline (no nearby hotspot): ~0.15 → score ~72 (Low/Medium boundary).
    """
    SIGMA2_H = 2 * 1.2 ** 2   # σ=1.2 km — tighter hotspot radius
    SIGMA2_S = 2 * 2.0 ** 2   # σ=2.0 km — broader safe suppression

    danger = sum(
        intensity * math.exp(-(haversine(lat, lng, hlat, hlng) ** 2) / SIGMA2_H)
        for hlat, hlng, intensity in HOTSPOTS
    )
    safe_pull = sum(
        intensity * math.exp(-(haversine(lat, lng, slat, slng) ** 2) / SIGMA2_S)
        for slat, slng, intensity in SAFE_ZONES
    )

    BASE = 0.15
    raw = BASE + danger * 0.75 - safe_pull * 0.8 + _octave_noise(lat, lng)
    return max(0.02, min(0.98, raw))


def get_time_modifier(hour: int) -> float:
    if 7 <= hour < 19:   return -0.15
    elif 19 <= hour < 21: return 0.0
    elif 21 <= hour < 23: return 0.10
    else:                 return 0.28


# ---------------------------------------------------------------------------
# Real-data enrichment  (queries DB for crime / weather / road records)
# ---------------------------------------------------------------------------

def get_enriched_data(lat: float, lng: float) -> dict:
    """
    Returns:
        crime_mod     — negative float (0.0 if no data)
        crime_count   — int of recent crimes within 500m
        weather_mod   — float modifier from latest weather record
        weather_text  — human-readable condition string
        weather_temp  — temp in °C
        weather_wind  — wind speed km/h
        road_mod      — average road/lighting modifier within 250m
        road_flags    — list of human-readable road warnings
        data_sources  — list of active data sources
    """
    result = {
        "crime_mod": 0.0, "crime_count": 0,
        "weather_mod": 0.0, "weather_text": None, "weather_temp": None, "weather_wind": None,
        "road_mod": 0.0, "road_flags": [],
        "data_sources": [],
    }
    if not DB_AVAILABLE or not DBSession:
        return result

    db = DBSession()
    try:
        # ── Crimes within 500 m, last 90 days ────────────────────────────
        cutoff_month = (datetime.now(timezone.utc) - timedelta(days=90)).strftime("%Y-%m")
        crimes = db.query(CrimeRecord).filter(CrimeRecord.month >= cutoff_month).all()
        nearby_crimes = [c for c in crimes if haversine(lat, lng, c.lat, c.lng) <= 0.5]
        if nearby_crimes:
            avg_sev = sum(c.severity for c in nearby_crimes) / len(nearby_crimes)
            # Each nearby crime contributes a small danger increment, capped at 0.30
            result["crime_mod"] = min(0.30, len(nearby_crimes) * avg_sev * 0.008)
            result["crime_count"] = len(nearby_crimes)
            result["data_sources"].append("UK Police API")

        # ── Latest weather ─────────────────────────────────────────────────
        weather = db.query(WeatherRecord).order_by(WeatherRecord.fetched_at.desc()).first()
        if weather:
            result["weather_mod"] = weather.safety_modifier
            result["weather_text"] = weather.condition_text
            result["weather_temp"] = weather.temp_c
            result["weather_wind"] = weather.wind_kmh
            result["data_sources"].append("Open-Meteo")

        # ── Road segments within 250 m ─────────────────────────────────────
        roads = db.query(RoadSegment).all()
        nearby_roads = [r for r in roads if haversine(lat, lng, r.lat, r.lng) <= 0.25]
        if nearby_roads:
            result["road_mod"] = sum(r.safety_modifier for r in nearby_roads) / len(nearby_roads)
            flags = set()
            for r in nearby_roads:
                if r.lit == "no":
                    flags.add("Unlit paths nearby")
                if r.surface in ("unpaved", "gravel", "dirt", "mud", "grass"):
                    flags.add("Poor road surface")
                if r.surface in ("cobblestone", "sett"):
                    flags.add("Cobblestone surface")
            result["road_flags"] = list(flags)
            result["data_sources"].append("OpenStreetMap")

    except Exception as exc:
        import logging
        logging.getLogger("streetsense.main").warning(f"[enrich] {exc}")
    finally:
        db.close()

    return result


# ---------------------------------------------------------------------------
# DB helpers for posts
# ---------------------------------------------------------------------------

def _db_save_post(lat, lng, username, content, sentiment, impact, tags) -> int:
    global _next_id
    if DB_AVAILABLE and DBSession:
        db = DBSession()
        try:
            r = PostRecord(lat=lat, lng=lng, username=username, content=content,
                           sentiment=sentiment, impact=impact,
                           tags=json.dumps(tags), platform="streetsense")
            db.add(r)
            db.commit()
            db.refresh(r)
            return r.id
        finally:
            db.close()
    else:
        pid = _next_id
        _next_id += 1
        _in_memory_posts.append(dict(id=pid, lat=lat, lng=lng, username=username,
                                     content=content, sentiment=sentiment, impact=impact,
                                     tags=tags, created_at=datetime.now(timezone.utc)))
        return pid


def _db_get_nearby_posts(lat, lng) -> list[dict]:
    now = datetime.now(timezone.utc)
    results = []
    if DB_AVAILABLE and DBSession:
        db = DBSession()
        try:
            rows = db.query(PostRecord).order_by(PostRecord.created_at.desc()).limit(500).all()
            for r in rows:
                if haversine(lat, lng, r.lat, r.lng) <= 0.6:
                    created = r.created_at
                    if created.tzinfo is None:
                        created = created.replace(tzinfo=timezone.utc)
                    results.append(dict(
                        id=f"user_{r.id}", username=r.username, content=r.content,
                        minutes_ago=max(0, int((now - created).total_seconds() / 60)),
                        sentiment=r.sentiment, impact=r.impact,
                        tags=json.loads(r.tags), platform="streetsense", is_user_post=True,
                    ))
        finally:
            db.close()
    else:
        for p in _in_memory_posts:
            if haversine(lat, lng, p["lat"], p["lng"]) <= 0.6:
                results.append(dict(
                    id=f"user_{p['id']}", username=p["username"], content=p["content"],
                    minutes_ago=max(0, int((now - p["created_at"]).total_seconds() / 60)),
                    sentiment=p["sentiment"], impact=p["impact"],
                    tags=p["tags"], platform="streetsense", is_user_post=True,
                ))
    return results


# ---------------------------------------------------------------------------
# Safety endpoint
# ---------------------------------------------------------------------------

@app.get("/api/safety")
def get_safety(lat: float, lng: float, hour: int = -1):
    if hour == -1:
        hour = datetime.now().hour

    danger = get_area_danger(lat, lng)
    time_mod = get_time_modifier(hour)

    # Real-data enrichment
    enriched = get_enriched_data(lat, lng)
    crime_mod   = enriched["crime_mod"]
    weather_mod = enriched["weather_mod"]
    road_mod    = enriched["road_mod"]

    final_danger = max(0.01, min(0.99, danger + time_mod + crime_mod + weather_mod + road_mod))
    score = max(4, min(99, round((1 - final_danger) * 100)))

    # Lighting
    if 7 <= hour < 20:
        lighting = "Good"
    elif 6 <= hour < 7 or 20 <= hour < 22:
        lighting = "Fair"
    else:
        lighting = "Poor"
    # Road data can override lighting
    if "Unlit paths nearby" in enriched["road_flags"]:
        lighting = "Poor"

    # Foot traffic
    if hour in range(8, 10) or hour in range(17, 20):
        foot_traffic = "High"
    elif hour in range(10, 17) or hour in range(20, 22):
        foot_traffic = "Medium"
    else:
        foot_traffic = "Low"

    rng = random.Random(int(lat * 1000) + int(lng * 1000))
    # Prefer real crime count if available, fall back to model estimate
    incidents_30d = enriched["crime_count"] if enriched["crime_count"] else max(0, round(final_danger * 60 + rng.gauss(0, 4)))
    response_time = max(4, round(5 + final_danger * 15))

    if danger < 0.35:   cctv = "Low"
    elif danger < 0.65: cctv = "Medium"
    else:               cctv = "High"

    if score >= 75:   risk = "Low"
    elif score >= 50: risk = "Medium"
    elif score >= 30: risk = "High"
    else:             risk = "Critical"

    summaries = {
        "Low":      f"This area is generally safe right now. {foot_traffic} foot traffic and {lighting.lower()} lighting make it a comfortable route.",
        "Medium":   f"Some caution advised. {incidents_30d} incidents reported nearby in the past 30 days. Lighting is {lighting.lower()}.",
        "High":     f"Elevated risk detected. Avoid isolated paths and stay in well-lit areas. Consider travelling with others.",
        "Critical": f"High risk area at this hour. Multiple incidents reported. Avoid if possible — use a main road or alternative route.",
    }

    weather_info = None
    if enriched["weather_text"]:
        weather_info = {
            "condition": enriched["weather_text"],
            "temp_c": enriched["weather_temp"],
            "wind_kmh": enriched["weather_wind"],
            "modifier": enriched["weather_mod"],
        }

    return {
        "score": score,
        "risk_level": risk,
        "summary": summaries[risk],
        "hour": hour,
        "metrics": {
            "lighting": lighting,
            "foot_traffic": foot_traffic,
            "incidents_30d": incidents_30d,
            "response_time_min": response_time,
            "cctv_coverage": cctv,
        },
        "score_breakdown": {
            "base":    round((1 - max(0.01, min(0.99, danger + time_mod))) * 100),
            "crime":   round(-crime_mod * 100, 1),
            "weather": round(weather_mod * 100, 1),
            "road":    round(road_mod * 100, 1),
        },
        "road_flags":   enriched["road_flags"],
        "weather":      weather_info,
        "data_sources": enriched["data_sources"],
    }


# ---------------------------------------------------------------------------
# Weather endpoint
# ---------------------------------------------------------------------------

@app.get("/api/weather")
def get_weather():
    if not DB_AVAILABLE or not DBSession:
        return {"available": False}
    db = DBSession()
    try:
        w = db.query(WeatherRecord).order_by(WeatherRecord.fetched_at.desc()).first()
        if not w:
            return {"available": False}
        return {
            "available": True,
            "condition_code": w.condition_code,
            "condition": w.condition_text,
            "temp_c": w.temp_c,
            "wind_kmh": w.wind_kmh,
            "safety_modifier": w.safety_modifier,
            "fetched_at": w.fetched_at.isoformat() if w.fetched_at else None,
        }
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Scraper status endpoint
# ---------------------------------------------------------------------------

@app.get("/api/scraper/status")
def get_scraper_status():
    try:
        from scraper import scraper_stats
        return scraper_stats
    except Exception:
        return {"error": "scraper not available"}


# ---------------------------------------------------------------------------
# Social media mock data + semantic analysis
# ---------------------------------------------------------------------------

NEGATIVE_POSTS = [
    ("Just witnessed a fight near here, people ran off down the road. Stay safe out there 😟", -18),
    ("Had my phone nearly snatched walking through here tonight. Be careful everyone", -22),
    ("Police presence here rn, looks like something happened earlier. Avoid if you can", -12),
    ("Felt really unsafe walking through just now. Group of guys were aggressive", -15),
    ("Sketchy vibe here tonight, made me really uncomfortable walking alone", -10),
    ("Someone was following me near here, got into a shop to be safe. Be alert", -20),
    ("Heard shouting and glass breaking. Not a great spot at this hour", -14),
    ("Not safe here right now — use a different route, trust me", -16),
    ("Saw police tape further up, definitely something happened here", -13),
    ("Got asked for money aggressively twice in 5 mins here. Stressful walk", -9),
]

NEUTRAL_POSTS = [
    ("Walking through now, seems pretty quiet tonight tbh", -2),
    ("Not many people around at this hour but nothing major", -3),
    ("Looks normal here, nothing unusual to report", 1),
    ("Bit dark around here but nothing sketchy going on", -4),
    ("Just passed through, fairly empty but fine", 0),
]

POSITIVE_POSTS = [
    ("Really lovely evening walk tonight, felt totally safe the whole way 😊", 12),
    ("Loads of people out here, great atmosphere, felt super comfortable", 10),
    ("Police patrol walking through regularly, feels very secure 👮", 14),
    ("Busy area, well-lit, saw families out and about. All good here!", 11),
    ("Just walked this route alone and felt completely fine. Recommend it!", 9),
    ("Street lights are great here and there's always someone around 💡", 8),
    ("Lovely community feel, people are friendly. Felt safe the whole time", 10),
    ("Night market nearby means it's really lively and safe feeling here", 13),
]

USERNAMES = [
    "londonwalker", "safetyfirst_uk", "night_owl_ldn", "commuter_kate",
    "ldn_local", "jaywalks_london", "urbanexplorer99", "saferoutes_jen",
    "latenight_ldn", "thereallib", "streets_of_ldn", "walkwise_tom",
    "ldn_dispatch", "roamingsafely", "citypulse_uk", "patrice_ldn",
    "anika_walks", "nightshift_ldn", "safepath_mk", "real_ldn_vibes",
]

SEMANTIC_SIGNALS = {
    "incident":      ["fight", "snatched", "robbery", "attack", "witnessed", "assault", "stabbing", "trouble"],
    "police":        ["police", "patrol", "officers", "police tape", "police presence"],
    "poor_lighting": ["dark", "unlit", "no lights", "poorly lit"],
    "good_lighting": ["well-lit", "street lights", "bright", "lit up"],
    "crowded":       ["loads of people", "busy", "families", "lively", "crowd", "lots of people"],
    "empty":         ["quiet", "empty", "nobody around", "not many people", "deserted"],
    "warning":       ["avoid", "unsafe", "be careful", "stay safe", "different route", "not safe"],
    "positive":      ["safe", "lovely", "comfortable", "fine", "great", "secure", "recommend"],
    "threat":        ["following", "aggressive", "sketchy", "group", "scary"],
}


def extract_semantic_tags(text: str, sentiment: str) -> list[str]:
    text_lower = text.lower()
    tags = []
    for signal, keywords in SEMANTIC_SIGNALS.items():
        if any(kw in text_lower for kw in keywords):
            if signal == "incident":         tags.append("incident reported")
            elif signal == "police":         tags.append("police activity")
            elif signal == "poor_lighting":  tags.append("poor lighting")
            elif signal == "good_lighting":  tags.append("good lighting")
            elif signal == "crowded":        tags.append("active area")
            elif signal == "empty":          tags.append("quiet area")
            elif signal == "warning":        tags.append("avoid advised")
            elif signal == "positive" and sentiment == "positive": tags.append("feels safe")
            elif signal == "threat":         tags.append("threatening behaviour")
    return tags[:2]


NEGATIVE_KEYWORDS = [
    "fight", "unsafe", "snatched", "avoid", "aggressive", "scary", "threat",
    "followed", "attacked", "robbery", "dangerous", "trouble", "sketchy",
    "uncomfortable", "intimidating", "mugged", "threatening", "suspicious",
]
POSITIVE_KEYWORDS = [
    "safe", "lovely", "comfortable", "fine", "great", "secure", "recommend",
    "bright", "busy", "friendly", "police patrol", "well-lit", "peaceful", "nice",
]


def analyze_user_sentiment(text: str) -> tuple[str, int]:
    t = text.lower()
    neg = sum(1 for kw in NEGATIVE_KEYWORDS if kw in t)
    pos = sum(1 for kw in POSITIVE_KEYWORDS if kw in t)
    if neg > pos: return "negative", -14
    if pos > neg: return "positive", 10
    return "neutral", -2


class PostCreate(BaseModel):
    lat: float
    lng: float
    username: str
    content: str


def _generate_mock_posts(lat: float, lng: float, hour: int) -> list[dict]:
    danger = get_area_danger(lat, lng)
    time_mod = get_time_modifier(hour)
    final_danger = max(0.01, min(0.99, danger + time_mod))

    rng = random.Random(int(lat * 10000) + int(lng * 10000) + hour // 3)
    posts = []
    for i in range(rng.randint(3, 5)):
        roll = rng.random()
        neg_threshold = final_danger * 0.68
        neu_threshold = neg_threshold + 0.18
        if roll < neg_threshold:
            template, base_impact = rng.choice(NEGATIVE_POSTS); sentiment = "negative"
        elif roll < neu_threshold:
            template, base_impact = rng.choice(NEUTRAL_POSTS);  sentiment = "neutral"
        else:
            template, base_impact = rng.choice(POSITIVE_POSTS); sentiment = "positive"

        posts.append({
            "id": f"mock_{i}",
            "username": rng.choice(USERNAMES),
            "content": template,
            "minutes_ago": rng.randint(4, 240),
            "sentiment": sentiment,
            "impact": base_impact + rng.randint(-2, 2),
            "tags": extract_semantic_tags(template, sentiment),
            "platform": rng.choice(["twitter", "reddit", "nextdoor", "twitter", "twitter"]),
            "is_user_post": False,
        })
    return posts


@app.post("/api/posts")
def create_post(body: PostCreate):
    print("")
    username = body.username.strip() or "anonymous"
    content  = body.content.strip()

    # Use ML classifier if available, fall back to keyword heuristic
    try:
        from ml.classifiers import classify
        ml = classify(content)
        # Map severity (0-1) to impact score (-22 to +14) matching mock post scale
        if ml["category"] in ("safe",):
            sentiment = "positive"
            impact    = round(ml["severity"] * -5 + 10)   # safe → positive impact
        elif ml["category"] in ("neutral",):
            sentiment = "neutral"
            impact    = round(-3 - ml["severity"] * 4)
        else:
            sentiment = "negative"
            impact    = round(-6 - ml["severity"] * 16)   # severity 1.0 → impact -22
        tags = extract_semantic_tags(content, sentiment) + [ml["category"].replace("_", " ")]
        tags = list(dict.fromkeys(tags))[:3]
    except Exception:
        sentiment, impact = analyze_user_sentiment(content)
        tags = extract_semantic_tags(content, sentiment)
    print("woof")
    print(impact)
    pid = _db_save_post(body.lat, body.lng, username, content, sentiment, impact, tags)
    return {
        "id": f"user_{pid}", "username": username, "content": content,
        "minutes_ago": 0, "sentiment": sentiment, "impact": impact,
        "tags": tags, "platform": "streetsense", "is_user_post": True,
    }


@app.get("/api/posts")
def get_posts(lat: float, lng: float, hour: int = -1):
    if hour == -1:
        hour = datetime.now(timezone.utc).hour
    user_posts = _db_get_nearby_posts(lat, lng)
    mock_posts = _generate_mock_posts(lat, lng, hour)
    all_posts = user_posts + mock_posts
    all_posts.sort(key=lambda p: p["minutes_ago"])
    total_impact = max(-45, min(45, sum(p["impact"] for p in all_posts)))
    return {
        "posts": all_posts[:10],
        "total_impact": total_impact,
        "post_count": len(all_posts),
        "user_post_count": len(user_posts),
    }


# ── Heatmap bounds (must match frontend ImageOverlay bounds) ──────────────────
HEATMAP_BOUNDS = {
    "lat_min": 51.35, "lat_max": 51.65,
    "lng_min": -0.50, "lng_max":  0.20,
}



CMAPS = {
    # Night palette — danger value thresholds aligned with score bands:
    #   danger < 0.20  → score > 75 → Low      → transparent
    #   danger 0.20-0.45 → score 55-75 → Medium  → blue
    #   danger 0.45-0.65 → score 35-55 → High    → purple→red
    #   danger > 0.65  → score < 35 → Critical  → orange→amber
    "night": [
        (0.00,   0,   0,   0,   0),
        (0.18,   0,   0,   0,   0),   # transparent — safe baseline
        (0.24,  14,  40, 140,  50),   # blue whisper
        (0.35,  29,  78, 216, 150),   # blue — Medium
        (0.48, 109,  40, 217, 195),   # purple
        (0.58, 190,  24,  93, 215),   # magenta
        (0.65, 220,  38,  38, 225),   # crimson — High
        (0.76, 249, 115,  22, 238),   # orange
        (0.87, 251, 191,  36, 248),   # amber — Critical
        (1.00, 255, 255, 200, 255),   # white-hot peak
    ],
    "day": [
        (0.00,   0,   0,   0,   0),
        (0.18,   0,   0,   0,   0),
        (0.24,  22, 163,  74,  60),   # green whisper
        (0.35,  34, 197,  94, 150),   # green — Medium
        (0.48, 132, 204,  22, 190),   # lime
        (0.58, 234, 179,   8, 210),   # yellow
        (0.65, 249, 115,  22, 225),   # orange — High
        (0.76, 239,  68,  68, 238),   # red
        (0.87, 185,  28,  28, 248),   # deep red — Critical
        (1.00, 127,  29,  29, 255),   # dark crimson peak
    ],
}

_heatmap_png_cache = {}   # keyed by palette name


def _render_heatmap_png(palette: str = "night") -> bytes:
    import numpy as np
    from scipy.ndimage import gaussian_filter
    from PIL import Image

    # Higher resolution for a crisper look
    W, H = 900, 600

    lat_min = HEATMAP_BOUNDS["lat_min"]
    lat_max = HEATMAP_BOUNDS["lat_max"]
    lng_min = HEATMAP_BOUNDS["lng_min"]
    lng_max = HEATMAP_BOUNDS["lng_max"]

    # Evaluate get_area_danger on the full grid — same function as /api/safety
    # so colours correspond exactly to scores.
    grid = np.zeros((H, W), dtype=np.float32)
    for row in range(H):
        lat = lat_max - (row / H) * (lat_max - lat_min)
        for col in range(W):
            lng = lng_min + (col / W) * (lng_max - lng_min)
            grid[row, col] = get_area_danger(lat, lng)

    # Minimal blur — just enough to soften pixel-grid edges, not to spread blobs.
    grid = gaussian_filter(grid, sigma=0.8)
    grid = np.clip(grid, 0.0, 1.0)

    # Build 256-entry LUT from CMAP control points
    CMAP = CMAPS.get(palette, CMAPS["night"])

    def interp_color(v):
        for i in range(len(CMAP) - 1):
            v0, r0, g0, b0, a0 = CMAP[i]
            v1, r1, g1, b1, a1 = CMAP[i + 1]
            if v0 <= v <= v1:
                t = (v - v0) / (v1 - v0)
                # Smooth-step easing so colour transitions feel organic
                t = t * t * (3 - 2 * t)
                return (
                    int(r0 + t * (r1 - r0)),
                    int(g0 + t * (g1 - g0)),
                    int(b0 + t * (b1 - b0)),
                    int(a0 + t * (a1 - a0)),
                )
        r, g, b, a = CMAP[-1][1], CMAP[-1][2], CMAP[-1][3], CMAP[-1][4]
        return (r, g, b, a)

    lut = [interp_color(i / 255) for i in range(256)]
    lut_r = bytes(c[0] for c in lut)
    lut_g = bytes(c[1] for c in lut)
    lut_b = bytes(c[2] for c in lut)
    lut_a = bytes(c[3] for c in lut)

    idx = (grid * 255).astype(np.uint8)
    r_ch = np.frombuffer(lut_r, dtype=np.uint8)[idx]
    g_ch = np.frombuffer(lut_g, dtype=np.uint8)[idx]
    b_ch = np.frombuffer(lut_b, dtype=np.uint8)[idx]
    a_ch = np.frombuffer(lut_a, dtype=np.uint8)[idx]

    rgba = np.stack([r_ch, g_ch, b_ch, a_ch], axis=-1)
    img  = Image.fromarray(rgba, mode="RGBA")

    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=True)
    return buf.getvalue()


@app.get("/api/heatmap/image")
def get_heatmap_image(palette: str = "night"):
    if palette not in CMAPS:
        palette = "night"
    if palette not in _heatmap_png_cache:
        _heatmap_png_cache[palette] = _render_heatmap_png(palette)
    return Response(content=_heatmap_png_cache[palette], media_type="image/png",
                    headers={"Cache-Control": "public, max-age=3600"})


@app.get("/api/heatmap/bounds")
def get_heatmap_bounds():
    return HEATMAP_BOUNDS


# Keep old /api/heatmap returning empty so frontend doesn't break during transition
@app.get("/api/heatmap")
def get_heatmap():
    return {"points": []}


# ---------------------------------------------------------------------------
# Map markers — police stations & safe spaces
# ---------------------------------------------------------------------------

POLICE_STATIONS = [
    {"name": "Brixton Police Station",         "lat": 51.4607, "lng": -0.1146},
    {"name": "Hackney Police Station",         "lat": 51.5443, "lng": -0.0557},
    {"name": "Peckham Police Station",         "lat": 51.4730, "lng": -0.0693},
    {"name": "Elephant & Castle Police",       "lat": 51.4953, "lng": -0.1007},
    {"name": "Kings Cross Police Station",     "lat": 51.5302, "lng": -0.1208},
    {"name": "Tottenham Police Station",       "lat": 51.5881, "lng": -0.0707},
    {"name": "Lewisham Police Station",        "lat": 51.4615, "lng": -0.0127},
    {"name": "Bethnal Green Police Station",   "lat": 51.5261, "lng": -0.0613},
    {"name": "Islington Police Station",       "lat": 51.5356, "lng": -0.1050},
    {"name": "Camden Police Station",          "lat": 51.5401, "lng": -0.1437},
    {"name": "Hammersmith Police Station",     "lat": 51.4927, "lng": -0.2247},
    {"name": "Wandsworth Police Station",      "lat": 51.4554, "lng": -0.1916},
    {"name": "Southwark Police Station",       "lat": 51.5027, "lng": -0.0830},
    {"name": "Tower Hamlets Police Station",   "lat": 51.5143, "lng": -0.0407},
    {"name": "Croydon Police Station",         "lat": 51.3741, "lng": -0.1013},
    {"name": "Stratford Police Station",       "lat": 51.5420, "lng": -0.0042},
    {"name": "Woolwich Police Station",        "lat": 51.4906, "lng":  0.0683},
    {"name": "Barking Police Station",         "lat": 51.5390, "lng":  0.0786},
    {"name": "Walthamstow Police Station",     "lat": 51.5863, "lng": -0.0178},
    {"name": "Haringey Police Station",        "lat": 51.5969, "lng": -0.1099},
    {"name": "Shepherd's Bush Police Station", "lat": 51.5036, "lng": -0.2192},
    {"name": "Ilford Police Station",          "lat": 51.5587, "lng":  0.0711},
    {"name": "New Cross Police Station",       "lat": 51.4777, "lng": -0.0393},
    {"name": "Harlesden Police Station",       "lat": 51.5355, "lng": -0.2476},
]

SAFE_SPACES = [
    # Hospitals
    {"name": "King's College Hospital",        "lat": 51.4680, "lng": -0.0932, "type": "hospital"},
    {"name": "St Thomas' Hospital",            "lat": 51.4988, "lng": -0.1188, "type": "hospital"},
    {"name": "Royal London Hospital",          "lat": 51.5186, "lng": -0.0596, "type": "hospital"},
    {"name": "University College Hospital",    "lat": 51.5246, "lng": -0.1340, "type": "hospital"},
    {"name": "Homerton Hospital",              "lat": 51.5497, "lng": -0.0444, "type": "hospital"},
    {"name": "Lewisham Hospital",              "lat": 51.4619, "lng": -0.0175, "type": "hospital"},
    {"name": "St George's Hospital",           "lat": 51.4272, "lng": -0.1748, "type": "hospital"},
    {"name": "Croydon University Hospital",    "lat": 51.3869, "lng": -0.1094, "type": "hospital"},
    # 24h tube/overground stations (busy, CCTV, staff)
    {"name": "Liverpool Street Station",       "lat": 51.5178, "lng": -0.0823, "type": "transport_hub"},
    {"name": "London Bridge Station",          "lat": 51.5051, "lng": -0.0864, "type": "transport_hub"},
    {"name": "Victoria Station",               "lat": 51.4952, "lng": -0.1441, "type": "transport_hub"},
    {"name": "Paddington Station",             "lat": 51.5154, "lng": -0.1755, "type": "transport_hub"},
    {"name": "Waterloo Station",               "lat": 51.5031, "lng": -0.1132, "type": "transport_hub"},
    {"name": "Canary Wharf Station",           "lat": 51.5051, "lng": -0.0209, "type": "transport_hub"},
    {"name": "Stratford Station",              "lat": 51.5415, "lng": -0.0042, "type": "transport_hub"},
    # Community safe spaces
    {"name": "Brixton Recreation Centre",      "lat": 51.4625, "lng": -0.1143, "type": "community"},
    {"name": "Hackney Community Centre",       "lat": 51.5451, "lng": -0.0559, "type": "community"},
    {"name": "Peckham Library",                "lat": 51.4738, "lng": -0.0692, "type": "community"},
    {"name": "Camden Centre",                  "lat": 51.5366, "lng": -0.1243, "type": "community"},
    {"name": "Southwark Council Offices",      "lat": 51.5029, "lng": -0.0905, "type": "community"},
    {"name": "Lewisham Gateway",               "lat": 51.4640, "lng": -0.0140, "type": "community"},
    {"name": "Stratford Library",              "lat": 51.5413, "lng": -0.0035, "type": "community"},
    {"name": "Croydon Central Library",        "lat": 51.3754, "lng": -0.0971, "type": "community"},
]


@app.get("/api/markers")
def get_markers():
    return {
        "police": POLICE_STATIONS,
        "safe_spaces": SAFE_SPACES,
    }


# ---------------------------------------------------------------------------
# Routing
# ---------------------------------------------------------------------------

OSRM_BASE = "http://router.project-osrm.org/route/v1"

OSRM_PROFILES = {"foot": "walking", "bike": "cycling", "car": "driving", "bus": "driving"}
EXPOSURE = {"foot": 1.00, "bike": 0.80, "car": 0.55, "bus": 0.40}
MODE_LABELS = {"foot": "Walking", "bike": "Cycling", "car": "Driving", "bus": "Bus / Transit"}
MODE_ICONS  = {"foot": "🚶", "bike": "🚲", "car": "🚗", "bus": "🚌"}


def _score_point(lat: float, lng: float, hour: int) -> int:
    danger = get_area_danger(lat, lng)
    time_mod = get_time_modifier(hour)
    return max(4, min(99, round((1 - max(0.01, min(0.99, danger + time_mod))) * 100)))


def _effective_safety(base: float, mode: str) -> int:
    exp = EXPOSURE.get(mode, 1.0)
    return min(99, round(base + (100 - base) * (1 - exp)))


def _risk_label(score: int) -> str:
    if score >= 75: return "Low"
    if score >= 50: return "Medium"
    if score >= 30: return "High"
    return "Critical"


@app.get("/api/route")
def get_route(
    from_lat: float, from_lng: float,
    to_lat: float, to_lng: float,
    mode: str = "foot",
    hour: int = -1,
):
    if hour == -1:
        hour = datetime.now(timezone.utc).hour

    profile = OSRM_PROFILES.get(mode, "walking")
    routes_raw = []

    try:
        url = (
            f"{OSRM_BASE}/{profile}/"
            f"{from_lng},{from_lat};{to_lng},{to_lat}"
            f"?overview=full&geometries=geojson&alternatives=true&steps=false"
        )
        with urllib.request.urlopen(url, timeout=8) as resp:
            osrm = json.loads(resp.read())
        if osrm.get("code") != "Ok":
            raise ValueError("OSRM returned non-Ok code")
        for r in osrm["routes"][:2]:
            routes_raw.append({
                "coords": r["geometry"]["coordinates"],
                "duration_s": round(r["duration"]),
                "distance_m": round(r["distance"]),
            })
    except Exception:
        n = 12
        coords = [
            [from_lng + (to_lng - from_lng) * i / n,
             from_lat + (to_lat - from_lat) * i / n]
            for i in range(n + 1)
        ]
        dist_m = round(haversine(from_lat, from_lng, to_lat, to_lng) * 1000)
        speeds = {"foot": 5, "bike": 15, "car": 30, "bus": 20}
        routes_raw = [{"coords": coords,
                       "duration_s": round(dist_m / (speeds.get(mode, 5) * 1000 / 3600)),
                       "distance_m": dist_m}]

    results = []
    for i, raw in enumerate(routes_raw):
        coords = raw["coords"]
        n_samples = min(25, max(5, len(coords) // 4))
        step = max(1, len(coords) // n_samples)
        samples = []
        for j in range(0, len(coords), step):
            lng_s, lat_s = coords[j]
            samples.append({"lat": lat_s, "lng": lng_s, "score": _score_point(lat_s, lng_s, hour)})
        if coords:
            lng_s, lat_s = coords[-1]
            samples.append({"lat": lat_s, "lng": lng_s, "score": _score_point(lat_s, lng_s, hour)})

        avg_safety = sum(s["score"] for s in samples) / len(samples)
        eff = _effective_safety(avg_safety, mode)
        results.append({
            "id": i, "geometry": coords,
            "duration_s": raw["duration_s"], "distance_m": raw["distance_m"],
            "avg_safety": round(avg_safety), "effective_safety": eff,
            "risk_level": _risk_label(eff), "safety_samples": samples, "is_recommended": False,
        })

    results.sort(key=lambda r: r["effective_safety"], reverse=True)
    results[0]["is_recommended"] = True

    base = results[0]["avg_safety"]
    mode_comparison = sorted(
        [{"mode": m, "label": MODE_LABELS[m], "icon": MODE_ICONS[m],
          "effective_safety": _effective_safety(base, m),
          "risk_level": _risk_label(_effective_safety(base, m))}
         for m in ["foot", "bike", "car", "bus"]],
        key=lambda x: x["effective_safety"], reverse=True,
    )

    return {
        "routes": results,
        "mode_comparison": mode_comparison,
        "recommended_mode": mode_comparison[0]["mode"],
        "current_mode": mode,
    }
