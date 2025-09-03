# agent/ingest_history.py
from pathlib import Path
import pandas as pd
from similarity_memory import build_or_load_memory

ROOT = Path(__file__).resolve().parents[1]
DECISIONS = ROOT / "ui" / "decisions.csv"

def _read_decisions_tolerant(path: Path) -> pd.DataFrame:
    if not path.exists() or path.stat().st_size == 0:
        return pd.DataFrame()
    try:
        return pd.read_csv(path, encoding="utf-8")
    except Exception:
        return pd.read_csv(path, engine="python", on_bad_lines="skip", encoding="utf-8")

if __name__ == "__main__":
    print(f"Loading decisions from: {DECISIONS}")
    df = _read_decisions_tolerant(DECISIONS)
    print(f"Loaded {len(df)} rows (tolerant read).")
    _ = build_or_load_memory(DECISIONS)
    print("Memory store updated ✓")
