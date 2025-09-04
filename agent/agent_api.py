# agent/agent_api.py
from __future__ import annotations

import os, json
from typing import Literal, List, Dict, Any
from pathlib import Path
import sys

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, field_validator

# Local imports
HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.append(str(HERE))

from db import get_session, engine
from models import Base
from repo import insert_decision, get_kpis, list_decisions
from tools import kyc_tool, credit_tool          # used for mock endpoints
from graph import graph                          # LangGraph pipeline

# ----------------- Config -----------------
HOST = os.getenv("AGENT_HOST", "127.0.0.1")
PORT = int(os.getenv("AGENT_PORT", "8010"))

# ----------------- App -----------------
app = FastAPI(title="Loan Review Agent API", version="5.0.0 (LangGraph)")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # tighten for prod
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.on_event("startup")
def _startup_create_tables():
    Base.metadata.create_all(bind=engine)

# ----------------- Schemas -----------------
Employment = Literal["employed", "self-employed", "student", "retired", "contract", "unemployed"]

class ReviewRequest(BaseModel):
    name: str
    age: int
    income: float
    employment_status: Employment
    credit_score: int
    loan_amount: float
    term_months: int
    interest_rate: float
    purpose: str

    @field_validator("age")
    @classmethod
    def check_age(cls, v): 
        if v < 18 or v > 100: raise ValueError("age must be between 18 and 100")
        return v
    @field_validator("income", "loan_amount", "interest_rate")
    @classmethod
    def non_negative(cls, v):
        if v < 0: raise ValueError("must be >= 0")
        return v
    @field_validator("credit_score")
    @classmethod
    def credit_range(cls, v):
        if v < 300 or v > 900: raise ValueError("credit_score must be in [300, 900]")
        return v

class ReviewResponse(BaseModel):
    decision: Literal["approve", "reject", "manual_review"]
    reason: str
    used_tools: List[str] = []

# ----------------- Public endpoints -----------------
@app.get("/health")
def health():
    return {"ok": True, "version": app.version}

@app.get("/kpis")
def kpis():
    with get_session() as s:
        return get_kpis(s)

@app.get("/decisions")
def decisions(limit: int = 200):
    with get_session() as s:
        return list_decisions(s, limit=limit)

# Mock tool endpoints (same logic as used inside the graph)
@app.get("/mock/kyc/{customer_id}")
def mock_kyc(customer_id: str):
    return kyc_tool(customer_id)

@app.get("/mock/credit/{customer_id}")
def mock_credit(customer_id: str):
    return credit_tool(customer_id)

# Main review endpoint -> runs the LangGraph pipeline
@app.post("/agent_review", response_model=ReviewResponse)
def agent_review(req: ReviewRequest):
    # assemble initial state for graph
    state = {
        "req": req.model_dump(),
        "baseline": None,
        "kyc": None,
        "credit": None,
        "similar": [],
        "llm_choice": None,
        "decision": None,
        "reason": None,
        "used_tools": [],
        "errors": [],
    }

    try:
        out = graph.invoke(state)   # run the pipeline
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Graph execution failed: {e}")

    decision = out.get("decision") or "manual_review"
    reason = (out.get("reason") or "No reason.").strip()

    # Persist to DB
    with get_session() as s:
        rec = {
            "name": req.name,
            "age": req.age,
            "income": req.income,
            "employment_status": req.employment_status,
            "credit_score": req.credit_score,
            "loan_amount": req.loan_amount,
            "term_months": req.term_months,
            "interest_rate": req.interest_rate,
            "purpose": req.purpose,
            "decision": decision,
            "reason": reason,
            "used_tools": {"tools": out.get("used_tools", [])},
            "raw_output": {
                "baseline": out.get("baseline"),
                "kyc": out.get("kyc"),
                "credit": out.get("credit"),
                "similar": out.get("similar", [])[:3],
                "llm_choice": out.get("llm_choice") or {},
                "errors": out.get("errors", []),
            },
        }
        insert_decision(s, rec)

    return ReviewResponse(decision=decision, reason=reason, used_tools=out.get("used_tools", []))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("agent_api:app", host=HOST, port=PORT, reload=True)
