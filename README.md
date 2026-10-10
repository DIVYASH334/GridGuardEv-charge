# GridGuard: Smart EV Grid Energy & Battery Health Safeguard

Run it:
    pip install -r requirements.txt
    python engine.py                # demo scenarios
    pytest -q                       # tests
    uvicorn app:app --reload        # dashboard + API at http://localhost:8000

Files: engine.py (decision engine), optimizer.py (cheapest-hours scheduler), app.py (FastAPI),
static/index.html (dashboard), data/tariff.json (edit this to use real tariff / solar data).
