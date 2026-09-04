@echo off
if not exist backend\.venv python -m venv backend\.venv
backend\.venv\Scripts\pip install -r backend\requirements.txt
cd frontend
call npm install
call npm run build
cd ..
start http://localhost:8002
backend\.venv\Scripts\python -m uvicorn backend.app:app --host 0.0.0.0 --port 8002
