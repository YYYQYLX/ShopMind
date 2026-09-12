@echo off
chcp 65001 >nul
cd /d "%~dp0"

rem OpenBLAS allocates a buffer per CPU thread. On some machines that allocation
rem fails and Streamlit exits right after startup with:
rem     OpenBLAS error: Memory allocation still failed after 10 retries, giving up.
rem Limiting it to one thread avoids the problem. The dataset here is tiny,
rem so there is no noticeable slowdown.
set OPENBLAS_NUM_THREADS=1
set OMP_NUM_THREADS=1

echo Starting ShopMind, opening http://localhost:8501
echo Keep this window open while using it. Closing it stops the server.
echo.

streamlit run app.py

pause
