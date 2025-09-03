# agent/repo.py
from __future__ import annotations
from sqlalchemy import select, func
from sqlalchemy.orm import Session
from typing import List, Dict, Any
from models import Decision

def insert_decision(s: Session, row: Dict[str, Any]) -> int:
    d = Decision(**row)
    s.add(d)
    s.flush()  # populates d.id
    return d.id

def get_kpis(s: Session) -> Dict[str, int]:
    total = s.scalar(select(func.count(Decision.id))) or 0
    approved = s.scalar(select(func.count()).where(Decision.decision == "approve")) or 0
    rejected = s.scalar(select(func.count()).where(Decision.decision == "reject")) or 0
    flagged = s.scalar(
        select(func.count()).where(Decision.decision.in_(["manual_review", "flag", "flagged"]))
    ) or 0
    return {"total": total, "approved": approved, "rejected": rejected, "flagged": flagged}

def list_decisions(s: Session, limit: int = 200) -> List[Dict[str, Any]]:
    rows = s.execute(
        select(Decision).order_by(Decision.id.desc()).limit(limit)
    ).scalars().all()
    out = []
    for r in rows:
        out.append({
            "id": r.id,
            "timestamp": r.timestamp.isoformat(timespec="seconds"),
            "name": r.name,
            "age": r.age,
            "income": r.income,
            "employment_status": r.employment_status,
            "credit_score": r.credit_score,
            "loan_amount": r.loan_amount,
            "term_months": r.term_months,
            "interest_rate": r.interest_rate,
            "purpose": r.purpose,
            "decision": r.decision,
            "reason": r.reason,
            "used_tools": (r.used_tools or {}).get("tools", []),
            "raw_output": r.raw_output or {},
        })
    return out
