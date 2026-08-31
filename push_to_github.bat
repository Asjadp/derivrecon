@echo off
title Push DerivRecon to GitHub
echo ============================================================
echo   Pushing DerivRecon to https://github.com/asjadp/derivrecon
echo ============================================================
cd /d d:\reconsilation
git push -u origin main
echo.
echo If successful, your repository is live on GitHub!
pause
