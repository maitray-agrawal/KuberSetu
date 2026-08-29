from fastapi import FastAPI, Path, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
import pandas as pd
import json
import difflib
import math
import os
from datetime import datetime
from dotenv import load_dotenv
from ml_matcher import get_matcher_model, extract_pair_features

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
    duplicates = []
    seen_gateway_ids = set()
    exceptions_logged = {
        "TIMING_DRIFT": 0,
        "FEE_VARIANCE": 0,
        "REFERENCE_VARIANCE": 0,
        "DUPLICATE_DETECTED": 0
    }

    # PASS 1: Exact ID Matches & Duplicate Detection
    for _, gw in gw_df.iterrows():
        gw_id = str(gw['gateway_id']).strip()
        leg_match = leg_df[leg_df['entry_id'].astype(str).str.strip() == gw_id]
        bank_match = bank_df[bank_df['settlement_ref'].astype(str).str.strip() == gw_id]
        
        if not leg_match.empty and not bank_match.empty:
            leg, bank = leg_match.iloc[0], bank_match.iloc[0]
            
            # Detect duplicate gateway row mapping to the same ledger/bank pair
            if gw_id in seen_gateway_ids:
                dup_entry = {
                    "gateway_id": gw_id,
                    "original_gateway_id": gw_id,
                    "ledger_id": str(leg['entry_id']),
                    "bank_id": str(bank['settlement_ref']),
                    "matched_pass": "Pass 1 (Exact ID Match - Duplicate)",
                    "root_causes": ["DUPLICATE_DETECTED"],
                    "rule_fired": "DUPLICATE_DETECTED",
                    "confidence": 1.00,
                    "exposure": float(gw['amount']),
                    "expected_loss": 0.0,
                    "status": "DUPLICATE_DETECTED"
                }
                duplicates.append(dup_entry)
                exceptions_logged["DUPLICATE_DETECTED"] += 1
                continue

            seen_gateway_ids.add(gw_id)
            causes = []
            
            if abs(gw['amount'] - bank['credited_amount']) > 0.01:
                causes.append("FEE_VARIANCE")
                exceptions_logged["FEE_VARIANCE"] += 1
            if (bank['dt'].normalize() - gw['dt'].normalize()).days > 0:
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

    # PASS 2: Fuzzy Matches using ML Model with Candidate Blocking
    matcher_model = get_matcher_model()
    matched_and_dup_ids = set(matched_results.keys()).union(seen_gateway_ids)
    gw_unmatched = gw_df[~gw_df['gateway_id'].isin(matched_and_dup_ids)]
    leg_unmatched = leg_df[~leg_df['entry_id'].isin([m['ledger_id'] for m in matched_results.values()])]
    bank_unmatched = bank_df[~bank_df['settlement_ref'].isin([m['bank_id'] for m in matched_results.values()])]

    unblocked_comparisons = len(gw_unmatched) * len(leg_unmatched) * len(bank_unmatched)
    blocked_comparisons = 0

    for _, gw in gw_unmatched.iterrows():
        best_match, best_score = None, 0.0
        gw_id = str(gw['gateway_id']).strip()
        gw_amt = float(gw['amount'])
        gw_amt_bucket = round(gw_amt, -2)
        gw_date = gw['dt'].floor('D')

        # BLOCKING: Filter ledger candidates in the same amount bucket / range
        leg_candidates = leg_unmatched[
            (leg_unmatched['gross_value'].apply(lambda x: round(x, -2)) == gw_amt_bucket) |
            (abs(gw_amt - leg_unmatched['gross_value']) < 1.0)
        ]

        # BLOCKING: Filter bank candidates in same amount bucket & within 3-day date window
        bank_candidates = bank_unmatched[
            ((bank_unmatched['credited_amount'].apply(lambda x: round(x, -2)) == gw_amt_bucket) |
             (abs(gw_amt - bank_unmatched['credited_amount']) <= (gw_amt * 0.05))) &
            (abs((bank_unmatched['dt'].dt.floor('D') - gw_date).dt.days) <= 3)
        ]

        blocked_comparisons += len(leg_candidates) * len(bank_candidates)

        for _, leg in leg_candidates.iterrows():
            for _, bank in bank_candidates.iterrows():
                features = extract_pair_features(gw, leg, bank)
                match_prob = float(matcher_model.predict_proba(features)[0][1])
                if match_prob >= 0.50 and match_prob > best_score:
                    best_score = match_prob
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

    reduction_pct = (1.0 - (blocked_comparisons / unblocked_comparisons)) * 100.0 if unblocked_comparisons > 0 else 0.0
    print(f"[Pass 2 Blocking Optimization] Unblocked candidate comparisons: {unblocked_comparisons} | Blocked candidate comparisons: {blocked_comparisons} | Complexity reduction: {reduction_pct:.2f}%")

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
        if gw_id not in matched_results and gw_id not in seen_gateway_ids:
            leg_m = leg_df[leg_df['entry_id'].astype(str).str.strip() == gw_id]
            bank_m = bank_df[bank_df['settlement_ref'].astype(str).str.strip() == gw_id]
            leg_id = str(leg_m.iloc[0]['entry_id']) if not leg_m.empty else None
            bank_id = str(bank_m.iloc[0]['settlement_ref']) if not bank_m.empty else None
            
            orphans.append({
                "gateway_id": gw_id,
                "ledger_id": leg_id,
                "bank_id": bank_id,
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
        "auto_resolved_value": round(sum(item['exposure'] for item in auto_resolved), 2),
        "human_review_count": len(human_review),
        "human_review_value": round(sum(item['exposure'] for item in human_review), 2),
        "orphan_count": len(orphans),
        "orphan_value": round(sum(item['exposure'] for item in orphans), 2),
        "duplicate_count": len(duplicates),
        "duplicate_value": round(sum(item['exposure'] for item in duplicates), 2),
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
            "duplicates": duplicates,
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
        "duplicates": duplicates,
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
    duplicates = res["duplicates"]
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

    for dup in duplicates:
        if dup["gateway_id"] == clean_id:
            return {
                "gateway_id": dup["gateway_id"],
                "original_gateway_id": dup.get("original_gateway_id"),
                "matched_pass": dup.get("matched_pass"),
                "rule_fired": dup.get("rule_fired"),
                "confidence": dup.get("confidence"),
                "expected_loss": dup.get("expected_loss"),
                "root_causes": dup.get("root_causes"),
                "exposure": dup.get("exposure"),
                "status": dup.get("status"),
                "ledger_id": dup.get("ledger_id"),
                "bank_id": dup.get("bank_id")
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
                "ledger_id": orphan.get("ledger_id"),
                "bank_id": orphan.get("bank_id")
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
        "duplicates": res["duplicates"],
        "orphans": res["orphans"],
        "exceptions_breakdown": res["exceptions_breakdown"]
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)