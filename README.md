# `DerivRecon`: Automated Multi-Asset Derivative Trade Reconciliation & Exception System

`DerivRecon` is an enterprise-grade trade capture verification, automated multi-asset derivative reconciliation, and exception management platform. Built to simulate institutional Middle Office operations at investment banks and hedge funds, it matches internal Order Management System (OMS) trade records against counterparty and clearinghouse confirmation feeds (e.g., DTCC, MarkitWire, CME).

---

## 🎯 Key Features & Capabilities

- **Multi-Asset Trade Economics**: Supports **Interest Rate Swaps (IRS)**, **Equity Options**, and **FX Forwards** including fixed/floating legs, payment frequencies, day count fractions (`ACT/360`, `30/360`), option strikes/expiries, and forward rates.
- **Multi-Tier Matching Engine**:
  - **Exact UTI Match**: Validates primary Unique Trade Identifiers.
  - **Tolerance Matching**: Handles floating-point rounding variance (e.g. ±$5.00 notional rounding or ±0.1 bps interest rate tolerance).
  - **Orphan Trade Detection**: Flags un-confirmed internal trades or un-matched counterparty entries.
- **Automated Break Classification & Severity Matrix**:
  - **Economic Breaks (CRITICAL / HIGH)**: Discrepancies in Notional, Fixed Rate, Option Strike, or FX Forward Rate.
  - **Timing Breaks (MEDIUM)**: Settlement date or trade execution timing shifts.
  - **Non-Economic Breaks (LOW)**: Trader ID formatting or book code variance.
- **Financial Exposure Engine**: Quantifies exact **Notional at Risk ($)** and annual cashflow delta for open breaks.
- **Interactive Exception Workbench**:
  - Assign breaks to Middle Office analysts.
  - Categorize root causes (*Front Office Mis-booking*, *Reset Rate Delay*, *Day Count Mismatch*, etc.).
  - Append time-stamped audit comments.
- **Executive KPI & Reporting**: Live Streamlit dashboard with STP match rate %, break aging charts, and automated Excel export.

---

## 🏗️ Project Architecture

```
d:/reconsilation/
├── README.md                           # Documentation & Interview Talking Points Guide
├── app.py                              # Streamlit Main Dashboard Entry Point
├── data/
│   ├── generator.py                    # Multi-Asset Synthetic Trade Generator
│   ├── internal_trades.json            # Mock Internal OMS Feed
│   └── counterparty_trades.json        # Mock Counterparty/Clearing Feed
├── src/
│   ├── __init__.py
│   ├── models.py                       # Pydantic & Dataclass Trade Models
│   ├── recon_engine.py                 # Multi-Tier Matching Engine & Severity Matrix
│   ├── risk_analyzer.py                # Financial Exposure & Notional-at-Risk Calculator
│   └── workflow.py                     # Break State Management & Audit Log Engine
└── tests/
    └── test_recon_engine.py            # Pytest Automated Test Suite
```

---

## 🚀 Quick Start Guide

### 1. Run Automated Test Suite
```bash
python -m pytest tests/
```

### 2. Generate Fresh Synthetic Trade Feeds
```bash
python -m data.generator
```

### 3. Launch Interactive Dashboard
```bash
streamlit run app.py
```

---

## 💼 How to Pitch This Project in Job Interviews

When interviewing for **Derivative Analyst**, **Trade Support**, or **Middle Office Operations** roles, highlight this project to stand out from other candidates:

### 1. Executive Elevator Pitch
> *"To complement my financial knowledge, I built `DerivRecon` — an automated multi-asset trade reconciliation engine. It simulates an institutional Middle Office workflow by matching internal OMS records against counterparty clearing feeds for Interest Rate Swaps, Options, and FX Forwards. It automatically categorizes breaks into Economic vs Non-Economic issues and calculates the financial exposure at risk."*

### 2. Demonstrating Understanding of Trade Economics
> *"I designed the system to evaluate key economic attributes such as day count conventions (ACT/360 vs 30/360), reset rates, fixed vs floating legs, and option strikes. Rather than just doing exact string matching, I implemented tolerance logic for interest rate variances down to 0.1 bps and small notional rounding differences."*

### 3. Demonstrating Risk Management & Root Cause Analysis
> *"In Middle Office, not all breaks carry equal risk. My engine ranks breaks by severity based on dollar exposure. It also features a complete Exception Workbench where analysts can assign breaks, log root cause categories like FO mis-bookings or reset rate delays, and maintain an audit log for compliance."*
