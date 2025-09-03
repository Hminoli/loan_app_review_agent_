# agent/models.py
from __future__ import annotations
from datetime import datetime
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy import String, Float, Integer, JSON, DateTime

class Base(DeclarativeBase):
    pass

class Decision(Base):
    __tablename__ = "decisions"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)

    # Application inputs
    name: Mapped[str] = mapped_column(String(120))
    age: Mapped[int] = mapped_column(Integer)
    income: Mapped[float] = mapped_column(Float)
    employment_status: Mapped[str] = mapped_column(String(40))
    credit_score: Mapped[int] = mapped_column(Integer)
    loan_amount: Mapped[float] = mapped_column(Float)
    term_months: Mapped[int] = mapped_column(Integer)
    interest_rate: Mapped[float] = mapped_column(Float)
    purpose: Mapped[str] = mapped_column(String(120))

    # Outputs
    decision: Mapped[str] = mapped_column(String(20))
    reason: Mapped[str] = mapped_column(String(2048))

    # Extras
    used_tools: Mapped[dict] = mapped_column(JSON)     # e.g. {"tools": ["kyc_check", "credit_check", ...]}
    raw_output: Mapped[dict] = mapped_column(JSON)     # raw payloads if needed
