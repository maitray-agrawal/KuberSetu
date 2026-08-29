import os
import json
import joblib
import pytest
import ml_matcher
from ml_matcher import (
    get_matcher_model,
    compute_data_fingerprint,
    MODEL_PATH,
    MODEL_META_PATH
)

def test_missing_model_triggers_training(monkeypatch):
    # Ensure model and meta files do not exist
    if os.path.exists(MODEL_PATH):
        os.remove(MODEL_PATH)
    if os.path.exists(MODEL_META_PATH):
        os.remove(MODEL_META_PATH)

    train_called = False
    original_train = ml_matcher.train_and_evaluate_model

    def mock_train(data_dir=ml_matcher.DATA_DIR, save_model=True):
        nonlocal train_called
        train_called = True
        return original_train(data_dir=data_dir, save_model=save_model)

    monkeypatch.setattr(ml_matcher, "train_and_evaluate_model", mock_train)

    model = get_matcher_model()
    assert train_called is True
    assert model is not None
    assert os.path.exists(MODEL_PATH)
    assert os.path.exists(MODEL_META_PATH)

def test_existing_model_matching_fingerprint_reuses_model(monkeypatch):
    # Train model first to ensure matching fingerprint
    ml_matcher.train_and_evaluate_model(save_model=True)
    assert os.path.exists(MODEL_PATH)
    assert os.path.exists(MODEL_META_PATH)

    train_called = False

    def mock_train(*args, **kwargs):
        nonlocal train_called
        train_called = True
        return None, {}

    monkeypatch.setattr(ml_matcher, "train_and_evaluate_model", mock_train)

    model = get_matcher_model()
    assert train_called is False
    assert model is not None

def test_existing_model_changed_fingerprint_triggers_retraining(monkeypatch):
    ml_matcher.train_and_evaluate_model(save_model=True)

    # Modify stored fingerprint in metadata
    with open(MODEL_META_PATH, "w") as f:
        json.dump({"fingerprint": "outdated_fingerprint_hash_123"}, f)

    train_called = False
    original_train = ml_matcher.train_and_evaluate_model

    def mock_train(data_dir=ml_matcher.DATA_DIR, save_model=True):
        nonlocal train_called
        train_called = True
        return original_train(data_dir=data_dir, save_model=save_model)

    monkeypatch.setattr(ml_matcher, "train_and_evaluate_model", mock_train)

    model = get_matcher_model()
    assert train_called is True
    assert model is not None
    
    # Confirm fingerprint metadata was updated
    with open(MODEL_META_PATH, "r") as f:
        meta = json.load(f)
    assert meta["fingerprint"] == compute_data_fingerprint()

def test_existing_model_missing_metadata_triggers_retraining(monkeypatch):
    ml_matcher.train_and_evaluate_model(save_model=True)

    # Remove metadata file
    if os.path.exists(MODEL_META_PATH):
        os.remove(MODEL_META_PATH)

    train_called = False
    original_train = ml_matcher.train_and_evaluate_model

    def mock_train(data_dir=ml_matcher.DATA_DIR, save_model=True):
        nonlocal train_called
        train_called = True
        return original_train(data_dir=data_dir, save_model=save_model)

    monkeypatch.setattr(ml_matcher, "train_and_evaluate_model", mock_train)

    model = get_matcher_model()
    assert train_called is True
    assert model is not None
    assert os.path.exists(MODEL_META_PATH)
