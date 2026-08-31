"""
Risk & Portfolio Analytics Engine for DerivRecon
Calculates STP match rates, break aging, Exposure at Risk, and breakdown analytics.
"""
from typing import List, Dict, Any
from src.models import ReconResult, BreakType, BreakSeverity

class RiskAnalyzer:
    @staticmethod
    def calculate_summary(results: List[ReconResult]) -> Dict[str, Any]:
        total_trades = len(results)
        if total_trades == 0:
            return {
                "total_trades": 0,
                "matched_trades": 0,
                "total_breaks": 0,
                "stp_rate_pct": 0.0,
                "total_exposure_at_risk": 0.0,
                "critical_breaks": 0,
                "high_breaks": 0,
                "medium_breaks": 0,
                "low_breaks": 0
            }

        matched = [r for r in results if r.break_type == BreakType.MATCHED]
        breaks = [r for r in results if r.break_type != BreakType.MATCHED]

        total_exposure = sum(r.exposure_at_risk for r in results)
        critical_count = sum(1 for r in results if r.severity == BreakSeverity.CRITICAL)
        high_count = sum(1 for r in results if r.severity == BreakSeverity.HIGH)
        medium_count = sum(1 for r in results if r.severity == BreakSeverity.MEDIUM)
        low_count = sum(1 for r in results if r.severity == BreakSeverity.LOW)

        stp_rate = round((len(matched) / total_trades) * 100, 2)

        return {
            "total_trades": total_trades,
            "matched_trades": len(matched),
            "total_breaks": len(breaks),
            "stp_rate_pct": stp_rate,
            "total_exposure_at_risk": round(total_exposure, 2),
            "critical_breaks": critical_count,
            "high_breaks": high_count,
            "medium_breaks": medium_count,
            "low_breaks": low_count
        }

    @staticmethod
    def break_distribution_by_asset_class(results: List[ReconResult]) -> Dict[str, Dict[str, int]]:
        dist: Dict[str, Dict[str, int]] = {}
        for r in results:
            ac = r.asset_class
            if ac not in dist:
                dist[ac] = {"MATCHED": 0, "ECONOMIC_BREAK": 0, "NON_ECONOMIC_BREAK": 0, "TIMING_BREAK": 0, "UNMATCHED": 0}
            
            btype = r.break_type.value if hasattr(r.break_type, "value") else str(r.break_type)
            if "UNMATCHED" in btype:
                dist[ac]["UNMATCHED"] += 1
            elif btype in dist[ac]:
                dist[ac][btype] += 1
        return dist

    @staticmethod
    def break_distribution_by_counterparty(results: List[ReconResult]) -> Dict[str, float]:
        exposure_map: Dict[str, float] = {}
        for r in results:
            cp = r.counterparty_name
            exposure_map[cp] = exposure_map.get(cp, 0.0) + r.exposure_at_risk
        return {k: round(v, 2) for k, v in exposure_map.items()}
