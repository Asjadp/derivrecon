"""
DerivRecon - Automated Multi-Asset Derivative Trade Reconciliation & Exception Management System
Built with Streamlit, Pandas, Plotly, and OpenPyXL.
"""
import streamlit as st
import pandas as pd
import plotly.express as px
import json
import os
import random
from datetime import date, timedelta
from typing import List, Tuple, Dict, Any, Optional
from dataclasses import dataclass, field
from enum import Enum
from io import BytesIO
from openpyxl import Workbook

# ---------------------------------------------------------
# 1. PAGE CONFIGURATION & STYLING
# ---------------------------------------------------------
st.set_page_config(
    page_title="DerivRecon | Derivative Trade Reconciliation System",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded"
)

st.markdown("""
    <style>
    .main-header {
        font-size: 2.2rem;
        font-weight: 700;
        color: #1E3A8A;
        margin-bottom: 0.2rem;
    }
    .sub-header {
        font-size: 1.0rem;
        color: #4B5563;
        margin-bottom: 1.5rem;
    }
    </style>
""", unsafe_allow_html=True)

# ---------------------------------------------------------
# 2. ENUMS & DATA MODELS
# ---------------------------------------------------------
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
    uti: str
    trade_date: str
    settlement_date: str
    counterparty_id: str
    counterparty_name: str
    book_id: str
    trader_id: str
    asset_class: AssetClass
    notional: float
    currency: str
    direction: str
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
    updated_at: str = field(default_factory=lambda: date.today().isoformat())

    def to_dict(self) -> Dict[str, Any]:
        return {
            "uti": self.uti,
            "asset_class": self.asset_class,
            "counterparty_name": self.counterparty_name,
            "break_type": self.break_type.value if isinstance(self.break_type, Enum) else str(self.break_type),
            "severity": self.severity.value if isinstance(self.severity, Enum) else str(self.severity),
            "status": self.status.value if isinstance(self.status, Enum) else str(self.status),
            "notional_internal": self.notional_internal,
            "notional_counterparty": self.notional_counterparty,
            "exposure_at_risk": round(self.exposure_at_risk, 2),
            "diff_count": len(self.field_diffs),
            "diff_fields": ", ".join([d.field_name for d in self.field_diffs]),
            "assigned_to": self.assigned_to or "Unassigned",
            "root_cause": self.root_cause or "Not Identified",
            "updated_at": self.updated_at
        }

# ---------------------------------------------------------
# 3. SYNTHETIC FEED GENERATOR
# ---------------------------------------------------------
COUNTERPARTIES = [
    ("LEI-JPM-001", "JPMorgan Chase Bank NA"),
    ("LEI-GS-002", "Goldman Sachs International"),
    ("LEI-MS-003", "Morgan Stanley & Co LLC"),
    ("LEI-BAML-004", "Bank of America Merrill Lynch"),
    ("LEI-CITI-005", "Citigroup Global Markets"),
    ("LEI-BARC-006", "Barclays Capital Inc"),
]

TRADERS = ["T_ALEXANDER", "T_BECHEL", "T_CHEN", "T_DAVIS", "T_EVANS"]
BOOKS = ["RATES_DESK_NY", "EQUITY_VOL_LDN", "FX_FORWARD_SG", "MACRO_HEDGE_01"]

def generate_trade_batch(count: int = 50, break_ratio: float = 0.30) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    random.seed(42)
    internal_trades = []
    counterparty_trades = []
    base_date = date(2026, 8, 15)

    for i in range(1, count + 1):
        uti = f"UTI-2026-DERIV-{i:04d}"
        cp_id, cp_name = random.choice(COUNTERPARTIES)
        trader = random.choice(TRADERS)
        book = random.choice(BOOKS)
        trade_dt = (base_date - timedelta(days=random.randint(0, 10))).isoformat()
        settle_dt = (base_date + timedelta(days=random.randint(30, 365))).isoformat()
        
        asset_class_choice = random.choice(list(AssetClass))
        currency = "USD"
        if asset_class_choice == AssetClass.FX_FORWARD:
            currency = random.choice(["EUR/USD", "GBP/USD", "USD/JPY"])

        notional = float(random.choice([1_000_000, 5_000_000, 10_000_000, 25_000_000, 50_000_000]))
        direction = random.choice(["PAY", "RECEIVE"]) if asset_class_choice == AssetClass.INTEREST_RATE_SWAP else random.choice(["BUY", "SELL"])

        details = {}
        if asset_class_choice == AssetClass.INTEREST_RATE_SWAP:
            details = {
                "fixed_rate": round(random.uniform(0.0300, 0.0500), 4),
                "floating_index": random.choice(["SOFR-3M", "EURIBOR-6M"]),
                "payment_frequency": random.choice(["SEMI-ANNUAL", "QUARTERLY"]),
                "day_count_convention": random.choice(["ACT/360", "30/360"])
            }
        elif asset_class_choice == AssetClass.EQUITY_OPTION:
            details = {
                "underlying": random.choice(["SPX", "AAPL", "NVDA", "TSLA"]),
                "option_type": random.choice(["CALL", "PUT"]),
                "option_style": random.choice(["EUROPEAN", "AMERICAN"]),
                "strike_price": float(random.choice([150, 200, 450, 500, 5500])),
                "expiration_date": (base_date + timedelta(days=random.randint(15, 180))).isoformat(),
                "premium_amount": round(notional * 0.025, 2)
            }
        elif asset_class_choice == AssetClass.FX_FORWARD:
            spot_rate = round(random.uniform(1.0500, 1.1200), 4)
            details = {
                "spot_rate": spot_rate,
                "forward_rate": round(spot_rate + round(random.uniform(0.0010, 0.0050), 4), 4),
                "dealt_currency": currency.split("/")[0] if "/" in currency else "USD"
            }

        internal_trade = TradeRecord(
            uti=uti, trade_date=trade_dt, settlement_date=settle_dt,
            counterparty_id=cp_id, counterparty_name=cp_name, book_id=book,
            trader_id=trader, asset_class=asset_class_choice, notional=notional,
            currency=currency, direction=direction, details=details
        ).to_dict()

        cp_trade = json.loads(json.dumps(internal_trade))

        if random.random() < break_ratio:
            break_scenario = random.choice(["ECONOMIC", "NON_ECONOMIC", "TIMING"])
            if break_scenario == "ECONOMIC":
                if random.choice(["notional", "rate"]):
                    cp_trade["notional"] = notional + random.choice([500_000, 1_000_000, -250_000])
                else:
                    if asset_class_choice == AssetClass.INTEREST_RATE_SWAP:
                        cp_trade["fixed_rate"] = round(cp_trade["fixed_rate"] + 0.0015, 4)
                    elif asset_class_choice == AssetClass.EQUITY_OPTION:
                        cp_trade["strike_price"] = cp_trade["strike_price"] + 10.0
                    elif asset_class_choice == AssetClass.FX_FORWARD:
                        cp_trade["forward_rate"] = round(cp_trade["forward_rate"] + 0.0040, 4)

            elif break_scenario == "NON_ECONOMIC":
                cp_trade["trader_id"] = f"{trader}_DESK2"

            elif break_scenario == "TIMING":
                dt_obj = date.fromisoformat(settle_dt)
                cp_trade["settlement_date"] = (dt_obj + timedelta(days=2)).isoformat()

        internal_trades.append(internal_trade)
        counterparty_trades.append(cp_trade)

    # Orphan trade breaks
    orphan_int = TradeRecord(
        uti=f"UTI-2026-DERIV-{count+1:04d}", trade_date=base_date.isoformat(),
        settlement_date=(base_date + timedelta(days=90)).isoformat(), counterparty_id="LEI-JPM-001",
        counterparty_name="JPMorgan Chase Bank NA", book_id="RATES_DESK_NY", trader_id="T_ALEXANDER",
        asset_class=AssetClass.INTEREST_RATE_SWAP, notional=15_000_000.0, currency="USD", direction="PAY",
        details={"fixed_rate": 0.0410, "floating_index": "SOFR-3M", "payment_frequency": "QUARTERLY", "day_count_convention": "ACT/360"}
    ).to_dict()

    orphan_cp = TradeRecord(
        uti=f"UTI-2026-DERIV-{count+2:04d}", trade_date=base_date.isoformat(),
        settlement_date=(base_date + timedelta(days=60)).isoformat(), counterparty_id="LEI-GS-002",
        counterparty_name="Goldman Sachs International", book_id="EQUITY_VOL_LDN", trader_id="T_CHEN",
        asset_class=AssetClass.EQUITY_OPTION, notional=8_000_000.0, currency="USD", direction="BUY",
        details={"underlying": "SPX", "option_type": "CALL", "option_style": "EUROPEAN", "strike_price": 5400.0, "expiration_date": (base_date + timedelta(days=60)).isoformat(), "premium_amount": 200000.0}
    ).to_dict()

    internal_trades.append(orphan_int)
    counterparty_trades.append(orphan_cp)
    return internal_trades, counterparty_trades

# ---------------------------------------------------------
# 4. RECONCILIATION ENGINE & RISK ANALYZER
# ---------------------------------------------------------
ECONOMIC_FIELDS = {"notional", "fixed_rate", "strike_price", "forward_rate", "option_type", "direction", "underlying", "currency"}
TIMING_FIELDS = {"settlement_date", "trade_date", "expiration_date"}

class ReconciliationEngine:
    def reconcile_batches(self, internal_trades: List[Dict[str, Any]], counterparty_trades: List[Dict[str, Any]]) -> List[ReconResult]:
        cp_trade_map = {t["uti"]: t for t in counterparty_trades if "uti" in t}
        internal_trade_map = {t["uti"]: t for t in internal_trades if "uti" in t}
        results = []
        matched_cp_utis = set()

        for uti, int_trade in internal_trade_map.items():
            if uti in cp_trade_map:
                cp_trade = cp_trade_map[uti]
                matched_cp_utis.add(uti)
                results.append(self._compare_single_pair(int_trade, cp_trade))
            else:
                results.append(ReconResult(
                    uti=uti, asset_class=int_trade.get("asset_class", "UNKNOWN"),
                    counterparty_name=int_trade.get("counterparty_name", "UNKNOWN"),
                    break_type=BreakType.UNMATCHED_INTERNAL, severity=BreakSeverity.HIGH,
                    status=BreakStatus.UNASSIGNED, notional_internal=int_trade.get("notional", 0.0),
                    notional_counterparty=0.0, exposure_at_risk=int_trade.get("notional", 0.0),
                    internal_trade=int_trade, counterparty_trade=None,
                    field_diffs=[FieldDiff("uti", uti, "MISSING_IN_COUNTERPARTY", True, "Trade present in internal OMS but missing in Counterparty feed.")]
                ))

        for uti, cp_trade in cp_trade_map.items():
            if uti not in matched_cp_utis:
                results.append(ReconResult(
                    uti=uti, asset_class=cp_trade.get("asset_class", "UNKNOWN"),
                    counterparty_name=cp_trade.get("counterparty_name", "UNKNOWN"),
                    break_type=BreakType.UNMATCHED_COUNTERPARTY, severity=BreakSeverity.HIGH,
                    status=BreakStatus.UNASSIGNED, notional_internal=0.0,
                    notional_counterparty=cp_trade.get("notional", 0.0), exposure_at_risk=cp_trade.get("notional", 0.0),
                    internal_trade=None, counterparty_trade=cp_trade,
                    field_diffs=[FieldDiff("uti", "MISSING_IN_INTERNAL_OMS", uti, True, "Trade confirmed by Counterparty but missing in Internal OMS.")]
                ))
        return results

    def _compare_single_pair(self, int_trade: Dict[str, Any], cp_trade: Dict[str, Any]) -> ReconResult:
        uti = int_trade["uti"]
        asset_class = int_trade.get("asset_class", "UNKNOWN")
        cp_name = int_trade.get("counterparty_name", "UNKNOWN")
        notional_int = float(int_trade.get("notional", 0.0))
        notional_cp = float(cp_trade.get("notional", 0.0))

        all_keys = set(int_trade.keys()).union(set(cp_trade.keys()))
        field_diffs = []

        for key in sorted(all_keys):
            int_val = int_trade.get(key)
            cp_val = cp_trade.get(key)
            if int_val == cp_val:
                continue

            if isinstance(int_val, (int, float)) and isinstance(cp_val, (int, float)):
                if abs(float(int_val) - float(cp_val)) <= 1e-4:
                    continue

            is_econ = key in ECONOMIC_FIELDS
            field_diffs.append(FieldDiff(key, int_val, cp_val, is_econ, f"Mismatch in {key}: Internal='{int_val}' vs CP='{cp_val}'"))

        if not field_diffs:
            return ReconResult(
                uti=uti, asset_class=asset_class, counterparty_name=cp_name,
                break_type=BreakType.MATCHED, severity=BreakSeverity.NONE, status=BreakStatus.RESOLVED,
                notional_internal=notional_int, notional_counterparty=notional_cp, exposure_at_risk=0.0,
                field_diffs=[], internal_trade=int_trade, counterparty_trade=cp_trade
            )

        has_economic_break = any(d.is_economic for d in field_diffs)
        has_timing_break = any(d.field_name in TIMING_FIELDS for d in field_diffs)

        if has_economic_break:
            break_type = BreakType.ECONOMIC_BREAK
            severity = BreakSeverity.CRITICAL if abs(notional_int - notional_cp) > 500_000 else BreakSeverity.HIGH
        elif has_timing_break:
            break_type = BreakType.TIMING_BREAK
            severity = BreakSeverity.MEDIUM
        else:
            break_type = BreakType.NON_ECONOMIC_BREAK
            severity = BreakSeverity.LOW

        exposure = abs(notional_int - notional_cp)
        if exposure < 1.0:
            for d in field_diffs:
                if d.field_name in ["fixed_rate", "forward_rate", "strike_price"]:
                    try:
                        exposure = abs(float(d.internal_val) - float(d.counterparty_val)) * notional_int
                    except (ValueError, TypeError):
                        exposure = 1000.0

        return ReconResult(
            uti=uti, asset_class=asset_class, counterparty_name=cp_name,
            break_type=break_type, severity=severity, status=BreakStatus.UNASSIGNED,
            notional_internal=notional_int, notional_counterparty=notional_cp, exposure_at_risk=round(exposure, 2),
            field_diffs=field_diffs, internal_trade=int_trade, counterparty_trade=cp_trade
        )

# ---------------------------------------------------------
# 5. WORKFLOW & ANALYTICS
# ---------------------------------------------------------
ROOT_CAUSE_CATEGORIES = [
    "Front Office Mis-booking", "Counterparty Confirm Discrepancy",
    "System Rounding Variance", "Reset Rate Update Delay",
    "Day Count Convention Mismatch", "Holiday Calendar Shift", "Orphan Feed Entry"
]

ANALYSTS = [
    "Alex Mercer (Senior Ops Analyst)", "Sarah Jenkins (Middle Office Specialist)",
    "David Kim (Derivative Ops Associate)", "Elena Rostova (Collateral Analyst)"
]

class WorkflowManager:
    def __init__(self, recon_results: List[ReconResult]):
        self.results_map = {r.uti: r for r in recon_results}

    def update_break(self, uti: str, status: Optional[BreakStatus] = None, assigned_to: Optional[str] = None, root_cause: Optional[str] = None, comment: Optional[str] = None) -> bool:
        if uti not in self.results_map:
            return False
        res = self.results_map[uti]
        if status: res.status = status
        if assigned_to: res.assigned_to = assigned_to
        if root_cause: res.root_cause = root_cause
        if comment:
            res.comments.append({"timestamp": date.today().isoformat(), "author": "Analyst", "text": comment})
        return True

# ---------------------------------------------------------
# 6. MAIN APPLICATION EXECUTION
# ---------------------------------------------------------
if "internal_trades" not in st.session_state or "cp_trades" not in st.session_state:
    int_t, cp_t = generate_trade_batch(50)
    st.session_state.internal_trades = int_t
    st.session_state.cp_trades = cp_t

recon_engine = ReconciliationEngine()
if "recon_results" not in st.session_state:
    st.session_state.recon_results = recon_engine.reconcile_batches(
        st.session_state.internal_trades, st.session_state.cp_trades
    )

if st.sidebar.button("🔄 Re-run Reconciliation"):
    st.session_state.recon_results = recon_engine.reconcile_batches(
        st.session_state.internal_trades, st.session_state.cp_trades
    )

results = st.session_state.recon_results
workflow = WorkflowManager(results)

# HEADER
st.markdown("<div class='main-header'>DerivRecon — Derivative Trade Reconciliation System</div>", unsafe_allow_html=True)
st.markdown("<div class='sub-header'>Middle Office Match Engine, Break Classification & Risk Workbench</div>", unsafe_allow_html=True)

# SIDEBAR FILTERS
st.sidebar.header("🔍 Filters")
asset_filter = st.sidebar.multiselect("Asset Class", options=[a.value for a in AssetClass], default=[a.value for a in AssetClass])
severity_filter = st.sidebar.multiselect("Severity", options=[s.value for s in BreakSeverity], default=[s.value for s in BreakSeverity])
type_filter = st.sidebar.multiselect("Break Type", options=[b.value for b in BreakType], default=[b.value for b in BreakType])
search_uti = st.sidebar.text_input("Search Trade UTI / Counterparty", "")

filtered_results = []
for r in results:
    ac_match = r.asset_class in asset_filter
    sev_str = r.severity.value if hasattr(r.severity, "value") else str(r.severity)
    type_str = r.break_type.value if hasattr(r.break_type, "value") else str(r.break_type)
    sev_match = sev_str in severity_filter
    type_match = type_str in type_filter
    search_match = True
    if search_uti:
        search_match = (search_uti.lower() in r.uti.lower()) or (search_uti.lower() in r.counterparty_name.lower())
    if ac_match and sev_match and type_match and search_match:
        filtered_results.append(r)

tab1, tab2, tab3, tab4, tab5 = st.tabs([
    "📊 Risk & KPI Summary",
    "🔍 Trade Diff Inspector",
    "🛠️ Exception Workbench",
    "⚡ Synthetic Feed Generator",
    "📄 Export Reports"
])

# TAB 1: SUMMARY
with tab1:
    total_trades = len(filtered_results)
    matched = [r for r in filtered_results if r.break_type == BreakType.MATCHED]
    breaks = [r for r in filtered_results if r.break_type != BreakType.MATCHED]
    stp_rate = round((len(matched) / max(total_trades, 1)) * 100, 2)
    tot_exposure = sum(r.exposure_at_risk for r in filtered_results)
    crit_count = sum(1 for r in filtered_results if r.severity == BreakSeverity.CRITICAL)

    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Total Trades", total_trades)
    c2.metric("STP Match Rate", f"{stp_rate}%")
    c3.metric("Total Breaks", len(breaks))
    c4.metric("Notional at Risk ($)", f"${tot_exposure:,.2f}")
    c5.metric("Critical Breaks", crit_count)

    st.markdown("---")
    ch1, ch2 = st.columns(2)
    with ch1:
        st.subheader("Match vs Break Composition")
        bcounts = {}
        for r in filtered_results:
            bt = r.break_type.value if hasattr(r.break_type, "value") else str(r.break_type)
            bcounts[bt] = bcounts.get(bt, 0) + 1
        df_pie = pd.DataFrame(list(bcounts.items()), columns=["Break Type", "Count"])
        st.plotly_chart(px.pie(df_pie, values="Count", names="Break Type", hole=0.4), use_container_width=True)

    with ch2:
        st.subheader("Exposure ($ Notional at Risk) by Counterparty")
        cp_exp = {}
        for r in filtered_results:
            cp_exp[r.counterparty_name] = cp_exp.get(r.counterparty_name, 0.0) + r.exposure_at_risk
        df_cp = pd.DataFrame(list(cp_exp.items()), columns=["Counterparty", "Exposure ($)"])
        st.plotly_chart(px.bar(df_cp, x="Exposure ($)", y="Counterparty", orientation="h"), use_container_width=True)

# TAB 2: INSPECTOR
with tab2:
    st.subheader("Side-by-Side Field Inspector")
    trade_options = [f"{r.uti} | {r.counterparty_name} | {r.break_type.value if hasattr(r.break_type, 'value') else r.break_type}" for r in filtered_results]
    if trade_options:
        selected_trade_str = st.selectbox("Select Trade UTI:", trade_options)
        selected_uti = selected_trade_str.split(" | ")[0]
        selected_result = next(r for r in filtered_results if r.uti == selected_uti)

        m1, m2, m3, m4 = st.columns(4)
        m1.metric("UTI", selected_result.uti)
        m2.metric("Break Type", selected_result.break_type.value if hasattr(selected_result.break_type, "value") else str(selected_result.break_type))
        m3.metric("Severity", selected_result.severity.value if hasattr(selected_result.severity, "value") else str(selected_result.severity))
        m4.metric("Discrepant Fields", len(selected_result.field_diffs))

        if selected_result.field_diffs:
            df_diffs = pd.DataFrame([{
                "Field Name": d.field_name, "Internal": str(d.internal_val),
                "Counterparty": str(d.counterparty_val), "Category": "ECONOMIC" if d.is_economic else "NON-ECONOMIC",
                "Description": d.description
            } for d in selected_result.field_diffs])
            st.dataframe(df_diffs, use_container_width=True)
        else:
            st.success("✅ Perfect Match across all trade fields!")

        r1, r2 = st.columns(2)
        r1.caption("Internal Record")
        r1.json(selected_result.internal_trade or {"status": "MISSING_IN_OMS"})
        r2.caption("Counterparty Confirmation")
        r2.json(selected_result.counterparty_trade or {"status": "MISSING_IN_CP_FEED"})
    else:
        st.warning("No trades available given active filters.")

# TAB 3: WORKBENCH
with tab3:
    st.subheader("Exception Resolution Workbench")
    break_results = [r for r in filtered_results if r.break_type != BreakType.MATCHED]
    if break_results:
        st.dataframe(pd.DataFrame([r.to_dict() for r in break_results]), use_container_width=True)
        target_uti = st.selectbox("Select Break UTI:", [r.uti for r in break_results])
        target_res = next(r for r in break_results if r.uti == target_uti)

        col_w1, col_w2 = st.columns(2)
        with col_w1:
            new_status = st.selectbox("Update Status", options=[s.value for s in BreakStatus])
            assigned_analyst = st.selectbox("Assign Analyst", options=ANALYSTS)
        with col_w2:
            root_cause = st.selectbox("Root Cause Category", options=ROOT_CAUSE_CATEGORIES)
            audit_comment = st.text_area("Audit Comment", placeholder="Enter resolution notes...")

        if st.button("💾 Save Break Update"):
            workflow.update_break(target_uti, BreakStatus(new_status), assigned_analyst, root_cause, audit_comment)
            st.success(f"Updated {target_uti}!")
            st.rerun()
    else:
        st.success("🎉 No active breaks matching filters!")

# TAB 4: GENERATOR
with tab4:
    st.subheader("Synthetic Trade Generator")
    batch_size = st.slider("Batch Size", 10, 200, 50, step=10)
    if st.button("🚀 Generate New Trade Feed"):
        int_t, cp_t = generate_trade_batch(batch_size)
        st.session_state.internal_trades = int_t
        st.session_state.cp_trades = cp_t
        st.session_state.recon_results = recon_engine.reconcile_batches(int_t, cp_t)
        st.success("Generated new feed!")
        st.rerun()

# TAB 5: EXPORT
with tab5:
    st.subheader("Export Reports")
    if st.button("📥 Download Excel Exception Report"):
        wb = Workbook()
        ws = wb.active
        ws.title = "Breaks"
        ws.append(["UTI", "Asset Class", "Counterparty", "Break Type", "Severity", "Exposure ($)", "Discrepant Fields"])
        for r in filtered_results:
            if r.break_type != BreakType.MATCHED:
                ws.append([
                    r.uti, r.asset_class, r.counterparty_name,
                    r.break_type.value if hasattr(r.break_type, "value") else str(r.break_type),
                    r.severity.value if hasattr(r.severity, "value") else str(r.severity),
                    r.exposure_at_risk, ", ".join([d.field_name for d in r.field_diffs])
                ])
        buf = BytesIO()
        wb.save(buf)
        buf.seek(0)
        st.download_button("💾 Save Excel File", data=buf, file_name="DerivRecon_Exceptions.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
