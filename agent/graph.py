# agent/graph.py
from __future__ import annotations

import os, json, requests
from typing import Any, Dict, List, Optional
from langgraph.graph import StateGraph, END

from tools import kyc_tool, credit_tool
from similarity_memory import similar_cases

# ---- Config (env-driven) ----
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://127.0.0.1:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3.2:3b")
OLLAMA_TIMEOUT = int(os.getenv("OLLAMA_TIMEOUT_SECS", "12"))
DISABLE_LLM = os.getenv("DISABLE_LLM", "0") == "1"

# ---- Helpers ----
def _rule_based(req: Dict[str, Any]) -> Dict[str, Any]:
    reasons, decision = [], "approve"
    # simple guardrails similar to your existing rules
    if req["loan_amount"] > 10 * req["income"]:
        reasons.append("Requested amount exceeds 10× annual income.")
    if req["credit_score"] < 520:
        reasons.append("Very low credit score (<520).")
    elif req["credit_score"] < 620:
        reasons.append("Low credit score (520–619). Consider manual review.")
    if req["employment_status"] in {"student", "unemployed"} and req["loan_amount"] > 0.5 * req["income"]:
        reasons.append("High risk profile given employment and requested amount.")

    if any("Very low credit score" in r for r in reasons):
        decision = "reject"
    elif any("exceeds 10×" in r for r in reasons) or any("High risk profile" in r for r in reasons):
        decision = "manual_review"

    return {"decision": decision, "reasons": reasons}

def _policy_guard(decision: str, req: Dict[str, Any], kyc: dict) -> str:
    if decision == "approve":
        if (not kyc.get("kyc_verified", False)) or kyc.get("pep_match", False):
            return "manual_review"
        if req["credit_score"] < 520 or req["loan_amount"] > 12 * req["income"]:
            return "manual_review"
    return decision

def _ollama_once(prompt: str) -> Optional[str]:
    try:
        r = requests.post(
            f"{OLLAMA_URL}/api/generate",
            json={"model": OLLAMA_MODEL, "prompt": prompt, "stream": False,
                  "options": {"temperature": 0.2, "top_p": 0.9, "num_predict": 220}},
            timeout=OLLAMA_TIMEOUT,
        )
        r.raise_for_status()
        return (r.json().get("response") or "").strip()
    except Exception:
        return None

def _format_reason_paragraph(req: Dict[str, Any], decision: str, short_reason: str, baseline: Dict[str, Any] | None) -> str:
    name = req.get("name") or "The applicant"
    inc = req.get("income")
    amt = req.get("loan_amount")
    cs  = req.get("credit_score")
    emp = req.get("employment_status") or "unknown"
    dti = None
    try:
        if inc and amt is not None and inc > 0:
            dti = round((amt / max(1.0, inc)), 2)
    except Exception:
        dti = None

    base_reasons = []
    if baseline and isinstance(baseline.get("reasons"), list):
        base_reasons = [str(r) for r in baseline.get("reasons") if r]

    parts = []
    parts.append(f"We decided to {decision.replace('_',' ')} this application. {short_reason.strip() or ''}".strip())
    ctx_bits = []
    if cs is not None:
        ctx_bits.append(f"credit score {cs}")
    if inc is not None:
        ctx_bits.append(f"monthly income {inc}")
    if amt is not None:
        ctx_bits.append(f"requested amount {amt}")
    if dti is not None:
        ctx_bits.append(f"amount-to-income ratio ≈ {dti}")
    if ctx_bits:
        parts.append("Key factors considered include " + ", ".join(ctx_bits) + ".")
    if base_reasons:
        parts.append("Rules check notes: " + "; ".join(base_reasons) + ".")

    if decision == "approve":
        nxt = "You can proceed to sign the agreement and upload any required KYC documents."
    elif decision == "reject":
        nxt = "You may reapply after improving your credit profile or adjusting the requested amount."
    else:
        nxt = "Our team will review your case and may request more documents."

    paragraph = " ".join(parts).replace("\n", " ").replace("•", "").replace("- ", "").strip()
    return paragraph + f"\nNext step: {nxt}"

# ---- Nodes ----
def node_rules(state: Dict[str, Any]) -> Dict[str, Any]:
    state["baseline"] = _rule_based(state["req"])
    state["used_tools"] = list(set(state.get("used_tools", []) + ["rules"]))
    return state

def node_tools(state: Dict[str, Any]) -> Dict[str, Any]:
    # call mock tools in parallel-ish style
    try:
        state["kyc"] = kyc_tool(state["req"]["name"])
        state["used_tools"] = list(set(state.get("used_tools", []) + ["kyc_tool"]))
    except Exception as e:
        state.setdefault("errors", []).append(f"kyc_tool: {e!s}")
    try:
        state["credit"] = credit_tool(state["req"]["name"])
        state["used_tools"] = list(set(state.get("used_tools", []) + ["credit_tool"]))
    except Exception as e:
        state.setdefault("errors", []).append(f"credit_tool: {e!s}")
    return state

def node_memory(state: Dict[str, Any]) -> Dict[str, Any]:
    try:
        state["similar"] = similar_cases({
            "income": state["req"]["income"],
            "loan_amount": state["req"]["loan_amount"],
            "credit_score": state["req"]["credit_score"],
            "purpose": state["req"]["purpose"],
        })
        if state["similar"]:
            state["used_tools"] = list(set(state.get("used_tools", []) + ["similar_memory"]))
    except Exception as e:
        state.setdefault("errors", []).append(f"similarity: {e!s}")
    return state

def node_llm(state: Dict[str, Any]) -> Dict[str, Any]:
    base = state.get("baseline") or {}
    decision = base.get("decision") or "manual_review"
    short_reason = "; ".join(base.get("reasons", [])) or "Based on policy and the provided numbers."
    # try to get a succinct reason from an LLM (optional)
    if not DISABLE_LLM:
        sim_lines = [f"- {d.get('page_content','')[:220]}" for d in (state.get("similar") or [])]
        prompt = f"""You are a senior underwriter. Return one short sentence (no bullets) explaining the decision.
Application={json.dumps(state["req"])}
KYC={json.dumps(state.get("kyc") or {})}
Credit={json.dumps(state.get("credit") or {})}
Baseline={json.dumps(base)}
SimilarCases:
{os.linesep.join(sim_lines) if sim_lines else "None"}"""
        resp = _ollama_once(prompt)
        if resp:
            short_reason = resp.splitlines()[0].strip()
            state["used_tools"] = list(set(state.get("used_tools", []) + ["llm_reasoning"]))
    # finalize decision may already be clear from baseline
    state["decision"] = decision
    state["reason"] = _format_reason_paragraph(state["req"], decision, short_reason, base)
    return state

def node_guard(state: Dict[str, Any]) -> Dict[str, Any]:
    d0 = state.get("decision") or "manual_review"
    guarded = _policy_guard(d0, state["req"], state.get("kyc") or {})
    if guarded != d0:
        state["used_tools"] = list(set(state.get("used_tools", []) + ["policy_guard"]))
        state["decision"] = guarded
        # keep previous paragraph but adjust the opening decision word
        state["reason"] = _format_reason_paragraph(
            state["req"],
            guarded,
            "Policy guard adjusted the outcome based on KYC and risk thresholds.",
            state.get("baseline") or {}
        )
    return state

# ---- Graph ----
_g = StateGraph(dict)
_g.add_node("rules", node_rules)
_g.add_node("tools", node_tools)
_g.add_node("memory", node_memory)
_g.add_node("llm", node_llm)
_g.add_node("guard", node_guard)

_g.set_entry_point("rules")
_g.add_edge("rules", "tools")
_g.add_edge("tools", "memory")
_g.add_edge("memory", "llm")
_g.add_edge("llm", "guard")
_g.add_edge("guard", END)

graph = _g.compile()