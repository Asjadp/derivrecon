@echo off
title Work On DerivRecon Project
echo ============================================================
echo   Opening DerivRecon Workspace & Launching Application...
echo ============================================================

cd /d d:\reconsilation

echo [1/2] Opening Project in VS Code...
start "" "C:\Users\asjad\AppData\Local\Programs\Microsoft VS Code\bin\code.cmd" "d:\reconsilation"

echo [2/2] Launching Streamlit Reconciliation Server...
"C:\Python314\python.exe" -m streamlit run app.py

pause
