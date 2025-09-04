# api/fake_api.py
# FastAPI + Pydantic + simple, realistic lending rules

from enum import Enum
from typing import Dict
from fastapi import FastAPI
from pydantic import BaseModel, conint, confloat, field_validator
import uvicorn

app = FastAPI(title="Bank Sim APIs")

# ---------- Schemas ----------
class Employment(str, Enum):
    employed = "employed"
    self_employed = "self-employed"
    contract = "contract"
    student = "student"
    retired = "retired"
    unemployed = "unemployed"

class LoanApplication(BaseModel):
    name: str
    age: conint(ge=18, le=75)
    income: confloat(ge=0)                   # annual income
    employment_status: Employment
    credit_score: conint(ge=300, le=850)     # FICO-like scale
    loan_amount: confloat(ge=0)
    purpose: str

    @field_validator("purpose")
    @classmethod
    def trim_purpose(cls, v: str) -> str:
        v = v.strip()
        return v if v else "unspecified"

class Decision(BaseModel):
    decision: str          # Approve | Reject | Flag
    reason: str

# ---------- Simulated external system ----------
CUSTOMERS: Dict[str, Dict] = {
    "John Doe":      {"past_defaults": 0, "years_with_employer": 5, "existing_loans": 1},
    "Jane Smith":    {"past_defaults": 1, "years_with_employer": 1, "existing_loans": 3},
    "Ayesha Perera": {"past_defaults": 0, "years_with_employer": 3, "existing_loans": 0},
    "Sunil Silva":   {"past_defaults": 0, "years_with_employer": 0, "existing_loans": 2},
}

@app.get("/customer_info/{name}")
def customer_info(name: str):
    # Return a generic profile if not found
    return CUSTOMERS.get(name, {"past_defaults": 0, "years_with_employer": 2, "existing_loans": 0})

# ---------- Lending policy (simple & explainable) ----------
@app.post("/check_compliance", response_model=Decision)
def check_compliance(app_in: LoanApplication):
    cs   = int(app_in.credit_score)
    inc  = float(app_in.income)
    amt  = float(app_in.loan_amount)
    emp  = app_in.employment_status.value
    age  = int(app_in.age)

    # Derived: loan-to-income ratio (LTI)
    if inc == 0:
        lti = float("inf")
    else:
        lti = amt / inc

    # --- Hard rejections (high risk) ---
    if cs < 580:
        return {"decision": "Reject", "reason": "Very low credit score (<580)"}
    if inc < 15000:
        return {"decision": "Reject", "reason": "Insufficient income (<15,000)"}
    if lti > 0.60:
        return {"decision": "Reject", "reason": "Loan-to-income too high (>60%)"}
    if emp == "unemployed" and cs < 640:
        return {"decision": "Reject", "reason": "Unemployed with weak credit"}

    # --- Fast approvals (low risk) ---
    if cs >= 700 and inc >= 75000 and lti <= 0.40:
        return {"decision": "Approve", "reason": "Good credit, strong income, affordable loan"}
    if amt <= 5000 and cs >= 650 and lti <= 0.50:
        return {"decision": "Approve", "reason": "Small affordable loan with adequate credit"}

    # --- Flags (needs officer review) ---
    if 600 <= cs < 700:
        return {"decision": "Flag", "reason": "Mid credit band (600–699) — review"}
    if 0.40 < lti <= 0.60:
        return {"decision": "Flag", "reason": "Borderline affordability (LTI 40–60%) — review"}
    if emp in {"self-employed", "contract", "student", "retired"}:
        return {"decision": "Flag", "reason": f"Employment status '{emp}' — review"}
    if 15000 <= inc < 75000:
        return {"decision": "Flag", "reason": "Moderate income — review"}

    # Default: conservative approve if all checks passed
    return {"decision": "Approve", "reason": "Meets baseline policy"}

# ---------- Run ----------
if __name__ == "__main__":
    uvicorn.run("fake_api:app", host="127.0.0.1", port=8000, reload=True)
