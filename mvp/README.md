# Kisan Direct AI – MVP

A runnable starter marketplace for farmers and customers with AI-assisted crop price and demand estimates.

## Stack
- Frontend: HTML, CSS, vanilla JavaScript
- Backend: Python + FastAPI
- Database: SQLite (created automatically)
- ML: scikit-learn RandomForest models trained on generated demonstration data

> The included data is synthetic demo data. Predictions are demonstrations, not live mandi prices or guaranteed outcomes. Connect verified mandi/APMC and weather datasets before using this for real decisions.

## Run locally

### 1. Backend
```bash
cd backend
python -m venv .venv
# Windows:
.venv\Scripts\activate
# macOS/Linux:
source .venv/bin/activate
pip install -r requirements.txt
uvicorn main:app --reload
```
Backend: http://127.0.0.1:8000  
API docs: http://127.0.0.1:8000/docs

### 2. Frontend
Open `frontend/index.html` in your browser. If your browser blocks local API requests, run:
```bash
cd frontend
python -m http.server 5500
```
Then open http://127.0.0.1:5500

## Demo accounts
Register a farmer or customer from the app. This MVP stores accounts and products in SQLite. Passwords are hashed.

## AI endpoints
- `POST /api/predict/price`
- `POST /api/predict/demand`

## Next production steps
1. Replace synthetic training data with verified historical mandi prices.
2. Add district/APMC-specific datasets, crop seasonality and weather observations.
3. Evaluate models on held-out chronological data and show prediction intervals.
4. Add secure JWT sessions, email/OTP verification, payment gateway and image storage.
5. Deploy backend and frontend; configure CORS and HTTPS.
