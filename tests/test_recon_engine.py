"""
Unit tests for DerivRecon Reconciliation Engine
"""
import pytest
from src.models import AssetClass, BreakType, BreakSeverity, BreakStatus
from src.recon_engine import ReconciliationEngine
from src.risk_analyzer import RiskAnalyzer

@pytest.fixture
def recon_engine():
    return ReconciliationEngine()

def test_exact_match(recon_engine):
    int_trade = {
        "uti": "UTI-001",
        "asset_class": AssetClass.INTEREST_RATE_SWAP.value,
        "counterparty_name": "JPMorgan",
        "notional": 10_000_000.0,
        "fixed_rate": 0.0450,
        "settlement_date": "2026-12-31"
    }
    cp_trade = dict(int_trade)

    results = recon_engine.reconcile_batches([int_trade], [cp_trade])
    assert len(results) == 1
    res = results[0]
    assert res.break_type == BreakType.MATCHED
    assert res.severity == BreakSeverity.NONE
    assert res.exposure_at_risk == 0.0
    assert len(res.field_diffs) == 0

def test_economic_break_notional(recon_engine):
    int_trade = {
        "uti": "UTI-002",
        "asset_class": AssetClass.INTEREST_RATE_SWAP.value,
        "counterparty_name": "Goldman Sachs",
        "notional": 10_000_000.0,
        "fixed_rate": 0.0450,
        "settlement_date": "2026-12-31"
    }
    cp_trade = dict(int_trade)
    cp_trade["notional"] = 12_000_000.0

    results = recon_engine.reconcile_batches([int_trade], [cp_trade])
    assert len(results) == 1
    res = results[0]
    assert res.break_type == BreakType.ECONOMIC_BREAK
    assert res.severity == BreakSeverity.CRITICAL
    assert res.exposure_at_risk == 2_000_000.0
    assert any(d.field_name == "notional" for d in res.field_diffs)

def test_non_economic_break(recon_engine):
    int_trade = {
        "uti": "UTI-003",
        "asset_class": AssetClass.EQUITY_OPTION.value,
        "counterparty_name": "Morgan Stanley",
        "notional": 5_000_000.0,
        "trader_id": "T_ALEXANDER",
        "settlement_date": "2026-12-31"
    }
    cp_trade = dict(int_trade)
    cp_trade["trader_id"] = "T_ALEXANDER_DESK2"

    results = recon_engine.reconcile_batches([int_trade], [cp_trade])
    assert len(results) == 1
    res = results[0]
    assert res.break_type == BreakType.NON_ECONOMIC_BREAK
    assert res.severity == BreakSeverity.LOW
    assert res.exposure_at_risk == 0.0

def test_orphan_trades(recon_engine):
    int_trade = {
        "uti": "UTI-INT-ONLY",
        "asset_class": AssetClass.FX_FORWARD.value,
        "counterparty_name": "Barclays",
        "notional": 3_000_000.0
    }
    cp_trade = {
        "uti": "UTI-CP-ONLY",
        "asset_class": AssetClass.FX_FORWARD.value,
        "counterparty_name": "Barclays",
        "notional": 4_000_000.0
    }

    results = recon_engine.reconcile_batches([int_trade], [cp_trade])
    assert len(results) == 2
    btypes = [r.break_type for r in results]
    assert BreakType.UNMATCHED_INTERNAL in btypes
    assert BreakType.UNMATCHED_COUNTERPARTY in btypes

def test_risk_analyzer_summary(recon_engine):
    int_trade1 = {"uti": "UTI-01", "asset_class": "IRS", "counterparty_name": "JPM", "notional": 100.0}
    cp_trade1 = dict(int_trade1)

    int_trade2 = {"uti": "UTI-02", "asset_class": "IRS", "counterparty_name": "JPM", "notional": 100.0}
    cp_trade2 = dict(int_trade2)
    cp_trade2["notional"] = 1000.0

    results = recon_engine.reconcile_batches([int_trade1, int_trade2], [cp_trade1, cp_trade2])
    summary = RiskAnalyzer.calculate_summary(results)

    assert summary["total_trades"] == 2
    assert summary["matched_trades"] == 1
    assert summary["total_breaks"] == 1
    assert summary["stp_rate_pct"] == 50.0
    assert summary["total_exposure_at_risk"] == 900.0
