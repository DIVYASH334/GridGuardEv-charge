"""Picks the cheapest hours inside a plug-in window to deliver the energy a trip needs."""
from engine import PACK_KWH, config, plan


def _label(h: int) -> str:
    return f"{h % 12 or 12} {'AM' if h % 24 < 12 else 'PM'}"


def _ranges(hours: list[int]) -> list[str]:
    out, run = [], []
    for h in hours:
        if run and h != (run[-1] + 1) % 24:
            out.append(run)
            run = []
        run.append(h)
    if run:
        out.append(run)
    return [f"{_label(r[0])} to {_label((r[-1] + 1) % 24)}" for r in out]


def schedule(plug_in: int, deadline: int, soc_from: int, soc_to: int, temp_c: float) -> dict:
    energy = max(0.0, (soc_to - soc_from) / 100 * PACK_KWH)
    off_price = config()["prices"]["off"]
    window = ((deadline - plug_in) % 24) or 24
    slots = []
    for i in range(window):
        hr = (plug_in + i) % 24
        p = plan(hr, temp_c)
        # solar is free; storage was charged off-peak, so it costs the off-peak rate
        eff = (p.grid * p.price + p.storage * off_price) / p.kw
        slots.append({"i": i, "hour": hr, "kw": p.kw, "eff": eff, "price": p.price})

    remaining, picks = energy, []
    for s in sorted(slots, key=lambda s: (s["eff"], s["i"])):
        if remaining <= 1e-9:
            break
        kwh = min(s["kw"], remaining)
        picks.append({**s, "kwh": kwh})
        remaining -= kwh
    feasible = remaining <= 1e-9
    smart = sum(s["kwh"] * s["eff"] for s in picks)

    remaining, plain = energy, 0.0          # plain = start now, all from grid
    for s in slots:
        kwh = min(s["kw"], remaining)
        plain += kwh * s["price"]
        remaining -= kwh

    picks.sort(key=lambda s: s["i"])
    hours = [s["hour"] for s in picks]
    return {"feasible": feasible, "energy_kwh": round(energy, 1), "hours": hours, "ranges": _ranges(hours),
            "smart_cost_inr": round(smart, 1), "plain_cost_inr": round(plain, 1),
            "saved_inr": round(plain - smart, 1)}
