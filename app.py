"""FastAPI backend. Run: uvicorn app:app --reload  then open http://localhost:8000"""
from pathlib import Path

from fastapi import FastAPI, Query
from fastapi.responses import FileResponse

import engine
from optimizer import schedule

app = FastAPI(title="GridGuard API")
HOUR = Query(..., ge=0, lt=24)
TEMP = Query(35, ge=20, le=60)


@app.get("/api/health")
def health():
    return {"status": "ok"}


@app.get("/api/plan")
def get_plan(hour: float = HOUR, temp: float = TEMP):
    return {**engine.plan(hour, temp).__dict__, "tier": engine.tier(hour)}


@app.get("/api/session")
def get_session(hour: float = HOUR, temp: float = TEMP, soc: int = Query(80, ge=21, le=100)):
    return engine.session(hour, temp, soc)


@app.get("/api/day")
def get_day(temp: float = TEMP):
    return engine.day_profile(temp)


@app.get("/api/schedule")
def get_schedule(plug_in: int = Query(18, ge=0, lt=24), deadline: int = Query(7, ge=0, lt=24),
                 soc_from: int = Query(20, ge=0, le=99), soc_to: int = Query(80, ge=1, le=100), temp: float = TEMP):
    return schedule(plug_in, deadline, soc_from, soc_to, temp)


@app.get("/api/charge")
def charge(hour: float = HOUR, temp: float = TEMP, start_soc: int = Query(30, ge=0, le=99), target_soc: int = Query(80, ge=1, le=100)):
    return engine.charge_session(hour, temp, start_soc, target_soc)


@app.get("/")
def home():
    return FileResponse(Path(__file__).parent / "static" / "index.html")
