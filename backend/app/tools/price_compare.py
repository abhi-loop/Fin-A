"""compare_prices tool: best price for a product across Indian online stores.

Data comes from Serper's Google Shopping endpoint (same SERPER_API_KEY that
web_search already uses). Python does all filtering and arithmetic; no LLM.
Save as backend/app/tools/price_compare.py
"""
import json
import re
import statistics
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

from sqlalchemy.orm import Session

from ..config import SERPER_API_KEY

# Listings for these are almost never what "best price for <phone>" means.
_ACCESSORY = re.compile(
    r"\b(case|cover|protector|guard|tempered|glass|charger|adapter|cable|"
    r"strap|skin|sticker|stand|holder|pouch|sleeve|bag|refurbished|"
    r"renewed|used|pre-owned|second hand)\b", re.I)


def _search_links(query: str) -> list[dict[str, str]]:
    """Plain store-search links (no prices): used as a fallback and as extras."""
    e = urllib.parse.quote_plus(query)
    return [
        {"store": "Amazon.in", "link": f"https://www.amazon.in/s?k={e}"},
        {"store": "Flipkart", "link": f"https://www.flipkart.com/search?q={e}"},
        {"store": "Google Shopping",
         "link": f"https://www.google.com/search?tbm=shop&gl=in&q={e}"},
    ]


def _to_price(value: Any) -> float | None:
    if isinstance(value, (int, float)):
        return float(value) or None
    s = str(value or "")
    if re.search(r"[$£€]|\b(USD|EUR|GBP)\b", s):
        return None  # gl=in should give rupees; skip anything else
    m = re.search(r"(\d[\d,]*(?:\.\d+)?)", s)
    if not m:
        return None
    try:
        return float(m.group(1).replace(",", "")) or None
    except ValueError:
        return None


def _serper_shopping(query: str) -> list[dict[str, Any]]:
    payload = json.dumps({"q": query, "gl": "in", "hl": "en", "num": 30}).encode()
    req = urllib.request.Request(
        "https://google.serper.dev/shopping", data=payload,
        headers={"X-API-KEY": SERPER_API_KEY, "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=12) as resp:
        return json.loads(resp.read()).get("shopping", []) or []


def compare_prices(db: Session, user_id: int, query: str,
                   max_price: float | None = None) -> dict[str, Any]:
    """Find the best price for a product (phone, laptop, watch...) across Indian
    online stores, and how much the cheapest listing saves versus the average."""
    query = (query or "").strip()
    base: dict[str, Any] = {"query": query, "currency": "INR",
                            "search_links": _search_links(query)}
    if not query:
        return {**base, "live": False, "offers": [], "error": "No product given."}
    if not SERPER_API_KEY:
        return {**base, "live": False, "offers": [],
                "error": "SERPER_API_KEY is not configured."}

    try:
        raw = _serper_shopping(query)
    except urllib.error.HTTPError as exc:
        try:
            detail = json.loads(exc.read()).get("message", "")
        except Exception:
            detail = ""
        return {**base, "live": False, "offers": [],
                "error": f"Serper HTTP {exc.code}: {detail}".strip(": ")}
    except Exception as exc:
        return {**base, "live": False, "offers": [],
                "error": f"Price search failed: {type(exc).__name__}: {exc}"}

    q_low = query.lower()
    offers: list[dict[str, Any]] = []
    for it in raw:
        price = _to_price(it.get("price"))
        title = str(it.get("title") or "").strip()
        store = str(it.get("source") or "").strip()
        link = str(it.get("link") or "").strip()
        if not (price and title and store and link):
            continue
        # drop accessories / used units the query did not ask for
        hits = {m.group(0).lower() for m in _ACCESSORY.finditer(title)}
        if any(h not in q_low for h in hits):
            continue
        offers.append({"store": store, "title": title[:120], "price": round(price, 2),
                       "link": link, "rating": it.get("rating"),
                       "rating_count": it.get("ratingCount"),
                       "delivery": it.get("delivery"), "image": it.get("imageUrl")})

    # model numbers in the query ("15", "128") must appear in the title
    nums = re.findall(r"\d+", query)
    if nums:
        matched = [o for o in offers if all(n in o["title"] for n in nums)]
        offers = matched or offers

    # price outliers (spare parts far below, bundles far above the median)
    if len(offers) >= 4:
        med = statistics.median(o["price"] for o in offers)
        offers = [o for o in offers if 0.4 * med <= o["price"] <= 3 * med]

    note = None
    if max_price:
        within = [o for o in offers if o["price"] <= max_price]
        if within:
            offers = within
        elif offers:
            note = f"Nothing listed under Rs {round(max_price):,}; showing the cheapest available."

    # cheapest listing per store, cheapest first
    per_store: dict[str, dict[str, Any]] = {}
    for o in sorted(offers, key=lambda x: x["price"]):
        per_store.setdefault(o["store"].lower(), o)
    offers = sorted(per_store.values(), key=lambda x: x["price"])[:8]

    if not offers:
        return {**base, "live": True, "offers": [], "max_price": max_price,
                "error": "No matching listings found.", "source": "Serper Google Shopping"}

    prices = [o["price"] for o in offers]
    best, avg, high = prices[0], statistics.mean(prices), prices[-1]
    stats = {
        "count": len(offers), "best_price": round(best),
        "average_price": round(avg), "highest_price": round(high),
        "save_vs_average": round(avg - best), "save_vs_highest": round(high - best),
        "save_pct_vs_average": round((avg - best) / avg * 100, 1) if avg else 0,
    }
    return {**base, "live": True, "offers": offers, "stats": stats,
            "max_price": max_price, "note": note, "source": "Serper Google Shopping"}