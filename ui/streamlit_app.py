# ui/streamlit_app.py
import os, json, requests, pandas as pd
from pathlib import Path
from datetime import datetime
import streamlit as st

# ------------- App Setup -------------
st.set_page_config(page_title="Loan Application Review Assistant", page_icon="🏦", layout="wide")
st.title("🏦 Loan Application Review Assistant (Agent + APIs)")

# ------------- Settings -------------
PROJECT_ROOT = Path(__file__).resolve().parents[1]
AGENT_URL = os.getenv("AGENT_REVIEW_URL", "http://127.0.0.1:8010/agent_review")
REQUEST_TIMEOUT = int(os.getenv("AGENT_TIMEOUT_SECS", "60"))
API_ROOT = AGENT_URL.rsplit("/", 1)[0]  # http://host:port

def clean_json_text(text: str) -> str:
    t = (text or "").strip()
    if t.startswith("```"):
        t = t.strip("` \n")
        if t[:4].lower() == "json":
            t = t[4:].strip()
    return t

def display_decision(card: dict):
    decision = str(card.get("decision", "")).strip().lower()
    reason   = str(card.get("reason", "") or "").strip()
    used     = card.get("used_tools", [])
    if decision == "approve": st.success("✅ **APPROVED**")
    elif decision == "reject": st.error("⛔ **REJECTED**")
    else: st.warning("⚠️ **FLAGGED FOR REVIEW**")
    if reason: st.markdown(f"**Reason:** {reason}")
    if used:
        if isinstance(used, str):
            try: used = json.loads(used)
            except Exception: pass
        if isinstance(used, list): st.caption("Used tools: " + ", ".join(map(str, used)))

def show_app_summary(app_dict: dict):
    with st.expander("See submitted application", expanded=False):
        st.json(app_dict)

def fetch_kpis():
    try:
        return requests.get(f"{API_ROOT}/kpis", timeout=10).json()
    except Exception:
        return None

def fetch_decisions(limit=200):
    try:
        return requests.get(f"{API_ROOT}/decisions", params={"limit": limit}, timeout=10).json()
    except Exception:
        return []

# ------------- UI Form -------------
with st.form("loan_form"):
    name = st.text_input("Name")
    col1, col2, col3 = st.columns(3)
    with col1:
        age = st.number_input("Age", min_value=18, max_value=100, value=30)
    with col2:
        income = st.number_input("Annual Income", min_value=0, value=75000, step=1000)
    with col3:
        credit_score = st.number_input("Credit Score", min_value=300, max_value=900, value=700)

    employment_status = st.selectbox(
        "Employment Status",
        ["employed", "self-employed", "student", "retired", "contract", "unemployed"],
        index=0
    )

    col4, col5, col6 = st.columns(3)
    with col4:
        loan_amount = st.number_input("Loan Amount", min_value=0, value=25000, step=1000)
    with col5:
        term_months = st.number_input("Term (months)", min_value=6, max_value=360, value=60, step=6)
    with col6:
        interest_rate = st.number_input("Interest Rate (%)", min_value=0.0, max_value=100.0, value=14.0, step=0.5)

    purpose = st.text_input("Purpose", value="car")
    submitted = st.form_submit_button("Submit")

if submitted:
    app_dict = {
        "name": name,
        "age": int(age),
        "income": float(income),
        "employment_status": employment_status,
        "credit_score": int(credit_score),
        "loan_amount": float(loan_amount),
        "term_months": int(term_months),
        "interest_rate": float(interest_rate),
        "purpose": purpose
    }
    try:
        r = requests.post(AGENT_URL, json=app_dict, timeout=REQUEST_TIMEOUT)
        if r.status_code != 200:
            st.error(f"Agent API returned {r.status_code}")
            try: st.code(json.dumps(r.json(), indent=2), language="json")
            except Exception: st.code(r.text)
            show_app_summary(app_dict)
        else:
            resp = r.json()
            raw = resp.get("output", resp)
            if isinstance(raw, dict):
                card = raw
            else:
                text = clean_json_text(str(raw))
                try: card = json.loads(text)
                except Exception: card = {"decision": "Flag", "reason": "Unparseable model output", "used_tools": []}
            st.success("Decision received")
            display_decision(card)
            show_app_summary(app_dict)
    except requests.exceptions.RequestException as e:
        st.error("API call failed.")
        st.caption("Exception:"); st.code(str(e))
        st.caption("Payload we sent:"); st.json(app_dict)

# ------------- Decision History (from API/DB) -------------
st.markdown("---")
st.subheader("📜 Decision history")

k = fetch_kpis()
if k:
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Total", int(k.get("total", 0)))
    c2.metric("Approved", int(k.get("approved", 0)))
    c3.metric("Rejected", int(k.get("rejected", 0)))
    c4.metric("Flagged", int(k.get("flagged", 0)))
else:
    st.caption("KPI API not available.")

hist = fetch_decisions(limit=300)
if not hist:
    st.caption("No decisions found yet. Submit an application above.")
else:
    df = pd.DataFrame(hist)
    # maintain order and pretty used_tools
    if "used_tools" in df.columns:
        df["used_tools"] = df["used_tools"].apply(lambda x: ", ".join(x) if isinstance(x, list) else str(x))
    st.dataframe(df, use_container_width=True, height=360)

    # download as CSV (client-side)
    csv_bytes = df.to_csv(index=False).encode("utf-8")
    st.download_button("⬇️ Download decisions.csv", data=csv_bytes, file_name="decisions.csv", mime="text/csv")
