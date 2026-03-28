"""
StreetSense — Multi-task fine-tuner
Trains a single DistilBERT model with two heads:
  • Category head  — 6-class softmax (CrossEntropyLoss)
  • Severity head  — scalar sigmoid regression (MSELoss)

Run:
    cd backend
    python ml/data_generator.py          # generate training data first
    python ml/train.py                   # fine-tune and save

Output: ml/models/streetsense_classifier/
"""

import json, os, time
from pathlib import Path
from collections import Counter

import torch
import torch.nn as nn
from torch.utils.data import Dataset, DataLoader, random_split
from torch.optim import AdamW
from torch.optim.lr_scheduler import LinearLR

from transformers import DistilBertTokenizerFast, DistilBertModel

# ── Config ────────────────────────────────────────────────────────────────────

DATA_PATH   = Path("ml/data/training_data.json")
MODEL_DIR   = Path("ml/models/streetsense_classifier")
BASE_MODEL  = "distilbert-base-uncased"

CATEGORIES  = ["crime", "antisocial", "weather", "road_hazard", "safe", "neutral"]
CAT2IDX     = {c: i for i, c in enumerate(CATEGORIES)}

MAX_LEN     = 96      # social posts are short — 96 tokens is plenty
BATCH_SIZE  = 16
EPOCHS      = 6
LR          = 2e-5
VAL_SPLIT   = 0.15
SEV_WEIGHT  = 2.0     # upweight severity loss relative to category loss

DEVICE = "cuda" if torch.cuda.is_available() else "cpu"


# ── Dataset ───────────────────────────────────────────────────────────────────

class PostDataset(Dataset):
    def __init__(self, records, tokenizer):
        self.records   = records
        self.tokenizer = tokenizer

    def __len__(self):
        return len(self.records)

    def __getitem__(self, idx):
        r = self.records[idx]
        enc = self.tokenizer(
            r["text"],
            max_length=MAX_LEN,
            padding="max_length",
            truncation=True,
            return_tensors="pt",
        )
        return {
            "input_ids":      enc["input_ids"].squeeze(0),
            "attention_mask": enc["attention_mask"].squeeze(0),
            "category":       torch.tensor(CAT2IDX[r["category"]], dtype=torch.long),
            "severity":       torch.tensor(r["severity"], dtype=torch.float),
        }


# ── Model ─────────────────────────────────────────────────────────────────────

class StreetSenseModel(nn.Module):
    def __init__(self, n_categories=len(CATEGORIES)):
        super().__init__()
        self.bert = DistilBertModel.from_pretrained(BASE_MODEL)
        h = self.bert.config.hidden_size   # 768

        self.category_head = nn.Sequential(
            nn.Linear(h, 128),
            nn.GELU(),
            nn.Dropout(0.2),
            nn.Linear(128, n_categories),
        )
        self.severity_head = nn.Sequential(
            nn.Linear(h, 64),
            nn.GELU(),
            nn.Dropout(0.1),
            nn.Linear(64, 1),
            nn.Sigmoid(),
        )

    def forward(self, input_ids, attention_mask):
        # CLS token representation
        cls = self.bert(input_ids=input_ids, attention_mask=attention_mask)\
                   .last_hidden_state[:, 0]
        return self.category_head(cls), self.severity_head(cls).squeeze(-1)


# ── Training loop ─────────────────────────────────────────────────────────────

def train():
    print(f"Device: {DEVICE}")

    # Load data
    if not DATA_PATH.exists():
        print("Training data not found — running generator first...")
        import sys; sys.path.insert(0, str(Path(__file__).parent.parent))
        from ml.data_generator import generate
        generate()

    records = json.loads(DATA_PATH.read_text())
    print(f"Loaded {len(records)} examples")
    cat_counts = Counter(r["category"] for r in records)
    for cat, n in sorted(cat_counts.items()):
        print(f"  {cat:15s} {n}")

    # Tokeniser
    tokenizer = DistilBertTokenizerFast.from_pretrained(BASE_MODEL)
    dataset   = PostDataset(records, tokenizer)

    # Train / val split
    n_val  = max(1, int(len(dataset) * VAL_SPLIT))
    n_train = len(dataset) - n_val
    train_ds, val_ds = random_split(
        dataset, [n_train, n_val],
        generator=torch.Generator().manual_seed(42),
    )
    train_loader = DataLoader(train_ds, batch_size=BATCH_SIZE, shuffle=True)
    val_loader   = DataLoader(val_ds,   batch_size=BATCH_SIZE)
    print(f"Train: {n_train}  Val: {n_val}")

    # Model + optimiser
    model = StreetSenseModel().to(DEVICE)
    optimiser = AdamW(model.parameters(), lr=LR, weight_decay=0.01)
    total_steps = EPOCHS * len(train_loader)
    scheduler = LinearLR(optimiser, start_factor=1.0, end_factor=0.1,
                         total_iters=total_steps)

    ce_loss  = nn.CrossEntropyLoss()
    mse_loss = nn.MSELoss()

    best_val_loss = float("inf")

    for epoch in range(1, EPOCHS + 1):
        # ── Train ────────────────────────────────────────────────────────
        model.train()
        t0 = time.time()
        train_loss = 0.0

        for batch in train_loader:
            ids   = batch["input_ids"].to(DEVICE)
            mask  = batch["attention_mask"].to(DEVICE)
            cats  = batch["category"].to(DEVICE)
            sevs  = batch["severity"].to(DEVICE)

            cat_logits, sev_pred = model(ids, mask)
            loss = ce_loss(cat_logits, cats) + SEV_WEIGHT * mse_loss(sev_pred, sevs)

            optimiser.zero_grad()
            loss.backward()
            nn.utils.clip_grad_norm_(model.parameters(), 1.0)
            optimiser.step()
            scheduler.step()
            train_loss += loss.item()

        train_loss /= len(train_loader)

        # ── Validate ─────────────────────────────────────────────────────
        model.eval()
        val_loss = 0.0
        correct  = 0
        total    = 0
        sev_mae  = 0.0

        with torch.no_grad():
            for batch in val_loader:
                ids   = batch["input_ids"].to(DEVICE)
                mask  = batch["attention_mask"].to(DEVICE)
                cats  = batch["category"].to(DEVICE)
                sevs  = batch["severity"].to(DEVICE)

                cat_logits, sev_pred = model(ids, mask)
                loss = ce_loss(cat_logits, cats) + SEV_WEIGHT * mse_loss(sev_pred, sevs)
                val_loss += loss.item()

                preds    = cat_logits.argmax(dim=-1)
                correct += (preds == cats).sum().item()
                total   += cats.size(0)
                sev_mae += (sev_pred - sevs).abs().sum().item()

        val_loss /= len(val_loader)
        acc = correct / total * 100
        mae = sev_mae / total

        elapsed = time.time() - t0
        print(
            f"Epoch {epoch}/{EPOCHS} | "
            f"train {train_loss:.4f} | val {val_loss:.4f} | "
            f"cat acc {acc:.1f}% | sev MAE {mae:.3f} | "
            f"{elapsed:.0f}s"
        )

        if val_loss < best_val_loss:
            best_val_loss = val_loss
            _save(model, tokenizer)
            print(f"  ✓ Saved best model (val_loss={val_loss:.4f})")

    print(f"\nDone. Best val loss: {best_val_loss:.4f}")
    print(f"Model saved → {MODEL_DIR}")


def _save(model, tokenizer):
    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    # Save tokeniser
    tokenizer.save_pretrained(MODEL_DIR)
    # Save model weights + config
    torch.save(model.state_dict(), MODEL_DIR / "model_weights.pt")
    config = {
        "base_model":  BASE_MODEL,
        "categories":  CATEGORIES,
        "max_len":     MAX_LEN,
        "hidden_size": model.bert.config.hidden_size,
    }
    (MODEL_DIR / "config.json").write_text(json.dumps(config, indent=2))


if __name__ == "__main__":
    train()
