"""
StreetSense — Inference module
Loads the fine-tuned StreetSense model and exposes two clean functions:

    classify(text)  →  {
        "category":   "crime",       # one of CATEGORIES
        "severity":   0.87,          # float 0.0–1.0
        "confidence": 0.94,          # softmax confidence on category
        "label":      "Critical",    # human-readable severity bucket
    }

Falls back to the keyword heuristic if the model hasn't been trained yet,
so the API always returns a valid response.
"""

from __future__ import annotations
import json, logging
from pathlib import Path

log = logging.getLogger("streetsense.classifiers")

CATEGORIES = ["crime", "antisocial", "weather", "road_hazard", "safe", "neutral"]


def _model_candidates() -> list[Path]:
    base = Path(__file__).resolve()
    return [
        base.parent / "models" / "streetsense_classifier",          # backend/ml/models/...
        base.parents[2] / "ml" / "models" / "streetsense_classifier",  # workspace/ml/models/...
        Path.cwd() / "ml" / "models" / "streetsense_classifier",   # when running from repo root
    ]


def _resolve_model_dir() -> Path | None:
    required = ["config.json", "model_weights.pt"]
    for path in _model_candidates():
        if path.exists() and all((path / name).exists() for name in required):
            return path
    return None

SEVERITY_LABELS = [
    (0.80, "Critical"),
    (0.55, "High"),
    (0.30, "Moderate"),
    (0.10, "Low"),
    (0.00, "Safe"),
]

def _severity_label(score: float) -> str:
    for threshold, label in SEVERITY_LABELS:
        if score >= threshold:
            return label
    return "Safe"


# ── Lazy model loader ─────────────────────────────────────────────────────────

_model     = None
_tokenizer = None
_config    = None
_device    = None
_model_dir = None


def _load():
    global _model, _tokenizer, _config, _device, _model_dir

    _model_dir = _resolve_model_dir()
    if not _model_dir:
        log.warning("[Classifier] No trained model found in candidates %s — using fallback", _model_candidates())
        return False

    try:
        import torch
        from transformers import DistilBertTokenizerFast, DistilBertModel
        import torch.nn as nn

        _device = "cuda" if torch.cuda.is_available() else "cpu"
        _config = json.loads((_model_dir / "config.json").read_text())

        # Rebuild model architecture
        class _StreetSenseModel(nn.Module):
            def __init__(self):
                super().__init__()
                self.bert = DistilBertModel.from_pretrained(_config["base_model"])
                h = _config["hidden_size"]
                n = len(_config["categories"])
                self.category_head = nn.Sequential(
                    nn.Linear(h, 128), nn.GELU(), nn.Dropout(0.2), nn.Linear(128, n)
                )
                self.severity_head = nn.Sequential(
                    nn.Linear(h, 64), nn.GELU(), nn.Dropout(0.1),
                    nn.Linear(64, 1), nn.Sigmoid()
                )

            def forward(self, input_ids, attention_mask):
                cls = self.bert(input_ids=input_ids, attention_mask=attention_mask)\
                           .last_hidden_state[:, 0]
                return self.category_head(cls), self.severity_head(cls).squeeze(-1)

        _model = _StreetSenseModel().to(_device)
        _model.load_state_dict(
            torch.load(_model_dir / "model_weights.pt", map_location=_device)
        )
        _model.eval()

        _tokenizer = DistilBertTokenizerFast.from_pretrained(str(_model_dir))

        log.info("[Classifier] Model loaded from %s (device=%s)", _model_dir, _device)
        return True

    except Exception as exc:
        log.warning("[Classifier] Load failed: %s — using fallback", exc)
        _model = None
        return False


_load_attempted = False

def _ensure_loaded() -> bool:
    global _load_attempted
    if not _load_attempted:
        _load_attempted = True
        return _load()
    return _model is not None


# ── Keyword fallback ──────────────────────────────────────────────────────────

_KEYWORD_RULES = [
    ("crime",       ["stabbed", "mugged", "robbed", "robbery", "assault", "theft",
                     "knife", "gun", "attack", "burglary", "pickpocket", "snatched",
                     "arrested", "police tape", "crime scene"]),
    ("antisocial",  ["threatening", "intimidating", "aggressive", "followed", "gang",
                     "harassing", "harassment", "antisocial", "drunk group",
                     "shouting", "menacing"]),
    ("weather",     ["rain", "fog", "ice", "snow", "flood", "thunder", "lightning",
                     "slippery", "icy", "wind", "storm", "drizzle", "visibility"]),
    ("road_hazard", ["pothole", "unlit", "no lights", "dark", "broken pavement",
                     "poor lighting", "street light", "road surface", "debris",
                     "scaffolding", "closed road"]),
    ("safe",        ["safe", "lovely", "comfortable", "police patrol", "well lit",
                     "families", "secure", "cctv", "recommend"]),
]

_NEG = ["unsafe", "avoid", "scared", "threatening", "dangerous", "crime",
        "mugged", "stabbed", "robbery", "attacked", "assault"]
_POS = ["safe", "lovely", "fine", "great", "recommend", "quiet", "peaceful",
        "nice", "friendly", "comfortable"]


def _fallback(text: str) -> dict:
    t = text.lower()

    # Category
    scores = {}
    for cat, keywords in _KEYWORD_RULES:
        scores[cat] = sum(1 for kw in keywords if kw in t)
    best_cat = max(scores, key=scores.get)
    if scores[best_cat] == 0:
        best_cat = "neutral"

    # Severity
    neg = sum(1 for w in _NEG if w in t)
    pos = sum(1 for w in _POS if w in t)
    if best_cat == "safe":
        severity = round(max(0.02, 0.08 - pos * 0.01), 3)
    elif best_cat == "crime":
        severity = round(min(0.98, 0.65 + neg * 0.06), 3)
    elif best_cat == "antisocial":
        severity = round(min(0.70, 0.45 + neg * 0.05), 3)
    elif best_cat == "weather":
        severity = round(min(0.55, 0.25 + neg * 0.06), 3)
    elif best_cat == "road_hazard":
        severity = round(min(0.50, 0.28 + neg * 0.05), 3)
    else:
        severity = round(min(0.30, 0.12 + neg * 0.04), 3)

    return {
        "category":   best_cat,
        "severity":   severity,
        "confidence": None,   # no confidence for heuristic
        "label":      _severity_label(severity),
        "source":     "heuristic",
    }


# ── Public API ────────────────────────────────────────────────────────────────

def classify(text: str) -> dict:
    """
    Classify a social media post.

    Returns:
        category   — one of: crime | antisocial | weather | road_hazard | safe | neutral
        severity   — float 0.0–1.0  (1.0 = most severe)
        confidence — softmax probability on category (None if heuristic)
        label      — human-readable severity (Critical / High / Moderate / Low / Safe)
        source     — "model" or "heuristic"
    """
    if not _ensure_loaded():
        return _fallback(text)

    try:
        import torch
        import torch.nn.functional as F

        enc = _tokenizer(
            text,
            max_length=_config["max_len"],
            padding="max_length",
            truncation=True,
            return_tensors="pt",
        )
        ids  = enc["input_ids"].to(_device)
        mask = enc["attention_mask"].to(_device)

        with torch.no_grad():
            cat_logits, sev_pred = _model(ids, mask)

        probs      = F.softmax(cat_logits, dim=-1).squeeze(0)
        cat_idx    = probs.argmax().item()
        confidence = round(probs[cat_idx].item(), 4)
        category   = _config["categories"][cat_idx]
        severity   = round(sev_pred.item(), 4)

        return {
            "category":   category,
            "severity":   severity,
            "confidence": confidence,
            "label":      _severity_label(severity),
            "source":     "model",
        }

    except Exception as exc:
        log.warning("[Classifier] Inference error: %s — using fallback", exc)
        return _fallback(text)


def classify_batch(texts: list[str]) -> list[dict]:
    """Classify multiple posts at once (more efficient on GPU)."""
    if not _ensure_loaded():
        return [_fallback(t) for t in texts]

    try:
        import torch
        import torch.nn.functional as F

        enc = _tokenizer(
            texts,
            max_length=_config["max_len"],
            padding=True,
            truncation=True,
            return_tensors="pt",
        )
        ids  = enc["input_ids"].to(_device)
        mask = enc["attention_mask"].to(_device)

        with torch.no_grad():
            cat_logits, sev_preds = _model(ids, mask)

        probs    = F.softmax(cat_logits, dim=-1)
        cat_idxs = probs.argmax(dim=-1).tolist()
        sevs     = sev_preds.tolist()
        cats_cfg = _config["categories"]

        results = []
        for i, (cat_idx, sev) in enumerate(zip(cat_idxs, sevs)):
            conf = round(probs[i, cat_idx].item(), 4)
            results.append({
                "category":   cats_cfg[cat_idx],
                "severity":   round(sev, 4),
                "confidence": conf,
                "label":      _severity_label(sev),
                "source":     "model",
            })
        return results

    except Exception as exc:
        log.warning("[Classifier] Batch inference error: %s — using fallback", exc)
        return [_fallback(t) for t in texts]
