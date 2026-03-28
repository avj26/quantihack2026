# StreetSense

Real-time street safety ratings for London. Click any location to get a safety score, metrics, and heatmap overlay.

## Quick Start

**Backend** (terminal 1):
```bash
cd backend
pip install -r requirements.txt
uvicorn main:app --reload
```

**Frontend** (terminal 2):
```bash
cd frontend
npm install
npm run dev
```

Open http://localhost:3000

## Stack
- React + Vite + Leaflet (heatmap + dark map tiles)
- FastAPI (mocked safety data, time-aware + location-aware scoring)
- Nominatim for geocoding (no API key needed)
