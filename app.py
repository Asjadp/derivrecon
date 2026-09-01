"""
DerivRecon - Automated Multi-Asset Derivative Trade Reconciliation & Exception Management System
Built with Streamlit, Pandas, Plotly, and OpenPyXL.
"""
import sys
import os
import json
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
                return int_trades, cp_trades
        except Exception:
            pass
    return generate_trade_batch(count=50, break_ratio=0.30)

if "internal_trades" not in st.session_state or "cp_trades" not in st.session_state:
    int_trades, cp_trades = load_default_trades()
    st.session_state.internal_trades = int_trades
    st.session_state.cp_trades = cp_trades

if "tolerance_rules" not in st.session_state:
    st.session_state.tolerance_rules = dict(DEFAULT_TOLERANCE_RULES)

def execute_reconciliation():
    engine = ReconciliationEngine(tolerance_rules=st.session_state.tolerance_rules)
    st.session_state.recon_results = engine.reconcile_batches(
        st.session_state.internal_trades,
        st.session_state.cp_trades
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
    ["📁 Baseline Sample Feeds", "⚡ Synthetic Feed Generator", "📤 Upload Custom Feeds"]
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
    synth_count = st.sidebar.slider("Trade Count", 10, 200, 50, step=10)
    synth_break_ratio = st.sidebar.slider("Break Probability", 0.05, 0.60, 0.30, step=0.05)
    if st.sidebar.button("🚀 Generate New Feeds", key="gen_sidebar_feed"):
        int_t, cp_t = generate_trade_batch(count=synth_count, break_ratio=synth_break_ratio)
        st.session_state.internal_trades = int_t
        st.session_state.cp_trades = cp_t
        execute_reconciliation()
        st.sidebar.success(f"Generated {synth_count} synthetic trades!")
        st.rerun()

elif data_source == "📤 Upload Custom Feeds":
    st.sidebar.caption("Upload JSON feeds matching TradeRecord schema:")
    uploaded_int = st.sidebar.file_uploader("Internal OMS Trades (JSON)", type=["json"], key="up_int")
    uploaded_cp = st.sidebar.file_uploader("Counterparty Feeds (JSON)", type=["json"], key="up_cp")
    if uploaded_int and uploaded_cp:
        if st.sidebar.button("📥 Ingest Uploaded Feeds", key="ingest_upload"):
            try:
                int_t = json.load(uploaded_int)
                cp_t = json.load(uploaded_cp)
                st.session_state.internal_trades = int_t
                st.session_state.cp_trades = cp_t
                execute_reconciliation()
                st.sidebar.success(f"Ingested {len(int_t)} internal & {len(cp_t)} CP trades!")
                st.rerun()
            except Exception as e:
                st.sidebar.error(f"Upload parse error: {e}")

# Matching Tolerances
with st.sidebar.expander("🎯 Matching Tolerances", expanded=False):
    notional_tol = st.number_input("Notional Rounding ($)", min_value=0.0, value=float(st.session_state.tolerance_rules.get("notional", 5.0)), step=1.0)
    rate_tol_bps = st.number_input("Fixed Rate Tol (bps)", min_value=0.0, value=float(round(st.session_state.tolerance_rules.get("fixed_rate", 0.00005) * 10000, 3)), step=0.1)
    fwd_tol_pips = st.number_input("Forward Rate Tol (pips)", min_value=0.0, value=float(round(st.session_state.tolerance_rules.get("forward_rate", 0.0001) * 10000, 1)), step=0.5)
    
    if st.button("Apply Tolerances", key="apply_tol"):
        st.session_state.tolerance_rules["notional"] = float(notional_tol)
        st.session_state.tolerance_rules["fixed_rate"] = float(rate_tol_bps / 10000)
        st.session_state.tolerance_rules["forward_rate"] = float(fwd_tol_pips / 10000)
        execute_reconciliation()
        st.success("Tolerances updated & reconciliation re-run!")
        st.rerun()

st.sidebar.markdown("---")
st.sidebar.markdown("## 🔍 Filters")

asset_filter = st.sidebar.multiselect(
    "Asset Class",
    options=[a.value for a in AssetClass],
    default=[a.value for a in AssetClass]
)

severity_filter = st.sidebar.multiselect(
    "Break Severity",
    options=[s.value for s in BreakSeverity],
    default=[s.value for s in BreakSeverity]
)

type_filter = st.sidebar.multiselect(
    "Break Type",
    options=[b.value for b in BreakType],
    default=[b.value for b in BreakType]
)

search_query = st.sidebar.text_input("Search Trade UTI / Counterparty", "")

# Filter Results
filtered_results: List[ReconResult] = []
for r in results:
    ac_match = r.asset_class in asset_filter
    sev_str = r.severity.value if hasattr(r.severity, "value") else str(r.severity)
    type_str = r.break_type.value if hasattr(r.break_type, "value") else str(r.break_type)
    sev_match = sev_str in severity_filter
    type_match = type_str in type_filter
    
    search_match = True
    if search_query:
        query_lower = search_query.strip().lower()
        search_match = (query_lower in r.uti.lower()) or (query_lower in r.counterparty_name.lower())
    
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
    st.subheader("Synthetic Trade Feed Generator")
    st.write("Generate high-fidelity multi-asset derivative trade batches simulating realistic Middle Office capture conditions.")
    
    gen_c1, gen_c2, gen_c3 = st.columns(3)
    with gen_c1:
        gen_batch_size = st.slider("Batch Size (Number of Trades)", 10, 500, 50, step=10, key="gen_tab_size")
    with gen_c2:
        gen_ratio = st.slider("Discrepancy Ratio", 0.05, 0.75, 0.30, step=0.05, key="gen_tab_ratio")
    with gen_c3:
        save_to_disk = st.checkbox("Save to data/ directory", value=True)

    if st.button("🚀 Generate & Reconcile New Batch", key="gen_tab_btn"):
        if save_to_disk:
            int_t, cp_t = save_feeds_to_file(count=gen_batch_size)
        else:
            int_t, cp_t = generate_trade_batch(count=gen_batch_size, break_ratio=gen_ratio)
        
        st.session_state.internal_trades = int_t
        st.session_state.cp_trades = cp_t
        execute_reconciliation()
        st.success(f"Generated {gen_batch_size} trade pairs with {int(gen_ratio*100)}% break injection!")
        st.rerun()

    st.markdown("---")
    st.markdown("#### 📥 Download Raw Synthetic Trade Feeds (JSON)")
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
    
    # Build Excel workbook
    wb = Workbook()
    ws = wb.active
    ws.title = "Break Exceptions"

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
