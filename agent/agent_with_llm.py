# agent_with_llm.py — robust agent with retrieval (Chroma) for TinyLlama via Ollama
# Produces:
#   - decision: Approve | Reject | Flag (normalized)
#   - reason: short, clean (from Compliance API)
#   - reason_detailed: 2–4 sentence plain-English explanation (LLM-generated with fallbacks)
#   - used_tools: ["check_compliance", "customer_info", "similar_cases"?]

from typing import Dict, Any, Optional, Tuple
import json, re, time, unicodedata
import requests
from langchain_ollama import ChatOllama
from langchain_core.messages import SystemMessage, HumanMessage

# vector memory for "similar past cases"
from similarity_memory import similar_cases

# ---------- Config ----------
CHECK_URL = "http://127.0.0.1:8000/check_compliance"
CUST_URL  = "http://127.0.0.1:8000/customer_info/{name}"

# Use your local tiny model
llm = ChatOllama(model="tinyllama", temperature=0.2)

# ---------- Helpers ----------
def _strip_accents(s: str) -> str:
    return unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode("ascii")

def _normalize_decision(s: Optional[str]) -> Optional[str]:
    if not s:
        return None
    t = _strip_accents(s).strip().lower()
    approve_set = {
        "approve","approved","ok","accept","accepted","grant","granted",
        "approuve","approuvee","aprobado","aprovado"
    }
    reject_set  = {
        "reject","rejected","deny","denied","decline","declined",
        "rejeter","rejete","rechazado","negado"
    }
    flag_set    = {
        "flag","review","manual review","needs review","hold",
        "surveiller","revision","pendiente"
    }
    if t in approve_set: return "Approve"
    if t in reject_set:  return "Reject"
    if t in flag_set:    return "Flag"
    return None

def _extract_json_block(text: str) -> Optional[Dict[str, Any]]:
    """Return the first valid JSON object found in text, or None."""
    t = text.strip()
    if t.startswith("```"):
        t = t.strip("` \n")
        if t.lower().startswith("json"):
            t = t[4:].strip()
    m = re.search(r"\{[\s\S]*\}", t)
    if not m:
        return None
    try:
        return json.loads(m.group(0))
    except Exception:
        return None

def _call_compliance(app_dict: Dict[str, Any]) -> Dict[str, Any]:
    for attempt in range(2):
        try:
            r = requests.post(CHECK_URL, json=app_dict, timeout=30)
            r.raise_for_status()
            return r.json()
        except Exception:
            if attempt == 1:
                raise
            time.sleep(0.5)

def _call_customer(name: str) -> Dict[str, Any]:
    for attempt in range(2):
        try:
            r = requests.get(CUST_URL.format(name=name), timeout=30)
            r.raise_for_status()
            return r.json()
        except Exception:
            if attempt == 1:
                raise
            time.sleep(0.5)

def _similar_cases_block(app_dict: dict, k: int = 3) -> Tuple[str, bool]:
    """Return a text block describing top-k similar cases, and whether we actually found any."""
    q = (
        f"Age {app_dict.get('age')}, income {app_dict.get('income')}, "
        f"employment {app_dict.get('employment_status')}, credit {app_dict.get('credit_score')}, "
        f"loan {app_dict.get('loan_amount')}, purpose {app_dict.get('purpose')}"
    )
    hits = similar_cases(q, k=k)
    if not hits:
        return "No similar prior cases found.", False
    lines = []
    for i, d in enumerate(hits, 1):
        lines.append(f"{i}) {d.page_content}")
    return "\n".join(lines), True

def _normalize_card(card: Dict[str, Any],
                    compliance: Dict[str, Any],
                    used_tools: list) -> Dict[str, Any]:
    """Ensure decision ∈ {Approve,Reject,Flag}; reason forced from compliance; tools ensured."""
    decision = _normalize_decision(str(card.get("decision", "")))
    if not decision:
        decision = _normalize_decision(str(compliance.get("decision", ""))) or "Flag"

    # Always show the compliance reason to keep it clean English
    reason = str(compliance.get("reason", "Decision based on compliance rules")).strip()

    tools = card.get("used_tools")
    if not isinstance(tools, list) or not tools:
        tools = used_tools

    # temp container; reason_detailed will be added later
    return {"decision": decision, "reason": reason, "used_tools": tools}

def _compute_lti(app: Dict[str, Any]) -> Optional[float]:
    inc = float(app.get("income", 0) or 0)
    amt = float(app.get("loan_amount", 0) or 0)
    if inc <= 0:
        return None
    return round(amt / inc, 3)

def _generate_detailed_reason(
    decision: str,
    compliance: Dict[str, Any],
    customer: Dict[str, Any],
    similar_text: str,
    app: Dict[str, Any]
) -> str:
    """
    Ask the LLM for a 2–4 sentence English explanation.
    Fallback to a deterministic paragraph if the LLM fails.
    """
    lti = _compute_lti(app)
    lti_str = f"{int(round(lti*100))}%" if lti is not None else "N/A"
    short_reason = str(compliance.get("reason", "Policy-based decision"))
    cs = app.get("credit_score")
    inc = app.get("income")
    amt = app.get("loan_amount")
    emp = app.get("employment_status")
    defaults = customer.get("past_defaults", "unknown")
    tenure = customer.get("years_with_employer", "unknown")
    loans = customer.get("existing_loans", "unknown")

    # Compose messages
    system = SystemMessage(
        content=(
            "You are an underwriting assistant. "
            "Write 2–4 short sentences in ENGLISH explaining the decision clearly to a customer. "
            "No markdown, no bullet points, no code fences."
        )
    )
    human = HumanMessage(
        content=(
            f"Decision: {decision}\n"
            f"Short reason (from policy): {short_reason}\n\n"
            f"Applicant data: credit_score={cs}, income={inc}, loan_amount={amt}, employment_status={emp}, LTI={lti_str}\n"
            f"Customer info: past_defaults={defaults}, years_with_employer={tenure}, existing_loans={loans}\n\n"
            "Similar past cases summary:\n"
            f"{similar_text}\n\n"
            "Write a concise explanation that ties these factors together and justifies the decision. "
            "Avoid numbers if unknown. Keep it friendly but professional."
        )
    )
    try:
        resp = llm.invoke([system, human])
        text = getattr(resp, "content", "").strip()
        # strip code fences if the tiny model adds them
        if text.startswith("```"):
            text = text.strip("` \n")
            if text.lower().startswith("json"):
                text = text[4:].strip()
        # keep it compact
        return text[:800] if text else short_reason
    except Exception:
        # Deterministic fallback
        parts = []
        if decision == "Approve":
            parts.append("Your application has been approved.")
        elif decision == "Reject":
            parts.append("We’re unable to approve your application at this time.")
        else:
            parts.append("Your application needs a brief manual review.")

        if short_reason:
            parts.append(short_reason + ".")
        if cs:
            parts.append(f"Credit score: {cs}.")
        if lti is not None:
            parts.append(f"Loan-to-income ratio: {lti_str}.")
        if isinstance(tenure, (int, float)) and tenure >= 0:
            parts.append(f"Employment tenure: {tenure} year(s).")
        if isinstance(defaults, (int, float)) and defaults >= 0:
            parts.append(f"Past defaults: {defaults}.")
        return " ".join(parts)[:800]

# ---------- Main entry point ----------
def review_application(app_dict: Dict[str, Any]) -> Dict[str, Any]:
    """
    Reviews a loan application by:
      1) calling the compliance API
      2) calling the customer info API
      3) retrieving similar past cases from Chroma
      4) asking the LLM (TinyLlama) to return a JSON decision + detailed reason
    Returns: {"output": "<JSON string>"}
    """
    # 1) Compliance
    try:
        compliance = _call_compliance(app_dict)
    except Exception:
        return {"output": json.dumps({
            "decision": "Flag",
            "reason": "Compliance service unavailable",
            "reason_detailed": "We could not complete automated checks. Please try again or contact support.",
            "used_tools": ["check_compliance"]
        }, ensure_ascii=False)}

    used_tools = ["check_compliance"]

    # 2) Customer info (best-effort)
    try:
        customer = _call_customer(app_dict.get("name", "unknown"))
        used_tools.append("customer_info")
    except Exception:
        customer = {"note": "Customer info unavailable"}

    # 3) Retrieval from vector memory
    similar_text, had_hits = _similar_cases_block(app_dict, k=3)
    if had_hits:
        used_tools.append("similar_cases")

    # 4) LLM Prompt for decision (still normalized + compliance reason kept)
    system = SystemMessage(
        content=(
            "You are a cautious loan officer.\n"
            "Output ENGLISH ONLY.\n"
            "Return ONLY a single JSON object. No prose, no markdown.\n"
            "Keys: decision (must be EXACTLY one of: Approve, Reject, Flag), "
            "reason (SHORT), used_tools (array of strings)."
        )
    )
    example_json = {
        "decision": "Approve",
        "reason": "Good credit/income and affordable amount",
        "used_tools": ["check_compliance", "customer_info", "similar_cases"]
    }
    human = HumanMessage(
        content=(
            "Decide on this loan using the API results and similar past cases.\n\n"
            f"Loan application:\n{json.dumps(app_dict, ensure_ascii=False)}\n\n"
            f"Compliance API result:\n{json.dumps(compliance, ensure_ascii=False)}\n\n"
            f"Customer info API result:\n{json.dumps(customer, ensure_ascii=False)}\n\n"
            f"Similar past cases (top-3):\n{similar_text}\n\n"
            "Respond ONLY with JSON and nothing else.\n"
            "JSON schema example (format only; adapt values):\n"
            f"{json.dumps(example_json, ensure_ascii=False)}\n\n"
            f'Use these exact used_tools values that apply: {json.dumps(used_tools, ensure_ascii=False)}'
        )
    )

    try:
        resp = llm.invoke([system, human])
        raw = getattr(resp, "content", str(resp)).strip()
        parsed = _extract_json_block(raw)

        if parsed is None:
            # Compliance-only fallback (clean reason)
            fallback = {
                "decision": compliance.get("decision", "Flag"),
                "reason": str(compliance.get("reason", "Decision based on compliance rules")).strip(),
                "used_tools": used_tools
            }
            card = _normalize_card(fallback, compliance, used_tools)
        else:
            card = _normalize_card(parsed, compliance, used_tools)

        # 5) Generate a more descriptive reason (LLM with fallback)
        detailed = _generate_detailed_reason(
            decision=card["decision"],
            compliance=compliance,
            customer=customer,
            similar_text=similar_text,
            app=app_dict
        )
        card["reason_detailed"] = detailed

        return {"output": json.dumps(card, ensure_ascii=False)}

    except Exception:
        # Final fallback: use compliance decision & reason; synthesize detailed
        card = {
            "decision": compliance.get("decision", "Flag"),
            "reason": str(compliance.get("reason", "Decision based on compliance rules")).strip(),
            "used_tools": used_tools
        }
        detailed = _generate_detailed_reason(
            decision=card["decision"],
            compliance=compliance,
            customer=customer,
            similar_text=similar_text,
            app=app_dict
        )
        card["reason_detailed"] = detailed
        return {"output": json.dumps(card, ensure_ascii=False)}
