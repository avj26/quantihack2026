from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import asyncio
import math
import random
import json
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

HOTSPOTS = [
    (51.4613, -0.1156, 0.95),  # Brixton
    (51.5431, -0.0559, 0.90),  # Hackney
    (51.4958, -0.1002, 0.85),  # Elephant & Castle
    (51.5308, -0.1238, 0.80),  # Kings Cross
    (51.4740, -0.0551, 0.88),  # Peckham
    (51.5200, -0.0800, 0.75),  # Bethnal Green
    (51.5074, -0.0680, 0.78),  # Whitechapel
    (51.4893, -0.1774, 0.70),  # Shepherd's Bush
    (51.5588, -0.0744, 0.72),  # Tottenham
    (51.4816, -0.0072, 0.82),  # New Cross
]

SAFE_ZONES = [
    (51.5000, -0.1950, 0.05),  # Kensington
    (51.4613, -0.3037, 0.08),  # Richmond
    (51.4241, -0.2054, 0.06),  # Wimbledon
    (51.5565, -0.1783, 0.07),  # Hampstead
    (51.4862, -0.2408, 0.09),  # Barnes
]


def haversine(lat1, lon1, lat2, lon2):
    R = 6371
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (math.sin(dlat / 2) ** 2
         + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon / 2) ** 2)
    return R * 2 * math.asin(math.sqrt(a))


def get_area_danger(lat: float, lng: float) -> float:
    danger = 0.0
    total_weight = 0.0
    for hlat, hlng, intensity in HOTSPOTS:
        dist = haversine(lat, lng, hlat, hlng)
        weight = intensity * math.exp(-dist * 1.5)
        danger += weight
        total_weight += math.exp(-dist * 1.5)
    safe_pull = 0.0
    for slat, slng, intensity in SAFE_ZONES:
        dist = haversine(lat, lng, slat, slng)
        safe_pull += intensity * math.exp(-dist * 2.0)
    raw = (danger - safe_pull * 0.5) / max(total_weight, 0.1)
    noise = (math.sin(lat * 317.3) * math.cos(lng * 211.7)) * 0.08
    return max(0.02, min(0.98, raw + noise + 0.25))


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


def _heatmap_weight(lat, lng):
    """
    Gaussian kernel density for heatmap visualisation.
    Each hotspot contributes exp(-d² / 2σ²) so influence falls off
    smoothly and symmetrically — proper Gaussian interpolation.
    σ = 1.8 km  →  full influence within ~1 km, negligible beyond ~4 km.
    """
    SIGMA2 = 2 * 1.8 ** 2   # 2σ²

    danger = sum(
        intensity * math.exp(-(haversine(lat, lng, hlat, hlng) ** 2) / SIGMA2)
        for hlat, hlng, intensity in HOTSPOTS
    )
    safe_adj = sum(
        intensity * math.exp(-(haversine(lat, lng, slat, slng) ** 2) / (2 * 2.2 ** 2)) * 0.55
        for slat, slng, intensity in SAFE_ZONES
    )
    # Tiny deterministic noise breaks up perfectly circular rings
    noise = abs(math.sin(lat * 317.3) * math.cos(lng * 211.7)) * 0.025
    return max(0.0, danger - safe_adj + noise)


_heatmap_cache = None

@app.get("/api/heatmap")
def get_heatmap():
    global _heatmap_cache
    if _heatmap_cache is not None:
        return {"points": _heatmap_cache}

    raw = []
    lat_min, lat_max = 51.35, 51.65
    lng_min, lng_max = -0.50, 0.20
    lat_step = 0.007   # ~780 m rows — matches radius without excessive accumulation
    lng_step = 0.011   # ~770 m cols

    lat = lat_min
    while lat <= lat_max:
        lng = lng_min
        while lng <= lng_max:
            raw.append((round(lat, 4), round(lng, 4), _heatmap_weight(lat, lng)))
            lng += lng_step
        lat += lat_step

    # Normalise so the full gradient (blue → red → yellow) is always used
    vals = [w for _, _, w in raw]
    lo, hi = min(vals), max(vals)
    span = hi - lo if hi != lo else 1.0
    points = [
        [lt, lg, round((w - lo) / span, 3)]
        for lt, lg, w in raw
    ]

    _heatmap_cache = points
    return {"points": points}


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
