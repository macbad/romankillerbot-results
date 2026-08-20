@echo off
cd /d "%~dp0"
py -3 export_dashboard.py
start "" http://localhost:8765
py -3 -m http.server 8765 --directory docs
