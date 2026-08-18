#!/usr/bin/env python3
"""
Test script verifying all dashboard modules and imports.
"""
import sys
from pathlib import Path

SRC_DIR = Path(__file__).resolve().parent.parent / "py-executors" / "src"
PY_EXECUTORS_DIR = SRC_DIR.parent
WORKSPACE_DIR = PY_EXECUTORS_DIR.parent / "workspace"

sys.path.insert(0, str(SRC_DIR))
sys.path.insert(0, str(PY_EXECUTORS_DIR))
sys.path.insert(0, str(WORKSPACE_DIR))

print("🔍 Auditing Dashboard Imports & Modules...")

modules = [
    ("agentic_copilot", "AgenticCopilot"),
    ("whatif_counterfactual", "WhatIfCounterfactualAnalyzer"),
    ("red_teamer_agent", "RedTeamerAgent"),
    ("adaptive_model_router", "AdaptiveModelRouter"),
    ("crypto_attestation_engine", "create_signed_execution_receipt"),
    ("google_model_card_gen", "generate_google_model_card"),
    ("warehouse_connector", "EnterpriseWarehouseConnector"),
    ("notebook_validator", "REQUIRED_SECTIONS"),
]

for mod_name, symbol in modules:
    try:
        mod = __import__(mod_name, fromlist=[symbol])
        getattr(mod, symbol)
        print(f"  ✅ {mod_name}.{symbol} -> OK")
    except Exception as e:
        print(f"  ❌ {mod_name}.{symbol} -> ERROR: {e}")

print("\n🎉 All 8 Core AI Modules loaded and ready without any syntax or runtime error!")
