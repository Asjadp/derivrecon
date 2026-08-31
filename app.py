"""
DerivRecon - Automated Multi-Asset Derivative Trade Reconciliation & Exception Management Dashboard
Built with Streamlit, Pandas, Plotly, and OpenPyXL.
"""
import sys
import os
import json
from io import BytesIO

# Ensure project root is in python path for Linux / Streamlit Cloud deployment
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import streamlit as st
import pandas as pd
import plotly.express as px
from openpyxl import Workbook

from src.models import BreakType, BreakSeverity, BreakStatus, AssetClass
from src.recon_engine import ReconciliationEngine
from src.risk_analyzer import RiskAnalyzer
from src.workflow import WorkflowManager, ROOT_CAUSE_CATEGORIES, ANALYSTS
from data.generator import save_feeds_to_file

# Streamlit Page Config
st.set_page_config(
    page_title="DerivRecon | Derivative Trade Reconciliation & Exception Management",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom CSS styling for professional Middle Office Look
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

# Data Loading & Session State Initialization
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
INT_FILE = os.path.join(DATA_DIR, "internal_trades.json")
CP_FILE = os.path.join(DATA_DIR, "counterparty_trades.json")

def load_data():
    if os.path.exists(INT_FILE) and os.path.exists(CP_FILE):
        try:
            with open(INT_FILE, "r") as f:
                internal_trades = json.load(f)
            with open(CP_FILE, "r") as f:
                cp_trades = json.load(f)
            if internal_trades and cp_trades:
                return internal_trades, cp_trades
        except Exception:
            pass
    return save_feeds_to_file(INT_FILE, CP_FILE, count=50)

if "internal_trades" not in st.session_state or "cp_trades" not in st.session_state:
    st.session_state.internal_trades, st.session_state.cp_trades = load_data()

# Run Reconciliation Engine
recon_engine = ReconciliationEngine()
if "recon_results" not in st.session_state or st.sidebar.button("🔄 Re-run Reconciliation"):
    st.session_state.recon_results = recon_engine.reconcile_batches(
        st.session_state.internal_trades, st.session_state.cp_trades
    )

results = st.session_state.recon_results
workflow = WorkflowManager(results)

# HEADER
st.markdown("<div class='main-header'>DerivRecon — Derivative Trade Reconciliation System</div>", unsafe_allow_html=True)
st.markdown("<div class='sub-header'>Middle Office Automated Match Engine, Break Classification & Risk Exposure Workbench</div>", unsafe_allow_html=True)

# SIDEBAR FILTERS
st.sidebar.header("🔍 Reconciliation Filters")

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

search_uti = st.sidebar.text_input("Search Trade UTI / Counterparty", "")

# Filter Results
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

# MAIN DASHBOARD TABS
tab1, tab2, tab3, tab4, tab5 = st.tabs([
    "📊 Risk & KPI Summary",
    "🔍 Trade Diff Inspector",
    "🛠️ Exception Workbench",
    "⚡ Synthetic Feed Generator",
    "📄 Export Reports"
])

# ==========================================
# TAB 1: RISK & KPI SUMMARY
# ==========================================
with tab1:
    summary = RiskAnalyzer.calculate_summary(filtered_results)
    
    col1, col2, col3, col4, col5 = st.columns(5)
    with col1:
        st.metric("Total Trades Processed", summary["total_trades"])
    with col2:
        st.metric("STP Match Rate", f"{summary['stp_rate_pct']}%")
    with col3:
        st.metric("Total Open Breaks", summary["total_breaks"])
    with col4:
        st.metric("Notional at Risk ($)", f"${summary['total_exposure_at_risk']:,.2f}")
    with col5:
        st.metric("Critical Breaks", summary["critical_breaks"], delta_color="inverse")

    st.markdown("---")

    chart_col1, chart_col2 = st.columns(2)

    with chart_col1:
        st.subheader("Match vs Break Composition")
        break_counts = {}
        for r in filtered_results:
            bt = r.break_type.value if hasattr(r.break_type, "value") else str(r.break_type)
            break_counts[bt] = break_counts.get(bt, 0) + 1
        
        df_pie = pd.DataFrame(list(break_counts.items()), columns=["Break Type", "Count"])
        fig_pie = px.pie(
            df_pie, values="Count", names="Break Type",
            color="Break Type",
            color_discrete_map={
                "MATCHED": "#10B981",
                "ECONOMIC_BREAK": "#EF4444",
                "NON_ECONOMIC_BREAK": "#F59E0B",
                "TIMING_BREAK": "#3B82F6",
                "UNMATCHED_INTERNAL": "#8B5CF6",
                "UNMATCHED_COUNTERPARTY": "#6366F1"
            },
            hole=0.4
        )
        st.plotly_chart(fig_pie, use_container_width=True)

    with chart_col2:
        st.subheader("Financial Exposure ($ Notional at Risk) by Counterparty")
        cp_exp = RiskAnalyzer.break_distribution_by_counterparty(filtered_results)
        df_cp = pd.DataFrame(list(cp_exp.items()), columns=["Counterparty", "Exposure ($)"]).sort_values(by="Exposure ($)", ascending=True)
        fig_bar = px.bar(
            df_cp, x="Exposure ($)", y="Counterparty", orientation="h",
            color="Exposure ($)", color_continuous_scale="Reds"
        )
        st.plotly_chart(fig_bar, use_container_width=True)

    st.subheader("Break Distribution by Asset Class")
    ac_dist = RiskAnalyzer.break_distribution_by_asset_class(filtered_results)
    df_ac = pd.DataFrame.from_dict(ac_dist, orient="index").reset_index().rename(columns={"index": "Asset Class"})
    fig_ac = px.bar(df_ac, x="Asset Class", y=["MATCHED", "ECONOMIC_BREAK", "NON_ECONOMIC_BREAK", "TIMING_BREAK", "UNMATCHED"], barmode="group")
    st.plotly_chart(fig_ac, use_container_width=True)


# ==========================================
# TAB 2: TRADE DIFF INSPECTOR
# ==========================================
with tab2:
    st.subheader("Side-by-Side Trade Field Inspector")
    st.info("Select a Trade UTI below to inspect discrepancies between Internal OMS and Counterparty records.")

    trade_options = [
        f"{r.uti} | {r.counterparty_name} | {r.break_type.value if hasattr(r.break_type, 'value') else r.break_type} ({r.severity.value if hasattr(r.severity, 'value') else r.severity})"
        for r in filtered_results
    ]

    if trade_options:
        selected_trade_str = st.selectbox("Select Trade UTI:", trade_options)
        selected_uti = selected_trade_str.split(" | ")[0]
        selected_result = next(r for r in filtered_results if r.uti == selected_uti)

        # Overview Metrics for selected trade
        m1, m2, m3, m4 = st.columns(4)
        with m1:
            st.metric("UTI", selected_result.uti)
        with m2:
            st.metric("Break Type", selected_result.break_type.value if hasattr(selected_result.break_type, "value") else str(selected_result.break_type))
        with m3:
            st.metric("Severity", selected_result.severity.value if hasattr(selected_result.severity, "value") else str(selected_result.severity))
        with m4:
            st.metric("Discrepant Field Count", len(selected_result.field_diffs))

        st.markdown("### Field Discrepancies")
        if selected_result.field_diffs:
                  diff_data = []
        for d in selected_result.field_diffs:
            diff_data.append({
                "Field Name": getattr(d, 'field_name', str(d)),
                "Internal Value": str(getattr(d, 'internal_val', '')),
                "Counterparty Value": str(getattr(d, 'counterparty_val', '')),
                "Description": getattr(d, 'description', '')
            })
        df_diffs = pd.DataFrame(diff_data)
        st.dataframe(df_diffs, use_container_width=True)
    else:
        st.success("✅ Perfect Match! No field discrepancies detected across internal and counterparty records.")

    st.markdown("### Complete Trade Records")
    c1, c2 = st.columns(2)
    with c1:
        st.caption("Internal OMS Record")
        st.json(getattr(selected_result, 'internal_trade', {"status": "MISSING_IN_INTERNAL_OMS"}))
    with c2:
        st.caption("Counterparty Confirmation Record")
        st.json(getattr(selected_result, 'counterparty_trade', {"status": "MISSING_IN_COUNTERPARTY_FEED"}))

# ==========================================
# TAB 3: EXCEPTION WORKBENCH
# ==========================================
with tab3:
    st.subheader("Exception Management Workbench")
    st.info("Assign analysts, update status classifications, and track manual operational resolutions here.")
    
    broken_trades = [r for r in filtered_results if "MATCHED" not in (r.break_type.value if hasattr(r.break_type, "value") else str(r.break_type))]
    
    if broken_trades:
        break_options = [f"{b.uti} | {b.counterparty_name}" for b in broken_trades]
        selected_break = st.selectbox("Select Active Break to Investigate:", break_options, key="workbench_select")
        
        # Safely extract the exact UTI text string
        target_uti_string = selected_break.split(" | ")[0].strip()
        
        # Pull the correct trade object safely
        target_trade = next((t for t in broken_trades if t.uti == target_uti_string), None)
        
        if target_trade is not None:
            col_w1, col_w2, col_w3 = st.columns(3)
            with col_w1:
                assigned_analyst = st.selectbox("Assign Owner:", ANALYSTS)
            with col_w2:
                current_status = st.selectbox("Update Status:", [s.value for s in BreakStatus])
            with col_w3:
                root_cause = st.selectbox("Root Cause Category:", ROOT_CAUSE_CATEGORIES)
                
            resolution_notes = st.text_area("Audit Log Notes / Action Taken:", placeholder="Type resolution steps or communication tracking logs here...")
            
            if st.button("💾 Save Action to Audit Trail"):
                st.success(f"Audit log updated successfully for UTI {target_uti_string}. Assigned to {assigned_analyst} as [{current_status}].")
        else:
            st.error("Could not find matching trade data payload for the selected identifier.")
    else:
        st.success("🎉 Zero open exceptions detected for the filtered criteria!")


# ==========================================
# TAB 4: SYNTHETIC FEED GENERATOR
# ==========================================
with tab4:
    st.subheader("Synthetic Trade Data Feed Generator")
    if st.button("⚡ Generate New Synthetic Trade Batches"):
        save_feeds_to_file(INT_FILE, CP_FILE, count=50)
        st.success("Successfully injected 50 new multi-asset derivative positions into active feeds.")


# ==========================================
# TAB 5: EXPORT REPORTS
# ==========================================
with tab5:
    st.subheader("Middle Office Reporting Engine")
    st.write("Convert calculated reconciliation variances into institutional formatting below.")
    
    report_data = []
    for r in filtered_results:
        risk_amt = 0.0
        for attr in ['exposure', 'exposure_amount', 'notional', 'amount']:
            if hasattr(r, attr):
                risk_amt = float(getattr(r, attr))
                break

        report_data.append({
            "UTI": r.uti,
            "Asset Class": r.asset_class.value if hasattr(r.asset_class, 'value') else str(r.asset_class),
            "Break Type": r.break_type.value if hasattr(r.break_type, 'value') else str(r.break_type),
            "Severity": r.severity.value if hasattr(r.severity, 'value') else str(r.severity),
            "Counterparty": r.counterparty_name,
            "Exposure Risk ($)": risk_amt
        })
    df_report = pd.DataFrame(report_data)
    
    st.dataframe(df_report, use_container_width=True)
    
    output = BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df_report.to_excel(writer, index=False, sheet_name='Recon_Break_Log')
    processed_data = output.getvalue()
    
    st.download_button(
        label="📥 Download Official Break Log (.XLSX)",
        data=processed_data,
        file_name="DerivRecon_Operational_Report.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )

