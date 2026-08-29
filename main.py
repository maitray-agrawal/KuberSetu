from fastapi import FastAPI, Path, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
import pandas as pd
import json
import difflib
import math
import os
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

app = FastAPI(
    title="SettleSense API",
    description="Financial Reconciliation Engine API",
    version="1.0.0"
)

# Allow React to talk to this API
cors_origins_str = os.getenv("CORS_ORIGINS", "*")
if cors_origins_str == "*":
    cors_origins = ["*"]
else:
    cors_origins = [origin.strip() for origin in cors_origins_str.split(",") if origin.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

DATA_DIR = os.getenv("DATA_DIR", "data")
RISK_TOLERANCE_INR = float(os.getenv("RISK_TOLERANCE_INR", "500.00"))

def similarity(a, b):
    return difflib.SequenceMatcher(None, str(a).lower(), str(b).lower()).ratio()

def run_reconciliation_logic(save_log: bool = False):
    # 1. Load Data
    gw_df = pd.read_csv(f"{DATA_DIR}/gateway.csv")
    leg_df = pd.read_csv(f"{DATA_DIR}/ledger.csv")
    bank_df = pd.read_csv(f"{DATA_DIR}/bank.csv")
    
    gw_df['dt'] = pd.to_datetime(gw_df['timestamp'], format='%d-%m-%Y %H:%M')
    leg_df['dt'] = pd.to_datetime(leg_df['entry_date'], format='%d.%m.%Y')
    bank_df['dt'] = pd.to_datetime(bank_df['settled_on'], format='%Y-%m-%d')

    matched_results = {}
    exceptions_logged = {"TIMING_DRIFT": 0, "FEE_VARIANCE": 0, "REFERENCE_VARIANCE": 0}

    # PASS 1: Exact ID Matches
    for _, gw in gw_df.iterrows():
        gw_id = str(gw['gateway_id']).strip()
        leg_match = leg_df[leg_df['entry_id'].astype(str).str.strip() == gw_id]
        bank_match = bank_df[bank_df['settlement_ref'].astype(str).str.strip() == gw_id]
        
        if not leg_match.empty and not bank_match.empty:
            leg, bank = leg_match.iloc[0], bank_match.iloc[0]
            causes = []
            
            if abs(gw['amount'] - bank['credited_amount']) > 0.01:
                causes.append("FEE_VARIANCE")
                exceptions_logged["FEE_VARIANCE"] += 1
            if (bank['dt'] - gw['dt']).days > 0:
                causes.append("TIMING_DRIFT")
                exceptions_logged["TIMING_DRIFT"] += 1
                
            if not causes:
                causes.append("EXACT_MATCH")
                
            rule_fired = causes[0] if len(causes) == 1 else ", ".join(causes)
            matched_results[gw_id] = {
                "gateway_id": gw_id,
                "ledger_id": str(leg['entry_id']),
                "bank_id": str(bank['settlement_ref']),
                "matched_pass": "Pass 1 (Exact ID Match)",
                "root_causes": causes,
                "rule_fired": rule_fired,
                "confidence": 1.00,
                "exposure": float(gw['amount'])
            }

    # PASS 2: Fuzzy Matches
    gw_unmatched = gw_df[~gw_df['gateway_id'].isin(matched_results.keys())]
    leg_unmatched = leg_df[~leg_df['entry_id'].isin([m['ledger_id'] for m in matched_results.values()])]
    bank_unmatched = bank_df[~bank_df['settlement_ref'].isin([m['bank_id'] for m in matched_results.values()])]

    for _, gw in gw_unmatched.iterrows():
        best_match, best_score = None, 0.0
        gw_id = str(gw['gateway_id']).strip()
        
        for _, leg in leg_unmatched.iterrows():
            for _, bank in bank_unmatched.iterrows():
                if abs(gw['amount'] - leg['gross_value']) < 1 and abs(gw['amount'] - bank['credited_amount']) <= (gw['amount'] * 0.05):
                    avg_sim = (similarity(gw_id, leg['entry_id']) + similarity(gw_id, bank['settlement_ref'])) / 2
                    if avg_sim > 0.65 and avg_sim > best_score:
                        best_score = avg_sim
                        best_match = (leg['entry_id'], bank['settlement_ref'])

        if best_match:
            matched_results[gw_id] = {
                "gateway_id": gw_id,
                "ledger_id": str(best_match[0]),
                "bank_id": str(best_match[1]),
                "matched_pass": "Pass 2 (Fuzzy Match)",
                "root_causes": ["REFERENCE_VARIANCE"],
                "rule_fired": "REFERENCE_VARIANCE",
                "confidence": round(best_score, 2),
                "exposure": float(gw['amount'])
            }
            exceptions_logged["REFERENCE_VARIANCE"] += 1
            leg_unmatched = leg_unmatched[leg_unmatched['entry_id'] != best_match[0]]
            bank_unmatched = bank_unmatched[bank_unmatched['settlement_ref'] != best_match[1]]

    # PASS 3: RISK POLICY ENGINE
    auto_resolved = []
    human_review = []
    orphans = []

    for gw_id, result in matched_results.items():
        prob_wrong = 1.0 - result['confidence']
        expected_loss = prob_wrong * result['exposure']
        
        result['expected_loss'] = round(expected_loss, 2)
        
        if expected_loss <= RISK_TOLERANCE_INR and result['confidence'] >= 0.70:
            result['status'] = "AUTO_RESOLVED"
            auto_resolved.append(result)
        else:
            result['status'] = "HUMAN_REVIEW"
            human_review.append(result)

    for _, gw in gw_unmatched.iterrows():
        gw_id = str(gw['gateway_id']).strip()
        if gw_id not in matched_results:
            orphans.append({
                "gateway_id": gw_id,
                "ledger_id": None,
                "bank_id": None,
                "matched_pass": "Unmatched (Orphan)",
                "exposure": float(gw['amount']),
                "status": "UNRESOLVED_ORPHAN",
                "root_causes": ["MISSING_SOURCES"],
                "rule_fired": "MISSING_SOURCES",
                "confidence": 0.0,
                "expected_loss": round(float(gw['amount']), 2)
            })

    # Build audit trail
    audit_trail = [
        {
            "gateway_id": res.get("gateway_id"),
            "ledger_id": res.get("ledger_id"),
            "bank_id": res.get("bank_id"),
            "matched_pass": res.get("matched_pass"),
            "rule_fired": res.get("rule_fired"),
            "confidence": res.get("confidence"),
            "expected_loss": res.get("expected_loss"),
            "exposure": res.get("exposure"),
            "status": res.get("status")
        }
        for res in matched_results.values()
    ]

    metrics = {
        "total_processed": len(gw_df),
        "auto_resolved_count": len(auto_resolved),
        "auto_resolved_value": sum(item['exposure'] for item in auto_resolved),
        "human_review_count": len(human_review),
        "human_review_value": sum(item['exposure'] for item in human_review),
        "orphan_count": len(orphans),
        "orphan_value": sum(item['exposure'] for item in orphans),
        "automation_rate": round(len(auto_resolved) / len(gw_df), 3) if len(gw_df) > 0 else 0.0
    }

    if save_log:
        os.makedirs("logs", exist_ok=True)
        timestamp_str = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        log_filename = f"logs/reconcile_{timestamp_str}.json"

        log_payload = {
            "timestamp": datetime.now().isoformat(),
            "metrics": metrics,
            "matched_results": matched_results,
            "audit_trail": audit_trail,
            "orphans": orphans,
            "exceptions_breakdown": exceptions_logged
        }

        with open(log_filename, "w", encoding="utf-8") as f:
            json.dump(log_payload, f, indent=2)

    return {
        "metrics": metrics,
        "matched_results": matched_results,
        "human_review_queue": human_review,
        "auto_resolved": auto_resolved,
        "orphans": orphans,
        "exceptions_breakdown": exceptions_logged
    }

@app.get("/api/health")
def health_check():
    return {
        "status": "healthy",
        "service": "SettleSense API",
        "timestamp": datetime.now().isoformat()
    }

@app.get("/api/metrics")
def get_metrics():
    res = run_reconciliation_logic(save_log=False)
    return {
        "metrics": res["metrics"],
        "exceptions_breakdown": res["exceptions_breakdown"]
    }

@app.get("/api/audit/{gateway_id}")
def get_audit_trail(
    gateway_id: str = Path(..., min_length=1, max_length=100, description="The Gateway Transaction ID to audit")
):
    clean_id = gateway_id.strip()
    if not clean_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Gateway ID must not be empty or whitespace."
        )

    res = run_reconciliation_logic(save_log=False)
    matched_results = res["matched_results"]
    orphans = res["orphans"]

    if clean_id in matched_results:
        item = matched_results[clean_id]
        return {
            "gateway_id": item["gateway_id"],
            "matched_pass": item.get("matched_pass"),
            "rule_fired": item.get("rule_fired"),
            "confidence": item.get("confidence"),
            "expected_loss": item.get("expected_loss"),
            "root_causes": item.get("root_causes"),
            "exposure": item.get("exposure"),
            "status": item.get("status"),
            "ledger_id": item.get("ledger_id"),
            "bank_id": item.get("bank_id")
        }

    for orphan in orphans:
        if orphan["gateway_id"] == clean_id:
            return {
                "gateway_id": orphan["gateway_id"],
                "matched_pass": orphan.get("matched_pass", "Unmatched (Orphan)"),
                "rule_fired": orphan.get("rule_fired", "MISSING_SOURCES"),
                "confidence": orphan.get("confidence", 0.0),
                "expected_loss": orphan.get("expected_loss"),
                "root_causes": orphan.get("root_causes", ["MISSING_SOURCES"]),
                "exposure": orphan.get("exposure"),
                "status": orphan.get("status", "UNRESOLVED_ORPHAN"),
                "ledger_id": None,
                "bank_id": None
            }

    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail=f"Transaction with gateway_id '{clean_id}' was not found."
    )

@app.get("/api/reconcile")
def run_reconciliation():
    res = run_reconciliation_logic(save_log=True)
    return {
        "metrics": res["metrics"],
        "human_review_queue": res["human_review_queue"],
        "exceptions_breakdown": res["exceptions_breakdown"]
    }

if __name__ == "__main__":
    import uvicorn
    # Run on port 8000
    uvicorn.run(app, host="0.0.0.0", port=8000)