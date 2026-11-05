@echo off
REM Double-click: reads every PDF in the "invoices" folder next to this file.
REM Add  --ai  after "invoices" below to read scanned invoices with Claude (needs ANTHROPIC_API_KEY).
cd /d "%~dp0"
if not exist invoices mkdir invoices
python extract.py invoices
echo.
echo The Excel report and CSV files are in the "output" folder.
pause
