import pandas as pd
import numpy as np
import json
import difflib
import os
import joblib
from sklearn.model_selection import train_test_split
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import precision_score, recall_score, confusion_matrix

DATA_DIR = os.getenv("DATA_DIR", "data")
MODEL_DIR = "models"
MODEL_PATH = os.path.join(MODEL_DIR, "matcher_model.joblib")

def similarity(a, b):
    return difflib.SequenceMatcher(None, str(a).lower(), str(b).lower()).ratio()

def extract_features_and_labels(data_dir: str = DATA_DIR):
    gw_df = pd.read_csv(f"{data_dir}/gateway.csv")
    leg_df = pd.read_csv(f"{data_dir}/ledger.csv")
    bank_df = pd.read_csv(f"{data_dir}/bank.csv")
    with open(f"{data_dir}/ground_truth.json", "r") as f:
        gt = json.load(f)

    gw_df['dt'] = pd.to_datetime(gw_df['timestamp'], format='%d-%m-%Y %H:%M')
    leg_df['dt'] = pd.to_datetime(leg_df['entry_date'], format='%d.%m.%Y')
    bank_df['dt'] = pd.to_datetime(bank_df['settled_on'], format='%Y-%m-%d')

    gw_to_truth = {str(truth['expected_gateway']).strip(): truth for cid, truth in gt.items()}

    # Exclude exact Pass 1 matches to focus on Pass 2 fuzzy candidates
    pass1_gw = set()
    for _, gw in gw_df.iterrows():
        gw_id = str(gw['gateway_id']).strip()
        leg_m = leg_df[leg_df['entry_id'].astype(str).str.strip() == gw_id]
        bank_m = bank_df[bank_df['settlement_ref'].astype(str).str.strip() == gw_id]
        if not leg_m.empty and not bank_m.empty:
            pass1_gw.add(gw_id)

    gw_unmatched = gw_df[~gw_df['gateway_id'].isin(pass1_gw)]
    leg_unmatched = leg_df[~leg_df['entry_id'].isin(pass1_gw)]
    bank_unmatched = bank_df[~bank_df['settlement_ref'].isin(pass1_gw)]

    features = []
    labels = []

    for _, gw in gw_unmatched.iterrows():
        gw_id = str(gw['gateway_id']).strip()
        truth = gw_to_truth.get(gw_id)
        exp_leg = str(truth['expected_ledger']).strip() if truth and truth.get('expected_ledger') else None
        exp_bank = str(truth['expected_bank']).strip() if truth and truth.get('expected_bank') else None

        c_legs = leg_unmatched[abs(gw['amount'] - leg_unmatched['gross_value']) < 1.0]
        c_banks = bank_unmatched[abs(gw['amount'] - bank_unmatched['credited_amount']) <= (gw['amount'] * 0.05)]

        for _, leg in c_legs.iterrows():
            leg_id = str(leg['entry_id']).strip()
            amt_diff_leg = abs(gw['amount'] - leg['gross_value']) / gw['amount']
            
            for _, bank in c_banks.iterrows():
                bank_id = str(bank['settlement_ref']).strip()
                amt_diff_bank = abs(gw['amount'] - bank['credited_amount']) / gw['amount']

                amt_diff_pct = (amt_diff_leg + amt_diff_bank) / 2.0
                date_diff_days = abs((bank['dt'].normalize() - gw['dt'].normalize()).days)
                sim_leg = similarity(gw_id, leg_id)
                sim_bank = similarity(gw_id, bank_id)
                ref_sim = (sim_leg + sim_bank) / 2.0
                ref_len_diff = abs(len(gw_id) - len(leg_id)) + abs(len(gw_id) - len(bank_id))

                is_match = 1 if (exp_leg and exp_bank and leg_id.lower() == exp_leg.lower() and bank_id.lower() == exp_bank.lower()) else 0
                features.append([amt_diff_pct, date_diff_days, ref_sim, ref_len_diff])
                labels.append(is_match)

    return np.array(features), np.array(labels)

def train_and_evaluate_model(data_dir: str = DATA_DIR, save_model: bool = True):
    X, y = extract_features_and_labels(data_dir)
    
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.2, random_state=42, stratify=y
    )

    clf = LogisticRegression(random_state=42)
    clf.fit(X_train, y_train)

    y_pred = clf.predict(X_test)
    y_prob = clf.predict_proba(X_test)[:, 1]

    precision = precision_score(y_test, y_pred, zero_division=0)
    recall = recall_score(y_test, y_pred, zero_division=0)
    cm = confusion_matrix(y_test, y_pred)

    print("==================================================")
    print("      ML MATCHER: LOGISTIC REGRESSION MODEL       ")
    print("==================================================")
    print(f"Total Candidate Pairs: {len(X)}")
    print(f"Train Set Size:       {len(X_train)}")
    print(f"Test Set Size (20%):  {len(X_test)}")
    print("--------------------------------------------------")
    print(f"Precision:            {precision:.2%}")
    print(f"Recall:               {recall:.2%}")
    print("Confusion Matrix:")
    print(f"  [[TN: {cm[0][0]}, FP: {cm[0][1]}]")
    print(f"   [FN: {cm[1][0]}, TP: {cm[1][1]}]]")
    print("==================================================")

    if save_model:
        os.makedirs(MODEL_DIR, exist_ok=True)
        joblib.dump(clf, MODEL_PATH)
        print(f"Model saved successfully to '{MODEL_PATH}'.")

    return clf, {
        "precision": precision,
        "recall": recall,
        "confusion_matrix": cm.tolist()
    }

def get_matcher_model():
    if not os.path.exists(MODEL_PATH):
        clf, _ = train_and_evaluate_model(save_model=True)
        return clf
    return joblib.load(MODEL_PATH)

def extract_pair_features(gw_row, leg_row, bank_row):
    gw_id = str(gw_row['gateway_id']).strip()
    leg_id = str(leg_row['entry_id']).strip()
    bank_id = str(bank_row['settlement_ref']).strip()

    amt = gw_row['amount']
    amt_diff_leg = abs(amt - leg_row['gross_value']) / amt
    amt_diff_bank = abs(amt - bank_row['credited_amount']) / amt
    amt_diff_pct = (amt_diff_leg + amt_diff_bank) / 2.0

    date_diff_days = abs((bank_row['dt'].normalize() - gw_row['dt'].normalize()).days)

    sim_leg = similarity(gw_id, leg_id)
    sim_bank = similarity(gw_id, bank_id)
    ref_sim = (sim_leg + sim_bank) / 2.0

    ref_len_diff = abs(len(gw_id) - len(leg_id)) + abs(len(gw_id) - len(bank_id))

    return np.array([[amt_diff_pct, date_diff_days, ref_sim, ref_len_diff]])

if __name__ == "__main__":
    train_and_evaluate_model()
