"""
Reconciliation & Matching Engine for DerivRecon
Handles exact matching, tolerance matching, break classification, and severity scoring.
"""
from typing import List, Dict, Any, Tuple, Optional
from src.models import (
    ReconResult, BreakType, BreakSeverity, BreakStatus, FieldDiff, AssetClass
)

ECONOMIC_FIELDS = {
    "notional", "fixed_rate", "strike_price", "forward_rate", "spot_rate",
    "option_type", "option_style", "direction", "underlying", "currency",
    "payment_frequency", "day_count_convention", "floating_index", "premium_amount"
}

NON_ECONOMIC_FIELDS = {
    "trader_id", "book_id", "counterparty_name", "counterparty_id"
}

TIMING_FIELDS = {
    "settlement_date", "trade_date", "expiration_date"
}

DEFAULT_TOLERANCE_RULES = {
    "notional": 5.0,            # $5 rounding threshold
    "fixed_rate": 0.00005,      # 0.005 bps threshold
    "forward_rate": 0.0001,     # 1 pip threshold
    "spot_rate": 0.0001,
    "strike_price": 0.01,       # 1 cent threshold
    "premium_amount": 1.0,      # $1 premium rounding
}

class ReconciliationEngine:
    def __init__(self, tolerance_rules: Optional[Dict[str, float]] = None):
        self.tolerance_rules = dict(DEFAULT_TOLERANCE_RULES)
        if tolerance_rules:
            self.tolerance_rules.update(tolerance_rules)

    def reconcile_batches(
        self, internal_trades: List[Dict[str, Any]], counterparty_trades: List[Dict[str, Any]]
    ) -> List[ReconResult]:
        """
        Reconciles a batch of internal trades against counterparty trades.
        Returns a list of ReconResult objects.
        """
        cp_trade_map = {t["uti"]: t for t in counterparty_trades if "uti" in t}
        internal_trade_map = {t["uti"]: t for t in internal_trades if "uti" in t}

        results: List[ReconResult] = []
        matched_cp_utis = set()

        for uti, int_trade in internal_trade_map.items():
            if uti in cp_trade_map:
                cp_trade = cp_trade_map[uti]
                matched_cp_utis.add(uti)
                result = self._compare_single_pair(int_trade, cp_trade)
                results.append(result)
            else:
                # Unmatched Internal Trade (Orphan in Internal OMS)
                result = ReconResult(
                    uti=uti,
                    asset_class=int_trade.get("asset_class", "UNKNOWN"),
                    counterparty_name=int_trade.get("counterparty_name", "UNKNOWN"),
                    break_type=BreakType.UNMATCHED_INTERNAL,
                    severity=BreakSeverity.HIGH,
                    status=BreakStatus.UNASSIGNED,
                    notional_internal=float(int_trade.get("notional", 0.0)),
                    notional_counterparty=0.0,
                    exposure_at_risk=float(int_trade.get("notional", 0.0)),
                    internal_trade=int_trade,
                    counterparty_trade=None,
                    field_diffs=[
                        FieldDiff(
                            field_name="uti",
                            internal_val=uti,
                            counterparty_val="MISSING_IN_COUNTERPARTY",
                            is_economic=True,
                            description="Trade present in internal OMS but missing in Counterparty feed."
                        )
                    ]
                )
                results.append(result)

        # Check for Unmatched Counterparty Trades (Orphan in CP feed)
        for uti, cp_trade in cp_trade_map.items():
            if uti not in matched_cp_utis:
                result = ReconResult(
                    uti=uti,
                    asset_class=cp_trade.get("asset_class", "UNKNOWN"),
                    counterparty_name=cp_trade.get("counterparty_name", "UNKNOWN"),
                    break_type=BreakType.UNMATCHED_COUNTERPARTY,
                    severity=BreakSeverity.HIGH,
                    status=BreakStatus.UNASSIGNED,
                    notional_internal=0.0,
                    notional_counterparty=float(cp_trade.get("notional", 0.0)),
                    exposure_at_risk=float(cp_trade.get("notional", 0.0)),
                    internal_trade=None,
                    counterparty_trade=cp_trade,
                    field_diffs=[
                        FieldDiff(
                            field_name="uti",
                            internal_val="MISSING_IN_INTERNAL_OMS",
                            counterparty_val=uti,
                            is_economic=True,
                            description="Trade confirmed by Counterparty but not found in Internal OMS."
                        )
                    ]
                )
                results.append(result)

        return results

    def _compare_single_pair(
        self, int_trade: Dict[str, Any], cp_trade: Dict[str, Any]
    ) -> ReconResult:
        uti = int_trade["uti"]
        asset_class = int_trade.get("asset_class", cp_trade.get("asset_class", "UNKNOWN"))
        cp_name = int_trade.get("counterparty_name", cp_trade.get("counterparty_name", "UNKNOWN"))
        notional_int = float(int_trade.get("notional", 0.0))
        notional_cp = float(cp_trade.get("notional", 0.0))

        # Collect all fields across both records
        all_keys = set(int_trade.keys()).union(set(cp_trade.keys()))
        field_diffs: List[FieldDiff] = []

        for key in sorted(all_keys):
            int_val = int_trade.get(key)
            cp_val = cp_trade.get(key)

            if int_val == cp_val:
                continue

            # Apply tolerance rules for numeric float/int values
            if (isinstance(int_val, (int, float)) or isinstance(cp_val, (int, float))) and int_val is not None and cp_val is not None:
                try:
                    f_int = float(int_val)
                    f_cp = float(cp_val)
                    tol = self.tolerance_rules.get(key, 1e-6)
                    if abs(f_int - f_cp) <= tol:
                        continue
                except (ValueError, TypeError):
                    pass

            # Field mismatch detected
            is_econ = key in ECONOMIC_FIELDS
            desc = f"Mismatch in {key}: Internal='{int_val}' vs CP='{cp_val}'"
            field_diffs.append(
                FieldDiff(
                    field_name=key,
                    internal_val=int_val,
                    counterparty_val=cp_val,
                    is_economic=is_econ,
                    description=desc
                )
            )

        if not field_diffs:
            return ReconResult(
                uti=uti,
                asset_class=asset_class,
                counterparty_name=cp_name,
                break_type=BreakType.MATCHED,
                severity=BreakSeverity.NONE,
                status=BreakStatus.RESOLVED,
                notional_internal=notional_int,
                notional_counterparty=notional_cp,
                exposure_at_risk=0.0,
                field_diffs=[],
                internal_trade=int_trade,
                counterparty_trade=cp_trade
            )

        # Categorize Break Type & Severity
        has_economic_break = any(d.is_economic for d in field_diffs)
        has_timing_break = any(d.field_name in TIMING_FIELDS for d in field_diffs)

        if has_economic_break:
            break_type = BreakType.ECONOMIC_BREAK
            severity = self._calculate_economic_severity(int_trade, cp_trade, field_diffs)
        elif has_timing_break:
            break_type = BreakType.TIMING_BREAK
            severity = BreakSeverity.MEDIUM
        else:
            break_type = BreakType.NON_ECONOMIC_BREAK
            severity = BreakSeverity.LOW

        exposure = self._calculate_exposure(int_trade, cp_trade, field_diffs)

        return ReconResult(
            uti=uti,
            asset_class=asset_class,
            counterparty_name=cp_name,
            break_type=break_type,
            severity=severity,
            status=BreakStatus.UNASSIGNED,
            notional_internal=notional_int,
            notional_counterparty=notional_cp,
            exposure_at_risk=exposure,
            field_diffs=field_diffs,
            internal_trade=int_trade,
            counterparty_trade=cp_trade
        )

    def _calculate_economic_severity(
        self, int_trade: Dict[str, Any], cp_trade: Dict[str, Any], diffs: List[FieldDiff]
    ) -> BreakSeverity:
        notional_int = float(int_trade.get("notional", 0.0))
        notional_cp = float(cp_trade.get("notional", 0.0))
        notional_delta = abs(notional_int - notional_cp)

        if notional_delta > 1_000_000:
            return BreakSeverity.CRITICAL
        elif notional_delta > 100_000:
            return BreakSeverity.HIGH
        
        # Check rate or strike discrepancies
        for d in diffs:
            if d.field_name in ["fixed_rate", "forward_rate"]:
                try:
                    delta = abs(float(d.internal_val) - float(d.counterparty_val))
                    if delta >= 0.0020:  # >= 20 bps or 20 pips
                        return BreakSeverity.CRITICAL
                    elif delta >= 0.0005: # >= 5 bps or 5 pips
                        return BreakSeverity.HIGH
                except (ValueError, TypeError):
                    return BreakSeverity.HIGH
            elif d.field_name == "strike_price":
                try:
                    delta = abs(float(d.internal_val) - float(d.counterparty_val))
                    base_strike = max(float(d.internal_val), 1.0)
                    rel_delta = delta / base_strike
                    if rel_delta >= 0.02 or delta >= 10.0:
                        return BreakSeverity.CRITICAL
                    elif rel_delta >= 0.005 or delta >= 2.0:
                        return BreakSeverity.HIGH
                except (ValueError, TypeError):
                    return BreakSeverity.HIGH

        return BreakSeverity.MEDIUM

    def _calculate_exposure(
        self, int_trade: Dict[str, Any], cp_trade: Dict[str, Any], diffs: List[FieldDiff]
    ) -> float:
        notional_int = float(int_trade.get("notional", 0.0))
        notional_cp = float(cp_trade.get("notional", 0.0))
        exposure = abs(notional_int - notional_cp)

        # If notional matches, check exposure from rate/strike delta over annual cashflow or option value
        if exposure < 1.0:
            for d in diffs:
                if d.field_name == "fixed_rate":
                    try:
                        rate_delta = abs(float(d.internal_val) - float(d.counterparty_val))
                        exposure = max(exposure, rate_delta * notional_int)
                    except (ValueError, TypeError):
                        pass
                elif d.field_name == "strike_price":
                    try:
                        strike_int = float(d.internal_val)
                        strike_cp = float(d.counterparty_val)
                        if strike_int > 0:
                            exposure = max(exposure, (abs(strike_int - strike_cp) / strike_int) * notional_int)
                    except (ValueError, TypeError):
                        pass
                elif d.field_name == "forward_rate":
                    try:
                        fwd_int = float(d.internal_val)
                        fwd_cp = float(d.counterparty_val)
                        if fwd_int > 0:
                            exposure = max(exposure, (abs(fwd_int - fwd_cp) / fwd_int) * notional_int)
                    except (ValueError, TypeError):
                        pass

        return round(exposure, 2)
