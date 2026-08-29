import pandas as pd
import os

DATA_DIR = os.getenv("DATA_DIR", "data")

def load_and_normalize_data(data_dir: str = DATA_DIR):
    """
    Loads gateway, ledger, and bank CSV datasets from data_dir and parses/normalizes timestamps.
    """
    gw_df = pd.read_csv(f"{data_dir}/gateway.csv")
    leg_df = pd.read_csv(f"{data_dir}/ledger.csv")
    bank_df = pd.read_csv(f"{data_dir}/bank.csv")
    
    gw_df['dt'] = pd.to_datetime(gw_df['timestamp'], format='%d-%m-%Y %H:%M')
    leg_df['dt'] = pd.to_datetime(leg_df['entry_date'], format='%d.%m.%Y')
    bank_df['dt'] = pd.to_datetime(bank_df['settled_on'], format='%Y-%m-%d')

    return gw_df, leg_df, bank_df
