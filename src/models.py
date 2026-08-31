"""
Trade and Reconciliation Data Models for DerivRecon
"""
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, Any, List, Optional
from datetime import date, datetime

class AssetClass(str, Enum):
    INTEREST_RATE_SWAP = "Interest Rate Swap"
    EQUITY_OPTION = "Equity Option"
    FX_FORWARD = "FX Forward"

class BreakType(str, Enum):
    MATCHED = "MATCHED"
    ECONOMIC_BREAK = "ECONOMIC_BREAK"
    NON_ECONOMIC_BREAK = "NON_ECONOMIC_BREAK"
    TIMING_BREAK = "TIMING_BREAK"
    UNMATCHED_INTERNAL = "UNMATCHED_INTERNAL"
    UNMATCHED_COUNTERPARTY = "UNMATCHED_COUNTERPARTY"

class BreakSeverity(str, Enum):
    NONE = "NONE"
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"

class BreakStatus(str, Enum):
    UNASSIGNED = "UNASSIGNED"
    UNDER_INVESTIGATION = "UNDER_INVESTIGATION"
    ESCALATED = "ESCALATED"
    RESOLVED = "RESOLVED"
    SUPPRESSED = "SUPPRESSED"

@dataclass
class TradeRecord:
    uti: str  # Unique Trade Identifier
    trade_date: str  # YYYY-MM-DD
    settlement_date: str  # YYYY-MM-DD
    counterparty_id: str
    counterparty_name: str
    book_id: str
    trader_id: str
    asset_class: AssetClass
    notional: float
    currency: str
    direction: str  # BUY/SELL, PAY/RECEIVE
    
    # Asset Specific Details (IRS, Options, FX)
    details: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        res = {
            "uti": self.uti,
            "trade_date": self.trade_date,
            "settlement_date": self.settlement_date,
            "counterparty_id": self.counterparty_id,
            "counterparty_name": self.counterparty_name,
            "book_id": self.book_id,
            "trader_id": self.trader_id,
            "asset_class": self.asset_class.value if isinstance(self.asset_class, Enum) else self.asset_class,
            "notional": self.notional,
            "currency": self.currency,
            "direction": self.direction,
        }
        res.update(self.details)
        return res

@dataclass
class FieldDiff:
    field_name: str
    internal_val: Any
    counterparty_val: Any
    is_economic: bool
    description: str

@dataclass
class ReconResult:
    uti: str
    asset_class: str
    counterparty_name: str
    break_type: BreakType
    severity: BreakSeverity
    status: BreakStatus
    notional_internal: float
    notional_counterparty: float
    exposure_at_risk: float
    field_diffs: List[FieldDiff] = field(default_factory=list)
    internal_trade: Optional[Dict[str, Any]] = None
    counterparty_trade: Optional[Dict[str, Any]] = None
    assigned_to: Optional[str] = None
    root_cause: Optional[str] = None
    comments: List[Dict[str, str]] = field(default_factory=list)
    updated_at: str = field(default_factory=lambda: datetime.now().isoformat())

    def to_dict(self) -> Dict[str, Any]:
        return {
            "uti": self.uti,
            "asset_class": self.asset_class,
            "counterparty_name": self.counterparty_name,
            "break_type": self.break_type.value if isinstance(self.break_type, Enum) else self.break_type,
            "severity": self.severity.value if isinstance(self.severity, Enum) else self.severity,
            "status": self.status.value if isinstance(self.status, Enum) else self.status,
            "notional_internal": self.notional_internal,
            "notional_counterparty": self.notional_counterparty,
            "exposure_at_risk": round(self.exposure_at_risk, 2),
            "diff_count": len(self.field_diffs),
            "diff_fields": ", ".join([d.field_name for d in self.field_diffs]),
            "assigned_to": self.assigned_to or "Unassigned",
            "root_cause": self.root_cause or "Not Identified",
            "updated_at": self.updated_at
        }
