# agent/tools.py
from __future__ import annotations

def kyc_tool(customer_id: str) -> dict:
    """
    Mock KYC check. Flags names starting with x/test/fake.
    Replace with real service call when available.
    """
    flagged = customer_id.lower().startswith(("x", "test", "fake"))
    return {
        "customer_id": customer_id,
        "kyc_verified": not flagged,
        "pep_match": bool(flagged),
        "doc_expired": False,
    }

def credit_tool(customer_id: str) -> dict:
    """
    Mock credit profile derived from the string's char sum (deterministic).
    Replace with real bureau integration.
    """
    base = sum(ord(c) for c in customer_id) % 100
    return {
        "customer_id": customer_id,
        "delinquencies_12mo": base % 3,
        "utilization": min(1.0, 0.2 + (base % 40) / 100.0),
        "recent_hard_pulls": base % 2,
    }
