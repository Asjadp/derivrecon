@echo off
title DerivRecon - Derivative Trade Reconciliation System
echo ============================================================
echo   Starting DerivRecon Trade Reconciliation Dashboard...
echo ============================================================
cd /d d:\reconsilation
"C:\Python314\python.exe" -m streamlit run app.py
pause
