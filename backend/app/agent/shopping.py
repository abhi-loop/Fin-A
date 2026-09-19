"""Shopping path: best-price comparison for a product (deterministic, no LLM).

Save as backend/app/agent/shopping.py
"""
import math
import re
from typing import Any

from sqlalchemy.orm import Session

from ..tools import finance_tools as T
from .router import RouterResult


def _rs(n: Any) -> str:
    s = str(round(abs(float(n or 0))))
    if len(s) > 3:
        s = re.sub(r"(\d)(?=(\d\d)+$)", r"\1,", s[:-3]) + "," + s[-3:]
    return "Rs " + s


def _out(answer: str, comparison: dict | None = None, metrics: list | None = None,
         insights: list | None = None, sources: list | None = None,
         tools: list | None = None) -> dict[str, Any]:
    return {
        "answer": answer,
        "metrics": metrics or [],
        "insights": insights or [],
        "sources": sources or [],
        "tools_used": tools or [],
        "intent": "price_compare",
        "alert_fired": False,
        "comparison": comparison,
    }


def handle(db: Session, user_id: int, route: RouterResult) -> dict[str, Any]:
    e = route.entities or {}
    product = str(e.get("product") or "").strip()
    try:
        max_price = float(e["max_price"]) if e.get("max_price") else None
    except (TypeError, ValueError):
        max_price = None

    if not product:
        return _out("Tell me which product to compare, for example "
                    "\"best price for iPhone 15\" or \"cheapest laptop under 60k\".")

    try:
        res = T.run_tool("compare_prices", db, user_id,
                         query=product, max_price=max_price)
    except Exception as exc:
        res = {"query": product, "live": False, "offers": [], "search_links": [],
               "error": f"{type(exc).__name__}: {exc}"}

    offers = res.get("offers") or []
    stats = res.get("stats")

    # ── No usable prices: still hand the user working store links ────────────
    if not offers or not stats:
        why = res.get("error") or "no listings were returned"
        print(f"[shopping] compare_prices({product!r}) gave no offers: {why}", flush=True)
        return _out(
            f"I couldn't get live prices for \"{product}\" right now ({why}). "
            f"You can compare directly on these stores:",
            comparison={**res, "offers": [], "affordability": None},
            sources=["Store search links"], tools=["compare_prices"])

    best = offers[0]

    # ── Can the user afford the best price? (Python arithmetic) ──────────────
    sim = T.simulate_purchase(db, user_id, best["price"])
    savings = T.get_savings_rate(db, user_id)["savings"]
    affordable = bool(sim["affordable"])
    months = None
    if not affordable and savings and savings > 0:
        months = math.ceil(-sim["remaining_after"] / savings) if sim["remaining_after"] < 0 else 1

    afford_line = (
        f"You can afford it and would still have {_rs(sim['remaining_after'])} "
        f"after your upcoming expenses."
        if affordable else
        f"It is more than your available money after upcoming expenses "
        f"({_rs(sim['balance'] - sim['upcoming_expenses'])})"
        + (f"; at your current savings of {_rs(savings)}/month that is about "
           f"{months} month(s) away." if months else "."))

    answer = (f"Best price for {product}: {_rs(best['price'])} at {best['store']}.")
    if stats["count"] > 1 and stats["save_vs_average"] > 0:
        answer += (f" That is {_rs(stats['save_vs_average'])} "
                   f"({stats['save_pct_vs_average']}%) below the average of "
                   f"{_rs(stats['average_price'])} across {stats['count']} stores.")
    answer += " " + afford_line

    comparison = {**res, "affordability": {
        "affordable": affordable, "remaining_after": sim["remaining_after"],
        "balance": sim["balance"], "months_to_afford": months}}

    return _out(
        answer, comparison,
        metrics=[
            {"label": "Best Price", "value": _rs(best["price"])},
            {"label": "You Save vs Avg", "value": _rs(stats["save_vs_average"])},
            {"label": "Stores Compared", "value": str(stats["count"])},
            {"label": "Affordable", "value": "Yes" if affordable else "Not yet"},
        ],
        insights=[
            f"Priciest listing is {_rs(stats['highest_price'])}, so the best deal "
            f"saves {_rs(stats['save_vs_highest'])} against it.",
            "Prices come from Google Shopping at the time you asked; "
            "check stock and delivery on the store page.",
        ],
        sources=["Google Shopping (Serper)", "Balance & Upcoming Expenses"],
        tools=["compare_prices", "simulate_purchase", "get_savings_rate"])