"""
DerivRecon - Automated Multi-Asset Derivative Trade Reconciliation & Exception Management System
Built with Streamlit, Pandas, Plotly, and OpenPyXL.
"""
import sys
import os
import json
import re
from io import BytesIO
from typing import List, Dict, Any, Optional
from datetime import datetime

# Ensure project root is in sys.path for local and Streamlit Cloud environments
ROOT_DIR = os.path.dirname(os.path.abspath(__file__))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from openpyxl import Workbook

from src.models import (
    AssetClass, BreakType, BreakSeverity, BreakStatus,
    TradeRecord, FieldDiff, ReconResult
)
from src.recon_engine import ReconciliationEngine, DEFAULT_TOLERANCE_RULES
from src.risk_analyzer import RiskAnalyzer
from src.workflow import WorkflowManager, ROOT_CAUSE_CATEGORIES, ANALYSTS
from data.generator import generate_trade_batch, save_feeds_to_file

# ---------------------------------------------------------
# 1. PAGE CONFIGURATION & STYLING
# ---------------------------------------------------------
st.set_page_config(
    page_title="DerivRecon | Multi-Asset Derivative Reconciliation",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded"
)

st.markdown("""
    <style>
    .main-header {
        font-size: 2.1rem;
        font-weight: 700;
        color: #60A5FA;
        margin-bottom: 0.1rem;
    }
    .sub-header {
        font-size: 0.95rem;
        color: #94A3B8;
        margin-bottom: 1.2rem;
    }
    .audit-entry {
        background-color: #1E293B;
        border-left: 4px solid #38BDF8;
        padding: 0.6rem 0.8rem;
        margin-bottom: 0.5rem;
        border-radius: 0.25rem;
        color: #E2E8F0;
    }
    </style>
""", unsafe_allow_html=True)

# ---------------------------------------------------------
# 2. DATA INGESTION & SESSION INITIALIZATION
# ---------------------------------------------------------
MAX_ROW_LIMIT = 200

def parse_uploaded_trade_file(uploaded_file, max_rows: int = MAX_ROW_LIMIT) -> Tuple[List[Dict[str, Any]], bool, int]:
    """
    Parses an uploaded file (Excel, CSV, or JSON) into a list of trade dictionaries.
    Returns (trades_list, was_capped, original_total_count).
    """
    fname = uploaded_file.name.lower()
    trades = []
    
    if fname.endswith(".json"):
        content = json.load(uploaded_file)
        if isinstance(content, list):
            trades = content
        elif isinstance(content, dict) and "trades" in content:
            trades = content["trades"]
        else:
            trades = [content]
            
    elif fname.endswith((".xlsx", ".xls")):
        df = pd.read_excel(uploaded_file)
        for col in df.columns:
            if pd.api.types.is_datetime64_any_dtype(df[col]):
                df[col] = df[col].dt.strftime("%Y-%m-%d")
        trades = df.where(pd.notnull(df), None).to_dict(orient="records")
        
    elif fname.endswith(".csv"):
        df = pd.read_csv(uploaded_file)
        for col in df.columns:
            if pd.api.types.is_datetime64_any_dtype(df[col]):
                df[col] = df[col].dt.strftime("%Y-%m-%d")
        trades = df.where(pd.notnull(df), None).to_dict(orient="records")
    else:
        raise ValueError(f"Unsupported format: {fname}. Please upload Excel (.xlsx/.xls), CSV (.csv), or JSON (.json).")
    
    total_count = len(trades)
    was_capped = False
    if total_count > max_rows:
        trades = trades[:max_rows]
        was_capped = True
        
    return trades, was_capped, total_count

def load_default_trades():
    int_path = os.path.join(ROOT_DIR, "data", "internal_trades.json")
    cp_path = os.path.join(ROOT_DIR, "data", "counterparty_trades.json")
    if os.path.exists(int_path) and os.path.exists(cp_path):
        try:
            with open(int_path, "r", encoding="utf-8") as f:
                int_trades = json.load(f)
            with open(cp_path, "r", encoding="utf-8") as f:
                cp_trades = json.load(f)
            if int_trades and cp_trades:
                return int_trades[:MAX_ROW_LIMIT], cp_trades[:MAX_ROW_LIMIT]
        except Exception:
            pass
    i_t, c_t = generate_trade_batch(count=50, break_ratio=0.30)
    return i_t[:MAX_ROW_LIMIT], c_t[:MAX_ROW_LIMIT]

if "internal_trades" not in st.session_state or "cp_trades" not in st.session_state:
    int_trades, cp_trades = load_default_trades()
    st.session_state.internal_trades = int_trades
    st.session_state.cp_trades = cp_trades

if "tolerance_rules" not in st.session_state:
    st.session_state.tolerance_rules = dict(DEFAULT_TOLERANCE_RULES)

def execute_reconciliation():
    engine = ReconciliationEngine(tolerance_rules=st.session_state.tolerance_rules)
    st.session_state.recon_results = engine.reconcile_batches(
        st.session_state.internal_trades[:MAX_ROW_LIMIT],
        st.session_state.cp_trades[:MAX_ROW_LIMIT]
    )
    st.session_state.workflow = WorkflowManager(st.session_state.recon_results)

if "recon_results" not in st.session_state or "workflow" not in st.session_state:
    execute_reconciliation()

workflow: WorkflowManager = st.session_state.workflow
results: List[ReconResult] = st.session_state.recon_results

# ---------------------------------------------------------
# 3. SIDEBAR CONTROLS & FILTERS
# ---------------------------------------------------------
st.sidebar.markdown("## ⚙️ Data & Controls")

# Data Source Ingestion
data_source = st.sidebar.selectbox(
    "Data Source Mode",
    ["📁 Baseline Sample Feeds", "⚡ Synthetic Feed Generator", "📤 Upload Custom Feeds (Excel/CSV/JSON)"]
)

if data_source == "📁 Baseline Sample Feeds":
    if st.sidebar.button("🔄 Reload Baseline Feeds", key="reload_baseline"):
        int_t, cp_t = load_default_trades()
        st.session_state.internal_trades = int_t
        st.session_state.cp_trades = cp_t
        execute_reconciliation()
        st.sidebar.success(f"Loaded {len(int_t)} internal & {len(cp_t)} counterparty trades.")
        st.rerun()

elif data_source == "⚡ Synthetic Feed Generator":
    synth_count = st.sidebar.slider("Trade Count (Max 200)", 10, MAX_ROW_LIMIT, 50, step=10)
    synth_break_ratio = st.sidebar.slider("Break Probability", 0.05, 0.60, 0.30, step=0.05)
    if st.sidebar.button("🚀 Generate New Feeds", key="gen_sidebar_feed"):
        int_t, cp_t = generate_trade_batch(count=synth_count, break_ratio=synth_break_ratio)
        st.session_state.internal_trades = int_t[:MAX_ROW_LIMIT]
        st.session_state.cp_trades = cp_t[:MAX_ROW_LIMIT]
        execute_reconciliation()
        st.sidebar.success(f"Generated {len(st.session_state.internal_trades)} synthetic trades!")
        st.rerun()

elif data_source == "📤 Upload Custom Feeds (Excel/CSV/JSON)":
    st.sidebar.caption("🔒 *Performance limit: Max 200 trades processed per feed.*")
    
    upload_mode = st.sidebar.radio("Upload Format:", ["Two Separate Files", "Single 2-Sheet Excel Workbook"], horizontal=True)
    
    if upload_mode == "Two Separate Files":
        uploaded_int = st.sidebar.file_uploader(
            "1. Internal OMS File (.xlsx, .xls, .csv, .json)",
            type=["xlsx", "xls", "csv", "json"],
            key="up_int"
        )
        uploaded_cp = st.sidebar.file_uploader(
            "2. Counterparty File (.xlsx, .xls, .csv, .json)",
            type=["xlsx", "xls", "csv", "json"],
            key="up_cp"
        )
        if uploaded_int and uploaded_cp:
            if st.sidebar.button("📥 Ingest Uploaded Files", key="ingest_upload_2files"):
                try:
                    int_t, int_capped, int_tot = parse_uploaded_trade_file(uploaded_int, MAX_ROW_LIMIT)
                    cp_t, cp_capped, cp_tot = parse_uploaded_trade_file(uploaded_cp, MAX_ROW_LIMIT)
                    st.session_state.internal_trades = int_t
                    st.session_state.cp_trades = cp_t
                    execute_reconciliation()
                    
                    msg = f"Ingested {len(int_t)} internal & {len(cp_t)} CP trades!"
                    if int_capped or cp_capped:
                        msg += f" (Capped to top {MAX_ROW_LIMIT} rows from {max(int_tot, cp_tot)} total rows)."
                    st.sidebar.success(msg)
                    st.rerun()
                except Exception as e:
                    st.sidebar.error(f"Upload parse error: {e}")

    else:
        uploaded_single = st.sidebar.file_uploader(
            "Single Excel Workbook with 'Internal' & 'Counterparty' sheets",
            type=["xlsx", "xls"],
            key="up_single"
        )
        if uploaded_single:
            if st.sidebar.button("📥 Ingest Workbook", key="ingest_upload_single"):
                try:
                    xls = pd.ExcelFile(uploaded_single)
                    sheet_names_lower = {s.lower(): s for s in xls.sheet_names}
                    int_sheet = sheet_names_lower.get("internal", xls.sheet_names[0])
                    cp_sheet = sheet_names_lower.get("counterparty", xls.sheet_names[1] if len(xls.sheet_names) > 1 else xls.sheet_names[0])
                    
                    df_int = pd.read_excel(xls, sheet_name=int_sheet)
                    df_cp = pd.read_excel(xls, sheet_name=cp_sheet)
                    
                    int_t = df_int.where(pd.notnull(df_int), None).to_dict(orient="records")[:MAX_ROW_LIMIT]
                    cp_t = df_cp.where(pd.notnull(df_cp), None).to_dict(orient="records")[:MAX_ROW_LIMIT]
                    
                    st.session_state.internal_trades = int_t
                    st.session_state.cp_trades = cp_t
                    execute_reconciliation()
                    st.sidebar.success(f"Ingested {len(int_t)} internal trades ({int_sheet}) and {len(cp_t)} CP trades ({cp_sheet})!")
                    st.rerun()
                except Exception as e:
                    st.sidebar.error(f"Workbook parse error: {e}")

# Matching Tolerances
with st.sidebar.expander("🎯 Matching Tolerances", expanded=True):
    st.markdown("**Quick Presets:**")
    p_col1, p_col2, p_col3 = st.columns(3)
    with p_col1:
        if st.button("Strict", key="p_strict", help="Zero tolerance ($5, 0.05 bps, 1 pip)"):
            st.session_state.tolerance_rules = {"notional": 5.0, "fixed_rate": 0.00005, "forward_rate": 0.0001, "strike_price": 0.01}
            execute_reconciliation()
            st.rerun()
    with p_col2:
        if st.button("Medium", key="p_med", help="Absorbs micro rounding ($50, 3.5 bps, 5 pips)"):
            st.session_state.tolerance_rules = {"notional": 50.0, "fixed_rate": 0.00035, "forward_rate": 0.0005, "strike_price": 1.0}
            execute_reconciliation()
            st.rerun()
    with p_col3:
        if st.button("Lenient", key="p_len", help="Absorbs larger variances ($100, 20 bps, 45 pips, $30 strike)"):
            st.session_state.tolerance_rules = {"notional": 100.0, "fixed_rate": 0.0020, "forward_rate": 0.0045, "strike_price": 30.0}
            execute_reconciliation()
            st.rerun()

    st.markdown("---")
    st.markdown("**Custom Thresholds:**")
    curr_notional = float(st.session_state.tolerance_rules.get("notional", 5.0))
    curr_rate_bps = float(round(st.session_state.tolerance_rules.get("fixed_rate", 0.00005) * 10000, 2))
    curr_fwd_pips = float(round(st.session_state.tolerance_rules.get("forward_rate", 0.0001) * 10000, 1))
    curr_strike = float(st.session_state.tolerance_rules.get("strike_price", 0.01))

    notional_tol = st.number_input("Notional Rounding ($)", min_value=0.0, value=curr_notional, step=10.0)
    rate_tol_bps = st.number_input("Fixed Rate Tol (bps)", min_value=0.0, value=curr_rate_bps, step=0.5)
    fwd_tol_pips = st.number_input("Forward Rate Tol (pips)", min_value=0.0, value=curr_fwd_pips, step=1.0)
    strike_tol = st.number_input("Option Strike Tol ($)", min_value=0.0, value=curr_strike, step=5.0)

    if st.button("⚡ Apply Custom Tolerances", key="apply_tol"):
        st.session_state.tolerance_rules["notional"] = float(notional_tol)
        st.session_state.tolerance_rules["fixed_rate"] = float(rate_tol_bps / 10000)
        st.session_state.tolerance_rules["forward_rate"] = float(fwd_tol_pips / 10000)
        st.session_state.tolerance_rules["strike_price"] = float(strike_tol)
        execute_reconciliation()
        st.rerun()

# Ensure latest reconciliation results are in scope
results: List[ReconResult] = st.session_state.recon_results
workflow: WorkflowManager = st.session_state.workflow

st.sidebar.markdown("---")
st.sidebar.markdown("## 🔍 Filters")

all_asset_classes = [a.value for a in AssetClass]
all_severities = [s.value for s in BreakSeverity]
all_break_types = [b.value for b in BreakType]

if "filter_asset" not in st.session_state:
    st.session_state.filter_asset = all_asset_classes
if "filter_sev" not in st.session_state:
    st.session_state.filter_sev = all_severities
if "filter_type" not in st.session_state:
    st.session_state.filter_type = all_break_types

if st.sidebar.button("🔄 Reset All Filters", key="reset_filters_btn"):
    st.session_state.filter_asset = all_asset_classes
    st.session_state.filter_sev = all_severities
    st.session_state.filter_type = all_break_types
    st.rerun()

asset_filter = st.sidebar.multiselect(
    "Asset Class",
    options=all_asset_classes,
    default=st.session_state.filter_asset,
    key="ms_asset"
)

severity_filter = st.sidebar.multiselect(
    "Break Severity",
    options=all_severities,
    default=st.session_state.filter_sev,
    key="ms_sev"
)

type_filter = st.sidebar.multiselect(
    "Break Type",
    options=all_break_types,
    default=st.session_state.filter_type,
    key="ms_type"
)

search_query = st.sidebar.text_input("Search Trade UTI / Counterparty", "")

# Filter Results
filtered_results: List[ReconResult] = []
for r in results:
    ac_val = r.asset_class.value if hasattr(r.asset_class, "value") else str(r.asset_class)
    sev_val = r.severity.value if hasattr(r.severity, "value") else str(r.severity)
    type_val = r.break_type.value if hasattr(r.break_type, "value") else str(r.break_type)

    ac_match = (ac_val in asset_filter) if asset_filter else True
    sev_match = (sev_val in severity_filter) if severity_filter else True
    type_match = (type_val in type_filter) if type_filter else True
    
    search_match = True
    if search_query and search_query.strip():
        q_lower = search_query.strip().lower()
        search_match = (q_lower in r.uti.lower()) or (q_lower in r.counterparty_name.lower())
    
    if ac_match and sev_match and type_match and search_match:
        filtered_results.append(r)

# ---------------------------------------------------------
# 4. MAIN HEADER & TAB NAVIGATION
# ---------------------------------------------------------
st.markdown("<div class='main-header'>DerivRecon — Derivative Trade Reconciliation System</div>", unsafe_allow_html=True)
st.markdown("<div class='sub-header'>Institutional Middle Office Match Engine, Risk Exposure Matrix & Exception Workbench</div>", unsafe_allow_html=True)

tab1, tab2, tab3, tab4, tab5 = st.tabs([
    "📊 Risk & KPI Summary",
    "🔍 Trade Diff Inspector",
    "🛠️ Exception Workbench",
    "⚡ Synthetic Generator",
    "📄 Export Reports"
])

# =========================================================
# TAB 1: EXECUTIVE KPI & RISK ANALYTICS
# =========================================================
with tab1:
    summary = RiskAnalyzer.calculate_summary(filtered_results)
    
    col1, col2, col3, col4, col5 = st.columns(5)
    with col1:
        with st.container(border=True):
            st.metric("Total Trades", summary["total_trades"])
    with col2:
        with st.container(border=True):
            st.metric("STP Match Rate", f"{summary['stp_rate_pct']}%")
    with col3:
        with st.container(border=True):
            st.metric("Total Breaks", summary["total_breaks"])
    with col4:
        with st.container(border=True):
            st.metric("Notional at Risk ($)", f"${summary['total_exposure_at_risk']:,.2f}")
    with col5:
        with st.container(border=True):
            st.metric("Critical Breaks", summary["critical_breaks"])

    st.markdown("---")
    
    chart_col1, chart_col2 = st.columns(2)
    
    with chart_col1:
        st.subheader("Match vs Break Classification")
        break_counts: Dict[str, int] = {}
        for r in filtered_results:
            b_name = r.break_type.value if hasattr(r.break_type, "value") else str(r.break_type)
            break_counts[b_name] = break_counts.get(b_name, 0) + 1
        
        if break_counts:
            df_pie = pd.DataFrame(list(break_counts.items()), columns=["Break Type", "Count"])
            fig_pie = px.pie(
                df_pie, values="Count", names="Break Type",
                hole=0.45,
                template="plotly_dark",
                color_discrete_sequence=px.colors.qualitative.Safe
            )
            fig_pie.update_layout(
                margin=dict(t=10, b=10, l=10, r=10),
                height=320,
                paper_bgcolor="rgba(0,0,0,0)",
                plot_bgcolor="rgba(0,0,0,0)"
            )
            st.plotly_chart(fig_pie)
        else:
            st.info("No trades match the current filter selection.")

    with chart_col2:
        st.subheader("Financial Exposure by Counterparty")
        cp_exposure = RiskAnalyzer.break_distribution_by_counterparty(filtered_results)
        if cp_exposure:
            df_cp = pd.DataFrame(list(cp_exposure.items()), columns=["Counterparty", "Exposure ($)"])
            df_cp = df_cp.sort_values(by="Exposure ($)", ascending=True)
            fig_bar = px.bar(
                df_cp, x="Exposure ($)", y="Counterparty",
                orientation="h",
                color="Exposure ($)",
                template="plotly_dark",
                color_continuous_scale="Tealgrn"
            )
            fig_bar.update_layout(
                margin=dict(t=10, b=10, l=10, r=10),
                height=320,
                paper_bgcolor="rgba(0,0,0,0)",
                plot_bgcolor="rgba(0,0,0,0)"
            )
            st.plotly_chart(fig_bar)
        else:
            st.info("No exposure data available.")

    st.markdown("---")
    st.subheader("Break Distribution by Asset Class")
    asset_dist = RiskAnalyzer.break_distribution_by_asset_class(filtered_results)
    if asset_dist:
        records = []
        for ac, counts in asset_dist.items():
            for btype, count in counts.items():
                records.append({"Asset Class": ac, "Category": btype, "Count": count})
        df_stacked = pd.DataFrame(records)
        fig_stacked = px.bar(
            df_stacked, x="Asset Class", y="Count", color="Category",
            barmode="stack",
            template="plotly_dark",
            color_discrete_sequence=px.colors.qualitative.Prism
        )
        fig_stacked.update_layout(
            margin=dict(t=10, b=10, l=10, r=10),
            height=280,
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)"
        )
        st.plotly_chart(fig_stacked)

# =========================================================
# TAB 2: TRADE DIFF INSPECTOR
# =========================================================
with tab2:
    st.subheader("Side-by-Side Field Level Inspector")
    if filtered_results:
        trade_options = [
            f"{r.uti} | {r.counterparty_name} | {r.break_type.value if hasattr(r.break_type, 'value') else r.break_type}"
            for r in filtered_results
        ]
        selected_str = st.selectbox("Select Trade UTI to Inspect:", trade_options)
        selected_uti = selected_str.split(" | ")[0]
        selected_res = next(r for r in filtered_results if r.uti == selected_uti)

        # Summary Header
        m1, m2, m3, m4 = st.columns(4)
        with m1:
            st.metric("UTI", selected_res.uti)
        with m2:
            st.metric("Break Type", selected_res.break_type.value if hasattr(selected_res.break_type, "value") else str(selected_res.break_type))
        with m3:
            st.metric("Severity", selected_res.severity.value if hasattr(selected_res.severity, "value") else str(selected_res.severity))
        with m4:
            st.metric("Discrepant Fields", len(selected_res.field_diffs))

        # Discrepancy Table
        if selected_res.field_diffs:
            st.markdown("#### ⚠️ Discrepancy Breakdown")
            diff_data = [{
                "Field Name": d.field_name,
                "Internal OMS Value": str(d.internal_val),
                "Counterparty Value": str(d.counterparty_val),
                "Classification": "🔴 ECONOMIC" if d.is_economic else "🔵 NON-ECONOMIC",
                "Explanation": d.description
            } for d in selected_res.field_diffs]
            st.dataframe(pd.DataFrame(diff_data))
        else:
            st.success("✅ Clean Match: All economic and non-economic fields align within tolerance!")

        # Raw Payload Comparison
        st.markdown("#### 📋 Raw Trade Payloads")
        c_raw1, c_raw2 = st.columns(2)
        with c_raw1:
            with st.container(border=True):
                st.caption("Internal OMS Record")
                st.json(selected_res.internal_trade or {"status": "ORPHAN: MISSING IN INTERNAL OMS"})
        with c_raw2:
            with st.container(border=True):
                st.caption("Counterparty Confirmation Record")
                st.json(selected_res.counterparty_trade or {"status": "ORPHAN: MISSING IN COUNTERPARTY FEED"})
    else:
        st.warning("No trades match current filters.")

# =========================================================
# TAB 3: EXCEPTION WORKBENCH
# =========================================================
with tab3:
    st.subheader("Exception Resolution & Workflow Workbench")
    break_list = [r for r in filtered_results if r.break_type != BreakType.MATCHED]
    
    if break_list:
        # Table of open breaks
        break_df = pd.DataFrame([r.to_dict() for r in break_list])
        st.dataframe(break_df)
        
        st.markdown("---")
        st.markdown("### 📝 Resolve & Update Break")
        
        break_utis = [r.uti for r in break_list]
        selected_break_uti = st.selectbox("Select Break to Investigate:", break_utis)
        current_break = workflow.results_map[selected_break_uti]
        
        # Determine default indexes
        current_status_val = current_break.status.value if hasattr(current_break.status, "value") else str(current_break.status)
        status_options = [s.value for s in BreakStatus]
        status_idx = status_options.index(current_status_val) if current_status_val in status_options else 0

        analyst_idx = ANALYSTS.index(current_break.assigned_to) if current_break.assigned_to in ANALYSTS else 0
        root_cause_idx = ROOT_CAUSE_CATEGORIES.index(current_break.root_cause) if current_break.root_cause in ROOT_CAUSE_CATEGORIES else 0

        with st.form("break_resolution_form"):
            col_f1, col_f2 = st.columns(2)
            with col_f1:
                form_status = st.selectbox("Update Status", options=status_options, index=status_idx)
                form_analyst = st.selectbox("Assign Middle Office Analyst", options=ANALYSTS, index=analyst_idx)
            with col_f2:
                form_root_cause = st.selectbox("Root Cause Category", options=ROOT_CAUSE_CATEGORIES, index=root_cause_idx)
                form_comment = st.text_area("Audit Resolution Comment", placeholder="Document findings, counterparty contact, or fix details...")

            submitted = st.form_submit_button("💾 Save Break Update")
            if submitted:
                workflow.update_break(
                    uti=selected_break_uti,
                    status=BreakStatus(form_status),
                    assigned_to=form_analyst,
                    root_cause=form_root_cause,
                    comment=form_comment if form_comment.strip() else None,
                    author=form_analyst.split(" ")[0] if form_analyst else "Analyst"
                )
                st.success(f"Successfully updated break {selected_break_uti}!")
                st.rerun()

        # Audit History Log
        st.markdown("#### 📜 Chronological Audit Trail")
        if current_break.comments:
            for c in reversed(current_break.comments):
                st.markdown(f"""
                <div class='audit-entry'>
                    <strong>📅 {c.get('timestamp', 'N/A')} | 👤 {c.get('author', 'Ops Analyst')}</strong><br/>
                    {c.get('text', '')}
                </div>
                """, unsafe_allow_html=True)
        else:
            st.info("No audit notes recorded yet for this trade break.")
    else:
        st.success("🎉 Zero Active Breaks! All trades in the filtered scope are fully reconciled.")

# =========================================================
# TAB 4: SYNTHETIC GENERATOR & DATA MANAGEMENT
# =========================================================
with tab4:
    st.subheader("Synthetic Trade Feed Generator & Download Templates")
    st.write("Generate high-fidelity multi-asset derivative trade batches simulating realistic Middle Office capture conditions (max 200 trades).")
    
    gen_c1, gen_c2, gen_c3 = st.columns(3)
    with gen_c1:
        gen_batch_size = st.slider("Batch Size (Max 200)", 10, MAX_ROW_LIMIT, 50, step=10, key="gen_tab_size")
    with gen_c2:
        gen_ratio = st.slider("Discrepancy Ratio", 0.05, 0.75, 0.30, step=0.05, key="gen_tab_ratio")
    with gen_c3:
        save_to_disk = st.checkbox("Save to data/ directory", value=True)

    if st.button("🚀 Generate & Reconcile New Batch", key="gen_tab_btn"):
        if save_to_disk:
            int_t, cp_t = save_feeds_to_file(count=gen_batch_size)
        else:
            int_t, cp_t = generate_trade_batch(count=gen_batch_size, break_ratio=gen_ratio)
        
        st.session_state.internal_trades = int_t[:MAX_ROW_LIMIT]
        st.session_state.cp_trades = cp_t[:MAX_ROW_LIMIT]
        execute_reconciliation()
        st.success(f"Generated {len(st.session_state.internal_trades)} trade pairs with {int(gen_ratio*100)}% break injection!")
        st.rerun()

    st.markdown("---")
    st.markdown("#### 📥 Download Sample Trade Templates (Excel & JSON)")
    st.caption("Use these files as templates to populate and upload your own custom trade feeds:")
    
    # Generate Excel buffers for download
    df_int = pd.DataFrame(st.session_state.internal_trades)
    df_cp = pd.DataFrame(st.session_state.cp_trades)
    
    buf_int_xlsx = BytesIO()
    with pd.ExcelWriter(buf_int_xlsx, engine="openpyxl") as writer:
        df_int.to_excel(writer, index=False, sheet_name="InternalOMS")
    buf_int_xlsx.seek(0)
    
    buf_cp_xlsx = BytesIO()
    with pd.ExcelWriter(buf_cp_xlsx, engine="openpyxl") as writer:
        df_cp.to_excel(writer, index=False, sheet_name="Counterparty")
    buf_cp_xlsx.seek(0)

    # Combined 2-sheet workbook
    buf_combined = BytesIO()
    with pd.ExcelWriter(buf_combined, engine="openpyxl") as writer:
        df_int.to_excel(writer, index=False, sheet_name="Internal")
        df_cp.to_excel(writer, index=False, sheet_name="Counterparty")
    buf_combined.seek(0)

    col_dl_a, col_dl_b, col_dl_c = st.columns(3)
    with col_dl_a:
        st.download_button(
            "📊 Download Dual-Sheet Excel Workbook (.xlsx)",
            data=buf_combined,
            file_name="DerivRecon_Dual_Feed_Template.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
    with col_dl_b:
        st.download_button(
            "📄 Download Internal OMS Excel (.xlsx)",
            data=buf_int_xlsx,
            file_name="internal_trades.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
    with col_dl_c:
        st.download_button(
            "📄 Download Counterparty Excel (.xlsx)",
            data=buf_cp_xlsx,
            file_name="counterparty_trades.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )

    st.markdown("###### JSON Feeds:")
    c_dl1, c_dl2 = st.columns(2)
    with c_dl1:
        st.download_button(
            "⬇️ Download Internal OMS Trades JSON",
            data=json.dumps(st.session_state.internal_trades, indent=2),
            file_name="internal_trades.json",
            mime="application/json"
        )
    with c_dl2:
        st.download_button(
            "⬇️ Download Counterparty Confirmations JSON",
            data=json.dumps(st.session_state.cp_trades, indent=2),
            file_name="counterparty_trades.json",
            mime="application/json"
        )

# =========================================================
# TAB 5: EXPORT REPORTS
# =========================================================
with tab5:
    st.subheader("Generate Daily Exception Report")
    st.write("Export a clean Excel or CSV report containing all un-reconciled breaks, field diffs, exposure values, and audit status.")

    export_breaks = [r for r in filtered_results if r.break_type != BreakType.MATCHED]

    # Email Authorization Gate
    with st.container(border=True):
        st.markdown("#### 🔒 Export Authorization & Audit Requirement")
        st.caption("Enter your corporate / professional email address to unlock report generation and download.")
        
        email_col1, email_col2 = st.columns([3, 1])
        with email_col1:
            user_email = st.text_input(
                "Corporate Email Address *",
                placeholder="analyst@investmentbank.com",
                key="export_auth_email"
            )
        
        email_clean = user_email.strip()
        is_valid_email = bool(re.match(r"^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$", email_clean))

        if not email_clean:
            st.info("ℹ️ Please provide an email address to enable report download.")
        elif not is_valid_email:
            st.warning("⚠️ Please enter a valid email format (e.g., name@company.com).")
        else:
            st.success(f"✅ Authorization verified for **{email_clean}**! Reports unlocked below.")

    if is_valid_email:
        # Build Excel workbook with audit stamp
        wb = Workbook()
        ws = wb.active
        ws.title = "Break Exceptions"

        # Audit Header Banner
        ws.append(["DerivRecon Exception Audit Report"])
        ws.append([f"Generated By: {email_clean}", f"Timestamp: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"])
        ws.append([f"Total Active Breaks: {len(export_breaks)}", f"Filter Scope: {len(filtered_results)} trades evaluated"])
        ws.append([]) # Empty row

        headers = [
            "UTI", "Asset Class", "Counterparty", "Break Type", "Severity", "Status",
            "Internal Notional", "CP Notional", "Exposure at Risk ($)", "Discrepant Fields",
            "Assigned Analyst", "Root Cause", "Last Updated"
        ]
        ws.append(headers)

        for r in export_breaks:
            row = [
                r.uti,
                r.asset_class,
                r.counterparty_name,
                r.break_type.value if hasattr(r.break_type, "value") else str(r.break_type),
                r.severity.value if hasattr(r.severity, "value") else str(r.severity),
                r.status.value if hasattr(r.status, "value") else str(r.status),
                r.notional_internal,
                r.notional_counterparty,
                r.exposure_at_risk,
                ", ".join([d.field_name for d in r.field_diffs]),
                r.assigned_to or "Unassigned",
                r.root_cause or "Not Identified",
                r.updated_at
            ]
            ws.append(row)

        excel_buffer = BytesIO()
        wb.save(excel_buffer)
        excel_buffer.seek(0)

        # Build CSV dataframe
        df_export = pd.DataFrame([r.to_dict() for r in export_breaks]) if export_breaks else pd.DataFrame()
        csv_data = df_export.to_csv(index=False).encode("utf-8")

        st.markdown("#### 📥 Instant Download")
        col_exp1, col_exp2 = st.columns(2)
        with col_exp1:
            st.download_button(
                label="💾 Download Excel Exception Report (.xlsx)",
                data=excel_buffer,
                file_name="DerivRecon_Daily_Exceptions.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                key="dl_excel_btn"
            )
        with col_exp2:
            st.download_button(
                label="📄 Download CSV Exception Report (.csv)",
                data=csv_data,
                file_name="DerivRecon_Daily_Exceptions.csv",
                mime="text/csv",
                key="dl_csv_btn"
            )
