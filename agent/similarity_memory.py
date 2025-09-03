# agent/similarity_memory.py
from __future__ import annotations

from pathlib import Path
import os
from typing import List
import pandas as pd
from langchain_ollama import OllamaEmbeddings
from langchain_community.vectorstores import Chroma

EMBED_MODEL = os.getenv("OLLAMA_EMBED_MODEL", "nomic-embed-text")
MEM_DIR = Path(__file__).parent / "memory_store"
COLLECTION_NAME = "loan_cases"

EXPECTED_COLS: List[str] = [
    "timestamp", "name", "age", "income", "employment_status",
    "credit_score", "loan_amount", "term_months", "interest_rate",
    "purpose", "decision", "reason", "used_tools", "raw_output",
]

def _as_text(row: pd.Series) -> str:
    return (
        f"Name: {row.get('name')}, Age: {row.get('age')}, "
        f"Income: {row.get('income')}, Employment: {row.get('employment_status')}, "
        f"Credit: {row.get('credit_score')}, Loan: {row.get('loan_amount')}, "
        f"Term: {row.get('term_months')} months, Rate: {row.get('interest_rate')}%, "
        f"Purpose: {row.get('purpose')}, Decision: {row.get('decision')}, "
        f"Reason: {row.get('reason')}"
    )

def _embedder() -> OllamaEmbeddings:
    return OllamaEmbeddings(model=EMBED_MODEL)

def _load_csv_safe(p: Path) -> pd.DataFrame:
    if not p.exists() or p.stat().st_size == 0:
        return pd.DataFrame(columns=EXPECTED_COLS)
    try:
        df = pd.read_csv(p, encoding="utf-8")
    except Exception:
        df = pd.read_csv(p, engine="python", on_bad_lines="skip", encoding="utf-8")
    for col in EXPECTED_COLS:
        if col not in df.columns:
            df[col] = None
    df = df[[c for c in EXPECTED_COLS]]
    df = df.dropna(how="all")
    return df

def _open_store(embed: OllamaEmbeddings) -> Chroma:
    MEM_DIR.mkdir(parents=True, exist_ok=True)
    return Chroma(collection_name=COLLECTION_NAME, embedding_function=embed, persist_directory=str(MEM_DIR))

def build_or_load_memory(decisions_csv: Path) -> Chroma:
    embed = _embedder()
    vs = _open_store(embed)
    df = _load_csv_safe(decisions_csv)
    if df.empty:
        return vs
    texts = [_as_text(r) for _, r in df.iterrows()]
    metadatas = df.to_dict(orient="records")
    try:
        vs.add_texts(texts=texts, metadatas=metadatas)
        vs.persist()
    except Exception:
        vs = Chroma.from_texts(
            texts=texts,
            embedding=embed,
            metadatas=metadatas,
            collection_name=COLLECTION_NAME,
            persist_directory=str(MEM_DIR),
        )
        vs.persist()
    return vs

def similar_cases(query_text: str, k: int = 3):
    try:
        embed = _embedder()
        vs = _open_store(embed)
        return vs.similarity_search(query_text, k=k)
    except Exception:
        return []
