from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import math
import random
import json
from datetime import datetime, timezone

# ---------------------------------------------------------------------------
# Database — SQLite via SQLAlchemy, with in-memory fallback if not installed
# ---------------------------------------------------------------------------

_DB_AVAILABLE = False
_in_memory_posts: list[dict] = []
_next_id = 1

try:
    from sqlalchemy import create_engine, Column, Integer, Float, String, DateTime, Text
    from sqlalchemy.orm import sessionmaker
    try:
        from sqlalchemy.orm import declarative_base
    except ImportError:
        from sqlalchemy.ext.declarative import declarative_base

    _engine = create_engine("sqlite:///./streetsense.db", connect_args={"check_same_thread": False})
    _Session = sessionmaker(autocommit=False, autoflush=False, bind=_engine)
    _Base = declarative_base()

    class PostRecord(_Base):
        __tablename__ = "posts"
        id = Column(Integer, primary_key=True, index=True)
        lat = Column(Float, nullable=False)
        lng = Column(Float, nullable=False)
        username = Column(String(80), nullable=False)
        content = Column(Text, nullable=False)
        sentiment = Column(String(20), nullable=False)
        impact = Column(Integer, nullable=False)
        tags = Column(Text, default="[]")
        platform = Column(String(30), default="streetsense")
        created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    _Base.metadata.create_all(bind=_engine)
    _DB_AVAILABLE = True
    print("✓ SQLite database ready")
except Exception as e:
    print(f"⚠ SQLAlchemy not available ({e}), using in-memory storage")


def _db_save_post(lat, lng, username, content, sentiment, impact, tags) -> int:
    global _next_id
    if _DB_AVAILABLE:
        db = _Session()
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
    if _DB_AVAILABLE:
        db = _Session()
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


app = FastAPI(title="StreetSense API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# London crime hotspots (real-ish areas with higher crime)
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

# Safer areas (lower crime)
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
    a = math.sin(dlat / 2) ** 2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon / 2) ** 2
    return R * 2 * math.asin(math.sqrt(a))


def get_area_danger(lat: float, lng: float) -> float:
    """0.0 = very safe, 1.0 = very dangerous"""
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

    # Add deterministic noise based on location
    noise = (math.sin(lat * 317.3) * math.cos(lng * 211.7)) * 0.08
    return max(0.02, min(0.98, raw + noise + 0.25))


def get_time_modifier(hour: int) -> float:
    if 7 <= hour < 19:
        return -0.15  # Safer during day
    elif 19 <= hour < 21:
        return 0.0
    elif 21 <= hour < 23:
        return 0.10
    else:
        return 0.28  # Late night / early morning


@app.get("/api/safety")
def get_safety(lat: float, lng: float, hour: int = -1):
    if hour == -1:
        hour = datetime.now().hour

    danger = get_area_danger(lat, lng)
    time_mod = get_time_modifier(hour)
    final_danger = max(0.01, min(0.99, danger + time_mod))

    score = max(4, min(99, round((1 - final_danger) * 100)))

    # Lighting
    if 7 <= hour < 20:
        lighting = "Good"
    elif 6 <= hour < 7 or 20 <= hour < 22:
        lighting = "Fair"
    else:
        lighting = "Poor"

    # Foot traffic
    if hour in range(8, 10) or hour in range(17, 20):
        foot_traffic = "High"
    elif hour in range(10, 17) or hour in range(20, 22):
        foot_traffic = "Medium"
    else:
        foot_traffic = "Low"

    # Incidents (seeded to be deterministic per location)
    rng = random.Random(int(lat * 1000) + int(lng * 1000))
    incidents_30d = max(0, round(final_danger * 60 + rng.gauss(0, 4)))
    response_time = max(4, round(5 + final_danger * 15))

    # CCTV
    if danger < 0.35:
        cctv = "Low"
    elif danger < 0.65:
        cctv = "Medium"
    else:
        cctv = "High"

    # Risk label
    if score >= 75:
        risk = "Low"
    elif score >= 50:
        risk = "Medium"
    elif score >= 30:
        risk = "High"
    else:
        risk = "Critical"

    summaries = {
        "Low": f"This area is generally safe right now. {foot_traffic} foot traffic and {lighting.lower()} lighting make it a comfortable route.",
        "Medium": f"Some caution advised. {incidents_30d} incidents reported nearby in the past 30 days. Lighting is {lighting.lower()}.",
        "High": f"Elevated risk detected. Avoid isolated paths and stay in well-lit areas. Consider travelling with others.",
        "Critical": f"High risk area at this hour. Multiple incidents reported. Avoid if possible — use a main road or alternative route.",
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
    }


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

# Semantic signal keywords for analysis
SEMANTIC_SIGNALS = {
    "incident": ["fight", "snatched", "robbery", "attack", "witnessed", "assault", "stabbing", "trouble"],
    "police": ["police", "patrol", "officers", "police tape", "police presence"],
    "poor_lighting": ["dark", "unlit", "no lights", "poorly lit"],
    "good_lighting": ["well-lit", "street lights", "bright", "lit up"],
    "crowded": ["loads of people", "busy", "families", "lively", "crowd", "lots of people"],
    "empty": ["quiet", "empty", "nobody around", "not many people", "deserted"],
    "warning": ["avoid", "unsafe", "be careful", "stay safe", "different route", "not safe"],
    "positive": ["safe", "lovely", "comfortable", "fine", "great", "secure", "recommend"],
    "threat": ["following", "aggressive", "sketchy", "group", "scary"],
}


def extract_semantic_tags(text: str, sentiment: str) -> list[str]:
    text_lower = text.lower()
    tags = []

    for signal, keywords in SEMANTIC_SIGNALS.items():
        if any(kw in text_lower for kw in keywords):
            if signal == "incident":
                tags.append("incident reported")
            elif signal == "police":
                tags.append("police activity")
            elif signal == "poor_lighting":
                tags.append("poor lighting")
            elif signal == "good_lighting":
                tags.append("good lighting")
            elif signal == "crowded":
                tags.append("active area")
            elif signal == "empty":
                tags.append("quiet area")
            elif signal == "warning":
                tags.append("avoid advised")
            elif signal == "positive" and sentiment == "positive":
                tags.append("feels safe")
            elif signal == "threat":
                tags.append("threatening behaviour")

    return tags[:2]


# ---------------------------------------------------------------------------
# Sentiment analysis for user-submitted posts
# ---------------------------------------------------------------------------

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
    """Returns (sentiment, impact) for a user-submitted post."""
    t = text.lower()
    neg = sum(1 for kw in NEGATIVE_KEYWORDS if kw in t)
    pos = sum(1 for kw in POSITIVE_KEYWORDS if kw in t)
    if neg > pos:
        return "negative", -14
    if pos > neg:
        return "positive", 10
    return "neutral", -2


# ---------------------------------------------------------------------------
# Request schema
# ---------------------------------------------------------------------------

class PostCreate(BaseModel):
    lat: float
    lng: float
    username: str
    content: str


# ---------------------------------------------------------------------------
# Posts endpoints
# ---------------------------------------------------------------------------

def _generate_mock_posts(lat: float, lng: float, hour: int) -> list[dict]:
    danger = get_area_danger(lat, lng)
    time_mod = get_time_modifier(hour)
    final_danger = max(0.01, min(0.99, danger + time_mod))

    rng = random.Random(int(lat * 10000) + int(lng * 10000) + hour // 3)
    posts = []
    num_posts = rng.randint(3, 5)

    for i in range(num_posts):
        roll = rng.random()
        neg_threshold = final_danger * 0.68
        neu_threshold = neg_threshold + 0.18

        if roll < neg_threshold:
            template, base_impact = rng.choice(NEGATIVE_POSTS)
            sentiment = "negative"
        elif roll < neu_threshold:
            template, base_impact = rng.choice(NEUTRAL_POSTS)
            sentiment = "neutral"
        else:
            template, base_impact = rng.choice(POSITIVE_POSTS)
            sentiment = "positive"

        impact = base_impact + rng.randint(-2, 2)
        posts.append({
            "id": f"mock_{i}",
            "username": rng.choice(USERNAMES),
            "content": template,
            "minutes_ago": rng.randint(4, 240),
            "sentiment": sentiment,
            "impact": impact,
            "tags": extract_semantic_tags(template, sentiment),
            "platform": rng.choice(["twitter", "reddit", "nextdoor", "twitter", "twitter"]),
            "is_user_post": False,
        })

    return posts


@app.post("/api/posts")
def create_post(body: PostCreate):
    username = body.username.strip() or "anonymous"
    content = body.content.strip()
    sentiment, impact = analyze_user_sentiment(content)
    tags = extract_semantic_tags(content, sentiment)
    pid = _db_save_post(body.lat, body.lng, username, content, sentiment, impact, tags)
    return {
        "id": f"user_{pid}",
        "username": username,
        "content": content,
        "minutes_ago": 0,
        "sentiment": sentiment,
        "impact": impact,
        "tags": tags,
        "platform": "streetsense",
        "is_user_post": True,
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


@app.get("/api/heatmap")
def get_heatmap():
    points = []
    rng = random.Random(42)

    # Dense clusters around hotspots
    for hlat, hlng, intensity in HOTSPOTS:
        count = int(intensity * 40)
        for _ in range(count):
            spread = rng.gauss(0, 0.008)
            spread2 = rng.gauss(0, 0.008)
            weight = max(0.1, intensity + rng.gauss(0, 0.15))
            points.append([hlat + spread, hlng + spread2, min(1.0, weight)])

    # Sparse background noise across London
    for _ in range(80):
        lat = rng.uniform(51.42, 51.58)
        lng = rng.uniform(-0.28, 0.02)
        weight = rng.uniform(0.05, 0.35)
        points.append([lat, lng, weight])

    return {"points": points}
