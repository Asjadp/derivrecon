"""
Exception Management & Workflow Engine for DerivRecon
Manages break resolution lifecycle, root-cause categorization, and audit logging.
"""
from typing import List, Dict, Any, Optional
from datetime import datetime
from src.models import ReconResult, BreakStatus

ROOT_CAUSE_CATEGORIES = [
    "Front Office Mis-booking",
    "Counterparty Confirm Discrepancy",
    "System Rounding Variance",
    "Reset Rate Update Delay",
    "Day Count Convention Mismatch",
    "Holiday Calendar Shift",
    "Orphan / Unmatched Feed Entry"
]

ANALYSTS = [
    "Alex Mercer (Senior Ops Analyst)",
    "Sarah Jenkins (Middle Office Specialist)",
    "David Kim (Derivative Ops Associate)",
    "Elena Rostova (Collateral & Recon Analyst)"
]

class WorkflowManager:
    def __init__(self, recon_results: List[ReconResult]):
        self.results_map: Dict[str, ReconResult] = {r.uti: r for r in recon_results}

    def update_break(
        self,
        uti: str,
        status: Optional[BreakStatus] = None,
        assigned_to: Optional[str] = None,
        root_cause: Optional[str] = None,
        comment: Optional[str] = None,
        author: str = "System User"
    ) -> bool:
        if uti not in self.results_map:
            return False

        res = self.results_map[uti]

        if status is not None:
            res.status = status
        if assigned_to is not None:
            res.assigned_to = assigned_to
        if root_cause is not None:
            res.root_cause = root_cause

        if comment:
            res.comments.append({
                "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "author": author,
                "text": comment
            })

        res.updated_at = datetime.now().isoformat()
        return True

    def get_results(self) -> List[ReconResult]:
        return list(self.results_map.values())
