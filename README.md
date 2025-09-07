# Loan Review Agent

## Overview
An end-to-end loan review system combining rule-based checks with AI-driven insights.  
Built with **Streamlit (UI)**, **FastAPI (backend)**, **SQLite (database)**, and **LangGraph + Mistral LLM (via Ollama)** for explainability.

## Features
- Loan application form with decision results  
- Rule-based KYC and credit checks  
- AI reasoning with LLM (optional)  
- KPI dashboard and decision history  
- SQLite for structured storage, optional Chroma for similarity recall  

## How to Run
1. Clone repo and create virtual environment  
2. Install dependencies: `pip install -r requirements.txt`  
3. Run backend: `uvicorn agent_api:app --reload --port 8010`  
4. Run frontend: `streamlit run ui/streamlit_app.py`  

## Project Roles
- LLM Prompt Design  
- API Simulation  
- UI (Streamlit Frontend)  
- Data Generation  
