"""
StreetSense — shared SQLAlchemy models.
Imported by both main.py and scraper.py.
"""
from datetime import datetime, timezone

DB_AVAILABLE = False
DBSession = None

try:
    from sqlalchemy import create_engine, Column, Integer, Float, String, DateTime, Text
    from sqlalchemy.orm import sessionmaker
    try:
        from sqlalchemy.orm import declarative_base
    except ImportError:
        from sqlalchemy.ext.declarative import declarative_base

    _engine = create_engine(
        "sqlite:///./streetsense.db",
        connect_args={"check_same_thread": False},
    )
    DBSession = sessionmaker(autocommit=False, autoflush=False, bind=_engine)
    Base = declarative_base()

    # ── User posts (existing) ──────────────────────────────────────────────
    class PostRecord(Base):
        __tablename__ = "posts"
        id         = Column(Integer, primary_key=True)
        lat        = Column(Float, nullable=False)
        lng        = Column(Float, nullable=False)
        username   = Column(String(80), nullable=False)
        content    = Column(Text, nullable=False)
        sentiment  = Column(String(20), nullable=False)
        impact     = Column(Integer, nullable=False)
        tags       = Column(Text, default="[]")
        platform   = Column(String(30), default="streetsense")
        created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    # ── Crime records (UK Police API) ──────────────────────────────────────
    class CrimeRecord(Base):
        __tablename__ = "crime_records"
        id         = Column(Integer, primary_key=True)
        crime_key  = Column(String(120), unique=True, index=True)  # dedup
        lat        = Column(Float, nullable=False)
        lng        = Column(Float, nullable=False)
        category   = Column(String(80))
        month      = Column(String(7))   # "2024-11"
        severity   = Column(Float, default=0.5)
        fetched_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    # ── Weather (Open-Meteo) ───────────────────────────────────────────────
    class WeatherRecord(Base):
        __tablename__ = "weather_records"
        id                = Column(Integer, primary_key=True)
        condition_code    = Column(Integer)
        condition_text    = Column(String(60))
        temp_c            = Column(Float)
        wind_kmh          = Column(Float)
        precipitation_mm  = Column(Float, default=0.0)
        safety_modifier   = Column(Float, default=0.0)  # negative = worse
        fetched_at        = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    # ── Road segments (OSM Overpass) ───────────────────────────────────────
    class RoadSegment(Base):
        __tablename__ = "road_segments"
        id              = Column(Integer, primary_key=True)
        osm_id          = Column(String(30), unique=True, index=True)
        lat             = Column(Float)
        lng             = Column(Float)
        highway         = Column(String(40))
        surface         = Column(String(40), default="unknown")
        lit             = Column(String(10), default="unknown")
        safety_modifier = Column(Float, default=0.0)
        fetched_at      = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    # ── Scraped social incidents (Reddit) ──────────────────────────────────
    class ScrapedIncident(Base):
        __tablename__ = "scraped_incidents"
        id           = Column(Integer, primary_key=True)
        incident_key = Column(String(120), unique=True, index=True)
        source       = Column(String(30))
        lat          = Column(Float, nullable=True)
        lng          = Column(Float, nullable=True)
        title        = Column(Text)
        content      = Column(Text, default="")
        url          = Column(String(300), default="")
        sentiment    = Column(String(20), default="negative")
        impact       = Column(Integer, default=-10)
        fetched_at   = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    Base.metadata.create_all(bind=_engine)
    DB_AVAILABLE = True
    print("[DB] SQLite ready → streetsense.db")

except Exception as exc:
    print(f"[DB] Not available ({exc}). In-memory fallback active.")

    class PostRecord: pass
    class CrimeRecord: pass
    class WeatherRecord: pass
    class RoadSegment: pass
    class ScrapedIncident: pass
