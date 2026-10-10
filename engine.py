"""GridGuard decision engine: tariff, solar, charging plan, battery ageing, session maths."""
import json
import math
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

DATA = Path(__file__).parent / "data" / "tariff.json"
PACK_KWH, CO2_PER_KWH = 60, 0.71      # kWh pack, kg CO2 per grid kWh (illustrative)
FAST_KW, WARM_KW, SAFE_KW = 50, 35, 22
STORAGE_CAP_KW = 12
EA, R = 45_000, 8.314                  # activation energy (J/mol), gas constant


@lru_cache
def config() -> dict:
    return json.loads(DATA.read_text())


def tier(hour: float) -> str:
    h = hour % 24
    for b in config()["bands"]:
        a, e = b["start"], b["end"]
        if (a <= h < e) if a < e else (h >= a or h < e):
            return b["tier"]
    raise ValueError(f"no tariff band for hour {hour}")


def price(hour: float) -> float:
    return config()["prices"][tier(hour)]


def solar_kw(hour: float) -> float:
    cfg = config()
    if "solar_hourly_kw" in cfg:
        return float(cfg["solar_hourly_kw"][int(hour) % 24])
    return cfg["solar_peak_kw"] * math.sin(math.pi * (hour - 6) / 12) if 6 < hour < 18 else 0.0


@dataclass
class Plan:
    mode: str
    kw: float
    solar: float
    storage: float
    grid: float
    price: float


def plan(hour: float, temp_c: float) -> Plan:
    sol, peak = solar_kw(hour), tier(hour) == "peak"
    if temp_c > 42:
        mode, kw = "PROTECTED_SLOW_CHARGE", SAFE_KW
    else:
        kw = WARM_KW if temp_c >= 38 else FAST_KW
        mode = "SOLAR_PRIORITY" if peak and sol > 0 else "HYBRID_GRID_CHARGE"
    s = min(sol, kw)
    b = min(STORAGE_CAP_KW, kw - s) if peak else 0
    return Plan(mode, kw, round(s, 2), round(b, 2), round(kw - s - b, 2), price(hour))


def aging_factor(temp_c: float) -> float:
    """Arrhenius: how many times faster the pack ages than at 25 C."""
    return math.exp(EA / R * (1 / 298.15 - 1 / (temp_c + 273.15)))


def battery_life_years(temp_c: float, kw: float) -> float:
    return 10 / (aging_factor(temp_c) * (kw / SAFE_KW) ** 0.4)


def session(hour: float, temp_c: float, target_soc: int, start_soc: int = 20) -> dict:
    p = plan(hour, temp_c)
    energy = max(0.0, (target_soc - start_soc) / 100 * PACK_KWH)
    plain = energy * p.price
    smart = energy * p.grid / p.kw * p.price
    return {
        "mode": p.mode,
        "charge_kw": p.kw,
        "energy_kwh": round(energy, 1),
        "cost_saved_inr": round(plain - smart, 1),
        "co2_saved_kg": round(energy * p.solar / p.kw * CO2_PER_KWH, 2),
        "life_saved_years": round(max(0.0, battery_life_years(temp_c, p.kw) - battery_life_years(temp_c, FAST_KW)), 2),
    }


def day_profile(temp_c: float) -> list[dict]:
    rows = []
    for h in range(24):
        p = plan(h, temp_c)
        rows.append({"hour": h, "tier": tier(h), "price": p.price, "solar_kw": round(solar_kw(h), 2),
                     "mode": p.mode, "charge_kw": p.kw, "grid_kw": p.grid})
    return rows


def ambient_c(hour: float) -> float:
    return 32 + 5 * math.sin(2 * math.pi * (hour - 9) / 24)


def charging_efficiency(kw: float, temp_c: float) -> float:
    """Share of grid energy that ends up stored; heat and high current waste more."""
    return max(0.80, 0.97 - 0.004 * max(0.0, temp_c - 30) - 0.0006 * max(0.0, kw - SAFE_KW))


def charge_session(hour: float, temp_c: float, start_soc: float, target_soc: float, steps: int = 20) -> dict:
    """Simulate one full charge, step by step, and report what happened (same maths as the dashboard's ON switch)."""
    step_kwh = (target_soc - start_soc) / 100 * PACK_KWH / steps
    stored = hours = drawn = paid = saved = co2 = clean = 0.0
    for _ in range(steps):
        p = plan(hour, temp_c)
        temp_c = round(temp_c + (ambient_c(hour) + 0.22 * p.kw - temp_c) * 0.3, 1)
        p = plan(hour, temp_c)
        eff = charging_efficiency(p.kw, temp_c)
        stored += step_kwh
        hours += step_kwh / p.kw
        hour = (hour + step_kwh / p.kw) % 24
        drawn += step_kwh / eff
        paid += step_kwh / eff * p.grid / p.kw * p.price
        saved += step_kwh * p.price * (1 - p.grid / p.kw)
        co2 += step_kwh * p.solar / p.kw * CO2_PER_KWH
        clean += step_kwh * (p.solar + p.storage) / p.kw
    return {"start_soc": start_soc, "end_soc": target_soc, "energy_added_kwh": round(stored, 1),
            "avg_power_kw": round(stored / hours, 1), "efficiency_pct": round(stored / drawn * 100, 1),
            "energy_drawn_kwh": round(drawn, 1), "heat_loss_kwh": round(drawn - stored, 1),
            "clean_share_pct": round(clean / stored * 100, 1), "cost_inr": round(paid, 1),
            "saved_inr": round(saved, 1), "co2_saved_kg": round(co2, 1), "final_temp_c": temp_c}


if __name__ == "__main__":
    demo = {"Extreme heat": (14, 46, 85), "Midnight low tariff": (1, 30, 90),
            "Evening peak": (19, 36, 80), "Sunny noon": (12, 33, 70)}
    for name, args in demo.items():
        print(f"{name:20}", session(*args))
    print("\nQuick charge (2 PM, 46 C, 30% to 85%):", charge_session(14, 46, 30, 85))
