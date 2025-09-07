# ui/streamlit_app.py
import os, json, requests, pandas as pd
from pathlib import Path
import streamlit as st

# ------------------ App Setup ------------------
st.set_page_config(page_title="Loan Application Review Assistant", layout="wide")

# ------------------ Styling ------------------
st.markdown(
    """
    <style>
        .stApp {
            background-color: #f8f9fa;
            color: #212529;
        }
        .main-title {
            font-size: 28px;
            font-weight: 700;
            color: #003366; 
        }
        .subtitle {
            font-size: 15px;
            color: #6c757d;
        }
        .card {
            padding: 18px;
            border-radius: 10px;
            background-color: #ffffff;
            box-shadow: 0px 2px 6px rgba(0,0,0,0.1);
            margin-bottom: 15px;
        }
        h2, h3, h4 {
            color: #003366; 
        }
    </style>
    """,
    unsafe_allow_html=True
)

# ------------------ Header ------------------
st.markdown('<div class="main-title">Loan Application Review Assistant</div>', unsafe_allow_html=True)
st.markdown('<div class="subtitle">AI-powered loan decisioning system</div>', unsafe_allow_html=True)

# ------------------ Config ------------------
PROJECT_ROOT = Path(__file__).resolve().parents[1]
AGENT_URL = os.getenv("AGENT_REVIEW_URL", "http://127.0.0.1:8010/agent_review")
REQUEST_TIMEOUT = int(os.getenv("AGENT_TIMEOUT_SECS", "60"))
API_ROOT = AGENT_URL.rsplit("/", 1)[0]

# ------------------ Helper Functions ------------------
def clean_json_text(text: str) -> str:
    t = (text or "").strip()
    if t.startswith("```"):
        t = t.strip("` \n")
        if t[:4].lower() == "json":
            t = t[4:].strip()
    return t

def display_decision_card(decision: str, reason: str, tools: list):
    color_map = {
        "approve": "#28a745",  
        "reject": "#dc3545",   
        "flag": "#ffc107"      
    }
    bg = color_map.get(decision.lower(), "#003366")  
    st.markdown(
        f"""
        <div style="padding:18px; border-radius:10px; background:{bg}; color:white; margin-top:10px;">
            <h3 style="margin:0;">{decision.upper()}</h3>
            <p>{reason}</p>
            <small>Tools used: {tools}</small>
        </div>
        """,
        unsafe_allow_html=True
    )

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

def kpi_card(label, value, color):
    st.markdown(
        f"""
        <div style="padding:12px; border-radius:8px; background:{color}; text-align:center; color:white;">
            <h5>{label}</h5>
            <h2 style="margin:0;">{value}</h2>
        </div>
        """,
        unsafe_allow_html=True
    )

# ------------------ Layout: Two Columns ------------------
col1, col2 = st.columns([1, 2])

# -------- Left Column: Loan Form --------
with col1:
    st.markdown("### Loan Application Form")
    with st.form("loan_form"):
        name = st.text_input("Name")
        age = st.number_input("Age", min_value=18, max_value=100, value=30)
        income = st.number_input("Annual Income", min_value=0, value=75000, step=1000)
        credit_score = st.number_input("Credit Score", min_value=300, max_value=900, value=700)

        employment_status = st.selectbox(
            "Employment Status",
            ["employed", "self-employed", "student", "retired", "contract", "unemployed"],
            index=0
        )

        loan_amount = st.number_input("Loan Amount", min_value=0, value=25000, step=1000)
        term_months = st.number_input("Term (months)", min_value=6, max_value=360, value=60, step=6)
        interest_rate = st.number_input("Interest Rate (%)", min_value=0.0, max_value=100.0, value=14.0, step=0.5)

        purpose = st.text_input("Purpose", value="car")
        submitted = st.form_submit_button("Submit")

# -------- Right Column: Results --------
with col2:
    st.markdown("### Results & Insights")

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
                try:
                    st.code(json.dumps(r.json(), indent=2), language="json")
                except Exception:
                    st.code(r.text)
                show_app_summary(app_dict)
            else:
                resp = r.json()
                raw = resp.get("output", resp)
                if isinstance(raw, dict):
                    card = raw
                else:
                    text = clean_json_text(str(raw))
                    try: 
                        card = json.loads(text)
                    except Exception: 
                        card = {"decision": "Flag", "reason": "Unparseable model output", "used_tools": []}
                st.success("Decision received")
                display_decision_card(card.get("decision", "Flag"), card.get("reason", ""), card.get("used_tools", []))
                show_app_summary(app_dict)
        except requests.exceptions.RequestException as e:
            st.error("API call failed.")
            st.caption("Exception:")
            st.code(str(e))
            st.caption("Payload we sent:")
            st.json(app_dict)

    # -------- KPI Dashboard --------
    st.markdown("#### Decision KPIs")
    k = fetch_kpis()
    if k:
        c1, c2, c3, c4 = st.columns(4)
        with c1: kpi_card("Total", k.get("total", 0), "#0d6efd")   # main blue
        with c2: kpi_card("Approved", k.get("approved", 0), "#1864ab")  # darker
        with c3: kpi_card("Rejected", k.get("rejected", 0), "#4dabf7")  # lighter
        with c4: kpi_card("Flagged", k.get("flagged", 0), "#74c0fc")    # lightest   
    else:
        st.caption("KPI API not available.")

    # -------- Decision History --------
    st.markdown("#### Decision History")
    hist = fetch_decisions(limit=300)
    if not hist:
        st.caption("No decisions found yet.")
    else:
        df = pd.DataFrame(hist)
        if "used_tools" in df.columns:
            df["used_tools"] = df["used_tools"].apply(lambda x: ", ".join(x) if isinstance(x, list) else str(x))
        st.dataframe(df, use_container_width=True, height=360)

        # Download option
        csv_bytes = df.to_csv(index=False).encode("utf-8")
        st.download_button("Download decisions.csv", data=csv_bytes, file_name="decisions.csv", mime="text/csv")
