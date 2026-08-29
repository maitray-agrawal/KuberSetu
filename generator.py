import pandas as pd
import random
import uuid
import json
import os
from datetime import datetime, timedelta

# --- CONFIGURATION ---
NUM_CANONICAL_RECORDS = 600
SEED = 42
random.seed(SEED)

DATA_DIR = "data"
os.makedirs(DATA_DIR, exist_ok=True)

# Distribution must sum to 1.0
DISTRIBUTIONS = {
    "EXACT_MATCH": 0.45,
    "TIMING_DRIFT": 0.15,
    "FEE_VARIANCE": 0.15,
    "REFERENCE_VARIANCE": 0.10,
    "DUPLICATE": 0.05,
    "GATEWAY_ONLY_ORPHAN": 0.04,
    "LEDGER_ONLY_ORPHAN": 0.03,
    "BANK_ONLY_ORPHAN": 0.03
}

# --- HELPER FUNCTIONS ---
def generate_canonical_txn():
    base_date = datetime(2026, 8, random.randint(1, 20), random.randint(0, 23), random.randint(0, 59))
    amount = round(random.uniform(500, 50000), 2)
    return {
        "canonical_id": f"TXN-{uuid.uuid4().hex[:8].upper()}",
        "merchant_id": f"M-{random.randint(100, 999)}",
        "true_amount": amount,
        "true_date": base_date,
        "fee": round(amount * 0.02, 2)
    }

def format_date(dt, system):
    if system == "gateway":
        return dt.strftime("%d-%m-%Y %H:%M")
    elif system == "ledger":
        return dt.strftime("%d.%m.%Y")
    elif system == "bank":
        return dt.strftime("%Y-%m-%d")

def fuzz_reference(ref):
    mutations = [
        lambda x: x.replace("TXN-", ""),
        lambda x: f"GW/{x}",
        lambda x: x.lower(),
        lambda x: x + " "
    ]
    return random.choice(mutations)(ref)

# --- GENERATION LOOP ---
gateway_data, ledger_data, bank_data = [], [], []
ground_truth = {}
scenario_counts = {}

choices = list(DISTRIBUTIONS.keys())
weights = list(DISTRIBUTIONS.values())

for _ in range(NUM_CANONICAL_RECORDS):
    txn = generate_canonical_txn()
    scenario = random.choices(choices, weights=weights)[0]
    scenario_counts[scenario] = scenario_counts.get(scenario, 0) + 1
    
    cid = txn["canonical_id"]
    amt = txn["true_amount"]
    fee = txn["fee"]
    dt = txn["true_date"]
    
    # Baseline: Exact match properties (Fix: bank_amt = amt by default)
    gw_ref, leg_ref, bank_ref = cid, cid, cid
    gw_amt, leg_amt, bank_amt = amt, amt, amt
    gw_dt, leg_dt, bank_dt = dt, dt, dt
    
    # Apply Scenarios
    if scenario == "TIMING_DRIFT":
        bank_dt = dt + timedelta(days=random.randint(1, 4))
    elif scenario == "FEE_VARIANCE":
        # Subtract fee + extra variance specifically for FEE_VARIANCE
        bank_amt = amt - fee - random.choice([0.05, 10.0, 5.50])
    elif scenario == "REFERENCE_VARIANCE":
        leg_ref = fuzz_reference(cid)
        bank_ref = fuzz_reference(cid)
    
    # Base Rows
    gw_row = {"gateway_id": gw_ref, "merchant": txn["merchant_id"], "amount": gw_amt, "timestamp": format_date(gw_dt, "gateway")}
    leg_row = {"entry_id": leg_ref, "account": txn["merchant_id"], "gross_value": leg_amt, "entry_date": format_date(leg_dt, "ledger")}
    bank_row = {"settlement_ref": bank_ref, "credited_amount": round(bank_amt, 2), "settled_on": format_date(bank_dt, "bank")}

    # Inject into sources based on scenario rules
    if scenario == "GATEWAY_ONLY_ORPHAN":
        gateway_data.append(gw_row)
        expected_leg, expected_bank = None, None
    elif scenario == "LEDGER_ONLY_ORPHAN":
        gateway_data.append(gw_row)
        bank_data.append(bank_row)
        expected_leg, expected_bank = None, bank_ref
    elif scenario == "BANK_ONLY_ORPHAN":
        gateway_data.append(gw_row)
        ledger_data.append(leg_row)
        expected_leg, expected_bank = leg_ref, None
    else:
        gateway_data.append(gw_row)
        ledger_data.append(leg_row)
        bank_data.append(bank_row)
        expected_leg, expected_bank = leg_ref, bank_ref
        
        if scenario == "DUPLICATE":
            # Inject a literal duplicate row into the gateway export (system glitch)
            gateway_data.append(gw_row.copy())

    # Log absolute truth
    ground_truth[cid] = {
        "scenario": scenario,
        "expected_gateway": gw_ref,
        "expected_ledger": expected_leg,
        "expected_bank": expected_bank,
        "financial_exposure": amt,
        "has_duplicate": (scenario == "DUPLICATE")
    }

# --- EXPORT ---
pd.DataFrame(gateway_data).to_csv(f"{DATA_DIR}/gateway.csv", index=False)
pd.DataFrame(ledger_data).to_csv(f"{DATA_DIR}/ledger.csv", index=False)
pd.DataFrame(bank_data).to_csv(f"{DATA_DIR}/bank.csv", index=False)

with open(f"{DATA_DIR}/ground_truth.json", "w") as f:
    json.dump(ground_truth, f, indent=4)

print(f"Generated {len(gateway_data)} Gateway, {len(ledger_data)} Ledger, and {len(bank_data)} Bank records.")
print("Scenario Distribution:")
for sc, count in sorted(scenario_counts.items()):
    print(f"  - {sc}: {count}")
print("Ground truth sealed.")