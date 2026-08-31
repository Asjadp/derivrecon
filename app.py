"""
DerivRecon - Automated Multi-Asset Derivative Trade Reconciliation & Exception Management Dashboard
Built with Streamlit, Pandas, Plotly, and OpenPyXL.
"""
import sys
import os
import json
from io import BytesIO

# Ensure project root is in python path for Linux / Streamlit Cloud deployment
base_dir = os.path.dirname(os.path.abspath(__file__))
if base_dir not in sys.path:
    sys.path.insert(0, base_dir)

import streamlit as st

# Streamlit Page Config MUST be the very first Streamlit call
st.set_page_config(
    page_title="DerivRecon | Derivative Trade Reconciliation & Exception Management",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded"
)

try:
    import pandas as pd
    import plotly.express as px
    from openpyxl import Workbook

    try:
        from src.models import BreakType, BreakSeverity, BreakStatus, AssetClass
        from src.recon_engine import ReconciliationEngine
        from src.risk_analyzer import RiskAnalyzer
        from src.workflow import WorkflowManager, ROOT_CAUSE_CATEGORIES, ANALYSTS
        from data.generator import save_feeds_to_file, generate_trade_batch
    except ImportError:
        from models import BreakType, BreakSeverity, BreakStatus, AssetClass
        from recon_engine import ReconciliationEngine
        from risk_analyzer import RiskAnalyzer
        from workflow import WorkflowManager, ROOT_CAUSE_CATEGORIES, ANALYSTS
        from generator import save_feeds_to_file, generate_trade_batch

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
    DATA_DIR = os.path.join(base_dir, "data")
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
        try:
            return save_feeds_to_file(INT_FILE, CP_FILE, count=50)
        except Exception:
            return generate_trade_batch(count=50)

    if "internal_trades" not in st.session_state or "cp_trades" not in st.session_state:
        st.session_state.internal_trades, st.session_state.cp_trades = load_data()

    # Run Reconciliation Engine
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
                        "Field Name": d.field_name,
                        "Internal Value": str(d.internal_val),
                        "Counterparty Value": str(d.counterparty_val),
                        "Field Category": "ECONOMIC" if d.is_economic else "NON-ECONOMIC",
                        "Description": d.description
                    })
                df_diffs = pd.DataFrame(diff_data)
                st.dataframe(df_diffs, use_container_width=True)
            else:
                st.success("✅ Perfect Match! No field discrepancies detected across internal and counterparty records.")

            st.markdown("### Complete Trade Records")
            c1, c2 = st.columns(2)
            with c1:
                st.caption("Internal OMS Record")
                st.json(selected_result.internal_trade or {"status": "MISSING_IN_INTERNAL_OMS"})
            with c2:
                st.caption("Counterparty Confirmation Record")
                st.json(selected_result.counterparty_trade or {"status": "MISSING_IN_COUNTERPARTY_FEED"})
        else:
            st.warning("No trades available for inspection matching the active filters.")


    # ==========================================
    # TAB 3: EXCEPTION WORKBENCH
    # ==========================================
    with tab3:
        st.subheader("Exception Resolution & Workflow Manager")
        
        # Table of all breaks
        break_results = [r for r in filtered_results if r.break_type != BreakType.MATCHED]
        if not break_results:
            st.success("🎉 No active breaks matching current filters!")
        else:
            df_workbench = pd.DataFrame([r.to_dict() for r in break_results])
            st.dataframe(df_workbench, use_container_width=True)

            st.markdown("---")
            st.markdown("### Update Break Action")

            col_w1, col_w2 = st.columns(2)
            
            break_utis = [r.uti for r in break_results]
            target_uti = col_w1.selectbox("Select Break UTI to Manage:", break_utis)
            target_res = next(r for r in break_results if r.uti == target_uti)

            with col_w1:
                curr_status_str = target_res.status.value if hasattr(target_res.status, "value") else str(target_res.status)
                status_options = [s.value for s in BreakStatus]
                status_idx = status_options.index(curr_status_str) if curr_status_str in status_options else 0
                new_status = st.selectbox("Update Status", options=status_options, index=status_idx)
                
                assigned_analyst = st.selectbox("Assign Analyst", options=ANALYSTS)
            
            with col_w2:
                root_cause = st.selectbox("Root Cause Category", options=ROOT_CAUSE_CATEGORIES)
                audit_comment = st.text_area("Audit Comment / Note", placeholder="Enter investigation notes or resolution details...")

            if st.button("💾 Save Break Update"):
                status_enum = BreakStatus(new_status)
                workflow.update_break(
                    uti=target_uti,
                    status=status_enum,
                    assigned_to=assigned_analyst,
                    root_cause=root_cause,
                    comment=audit_comment,
                    author="Derivative Analyst User"
                )
                st.success(f"Successfully updated break {target_uti}!")
                st.rerun()

            # Audit Trail View
            st.markdown(f"#### Audit Log for {target_uti}")
            if target_res.comments:
                for c in target_res.comments:
                    st.write(f"⏱️ **{c['timestamp']}** | **{c['author']}**: {c['text']}")
            else:
                st.caption("No audit comments logged yet for this UTI.")


    # ==========================================
    # TAB 4: SYNTHETIC FEED GENERATOR
    # ==========================================
    with tab4:
        st.subheader("Synthetic Trade Feed Generator")
        st.write("Generate custom trade feeds to test reconciliation performance under different market break conditions.")

        g_col1, g_col2 = st.columns(2)
        with g_col1:
            batch_size = st.slider("Number of Trades in Batch", 10, 200, 50, step=10)
        with g_col2:
            break_pct = st.slider("Injected Break Rate (%)", 5, 80, 30, step=5)

        if st.button("🚀 Generate New Trade Batch & Reconcile"):
            save_feeds_to_file(INT_FILE, CP_FILE, count=batch_size)
            st.session_state.internal_trades, st.session_state.cp_trades = load_data()
            st.session_state.recon_results = recon_engine.reconcile_batches(
                st.session_state.internal_trades, st.session_state.cp_trades
            )
            st.success(f"Generated new feed with {batch_size} trades and re-executed reconciliation!")
            st.rerun()


    # ==========================================
    # TAB 5: EXPORT REPORTS
    # ==========================================
    with tab5:
        st.subheader("Generate Daily Exception Report")
        st.write("Export a clean Excel report containing all un-reconciled breaks, field diffs, exposure values, and audit status.")

        if st.button("📥 Download Excel Exception Report"):
            wb = Workbook()
            ws = wb.active
            ws.title = "Break Exceptions"

            # Headers
            headers = ["UTI", "Asset Class", "Counterparty", "Break Type", "Severity", "Status", "Internal Notional", "CP Notional", "Exposure at Risk ($)", "Discrepant Fields", "Assigned Analyst", "Root Cause"]
            ws.append(headers)

            for r in filtered_results:
                if r.break_type != BreakType.MATCHED:
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
                        r.root_cause or "Not Identified"
                    ]
                    ws.append(row)

            output = BytesIO()
            wb.save(output)
            output.seek(0)

            st.download_button(
                label="💾 Save Excel File",
                data=output,
                file_name="DerivRecon_Daily_Exception_Report.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )

except Exception as err:
    st.error(f"Application Execution Error: {err}")
    st.exception(err)
