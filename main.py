from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from datetime import datetime
import os
import json
from dotenv import load_dotenv

from data_loader import load_and_normalize_data
from matcher import run_matching_pipeline
from policy import apply_risk_policy

load_dotenv()

CORS_ORIGINS = os.getenv("CORS_ORIGINS", "*").split(",")
LOGS_DIR = "logs"

app = FastAPI(
    title="KuberSetu Reconciler API",
    description="Engineered 3-pass reconciliation pipeline with risk triage policy.",
    version="1.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

def run_reconciliation_logic(save_log: bool = True) -> dict:
    """
    Orchestrates dataset loading, matching pipeline, and risk policy triage.
    Optionally saves audit trail to /logs folder.
    """
    gw_df, leg_df, bank_df = load_and_normalize_data()
    matching_output = run_matching_pipeline(gw_df, leg_df, bank_df)
    results = apply_risk_policy(gw_df, leg_df, bank_df, matching_output)

    if save_log:
        os.makedirs(LOGS_DIR, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        log_filename = os.path.join(LOGS_DIR, f"reconcile_{timestamp}.json")
        with open(log_filename, "w") as f:
            json.dump(results, f, indent=2)

    return results

@app.get("/api/health")
def health_check():
    return {
        "status": "healthy",
        "service": "KuberSetu Reconciliation Engine",
        "timestamp": datetime.utcnow().isoformat()
    }

@app.get("/api/reconcile")
def reconcile():
    return run_reconciliation_logic(save_log=True)

@app.get("/api/metrics")
def get_metrics():
    results = run_reconciliation_logic(save_log=False)
    return results["metrics"]

@app.get("/api/audit/{gateway_id}")
def get_audit_trail(gateway_id: str):
    results = run_reconciliation_logic(save_log=False)
    target_id = gateway_id.strip()

    if target_id in results["matched_results"]:
        return results["matched_results"][target_id]

    for dup in results["duplicates"]:
        if dup["gateway_id"] == target_id:
            return dup

    for orphan in results["orphans"]:
        if orphan["gateway_id"] == target_id:
            return orphan

    raise HTTPException(status_code=404, detail=f"Transaction ID {gateway_id} not found in audit trail.")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)