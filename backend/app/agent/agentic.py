"""Agentic Path — investment / goal / IPO decisions + Confidence Scorer.

Flow:
  1. Evidence gathering (Python executes the tools, every time)
     get_user_profile + web_search + get_spending_history
  2. Confidence Scorer (Gemini call)
     -> verdict, confidence, reasoning, caveats, optional alert
  3. Guardrails (deterministic, the LLM cannot override them)
     - amount > balance            -> insufficient_funds
     - "buy" on non-live market data -> confidence capped at 60
  4. Optional alert -> alerts table
  5. Return a ChatOut-compatible dict (the Recommendation object)

Falls back to a rules-based path when Gemini is unavailable. The fallback ALSO
calls web_search, and every fallback reason is printed as "[agentic] ...".
"""

import json
import os
import re
import traceback
from typing import Any

from sqlalchemy.orm import Session

from ..config import GEMINI_API_KEY
from ..models import Alert
from ..tools import finance_tools as T
from .prompts import CONFIDENCE_SCORER_PROMPT
from .router import RouterResult

GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.6-flash")

VERDICTS = {"buy", "hold", "avoid", "insufficient_funds"}


# ─── Small helpers ────────────────────────────────────────────────────────────


def _log(msg: str) -> None:
    print(f"[agentic] {msg}", flush=True)


def _rs(n: Any) -> str:
    """Format an amount as Indian rupees (1,00,000 style)."""
    s = str(round(abs(float(n or 0))))
    if len(s) > 3:
        s = re.sub(r"(\d)(?=(\d\d)+$)", r"\1,", s[:-3]) + "," + s[-3:]
    return "Rs " + s


def _to_int(v: Any, default: int = 50) -> int:
    try:
        return max(0, min(100, int(float(str(v).replace("%", "").strip()))))
    except (TypeError, ValueError):
        return default


def _as_list(v: Any) -> list[str]:
    if isinstance(v, list):
        return [str(x) for x in v if x]
    return [str(v)] if v else []


def _extract_json(text: str) -> dict[str, Any] | None:
    """Extract a JSON object from an LLM response."""
    text = re.sub(r"^```(?:json)?|```$", "", text.strip(), flags=re.M).strip()
    try:
        out = json.loads(text)
        return out if isinstance(out, dict) else None
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", text, re.S)
        if match:
            try:
                out = json.loads(match.group(0))
                return out if isinstance(out, dict) else None
            except json.JSONDecodeError:
                return None
    return None


def _call_tool(db: Session, user_id: int, name: str, **kwargs) -> dict[str, Any]:
    """Run a tool; a failing tool becomes data, it never kills the request."""
    try:
        out = T.run_tool(name, db, user_id, **kwargs)
        return out if isinstance(out, dict) else {"result": out}
    except Exception as exc:
        _log(f"tool {name} failed: {type(exc).__name__}: {exc}")
        return {"error": str(exc)}


def _search_query(route: RouterResult, question: str) -> str:
    """Build a short search query instead of sending the whole sentence."""
    ticker = route.entities.get("ticker")
    subject = ticker or question
    if route.intent == "ipo_alert":
        return f"{subject} IPO subscription status GMP"
    return f"{subject} share price today"


def _entity_amount(route: RouterResult) -> float:
    try:
        return float(route.entities.get("amount") or 0)
    except (TypeError, ValueError):
        return 0.0


def _is_live(search: dict[str, Any]) -> bool:
    return bool(search.get("live")) and bool(search.get("results"))


# ─── Market quote (Twelve Data, via the get_market_quote tool) ────────────────

_SYMBOLS = {
    "reliance": "RELIANCE", "tcs": "TCS", "infosys": "INFY", "infy": "INFY",
    "wipro": "WIPRO", "hdfc": "HDFCBANK", "icici": "ICICIBANK", "sbi": "SBIN",
    "itc": "ITC", "apple": "AAPL", "google": "GOOGL", "microsoft": "MSFT",
    "amazon": "AMZN", "tesla": "TSLA", "nvidia": "NVDA", "meta": "META",
    "netflix": "NFLX",
}


def _symbol_for(route: RouterResult) -> str | None:
    ticker = str(route.entities.get("ticker") or "").strip()
    if not ticker or route.intent == "ipo_alert":
        return None  # IPOs have no quote yet; web_search covers them
    return _SYMBOLS.get(ticker.lower(), ticker.upper())


def _quote_info(raw: Any) -> dict[str, Any]:
    """Normalise the get_market_quote result (Twelve Data field names)."""
    def num(v: Any) -> float | None:
        try:
            return float(v)
        except (TypeError, ValueError):
            return None

    if isinstance(raw, dict) and isinstance(raw.get("quote"), dict):
        raw = raw["quote"]
    if (not isinstance(raw, dict) or raw.get("error")
            or raw.get("status") == "error" or raw.get("code")):
        return {"ok": False}
    price = num(raw.get("price") or raw.get("close") or raw.get("current_price"))
    if price is None:
        return {"ok": False}
    return {
        "ok": True,
        "symbol": raw.get("symbol"),
        "name": raw.get("name"),
        "price": price,
        "currency": raw.get("currency") or "",
        "change_pct": num(raw.get("percent_change") or raw.get("change_pct")),
        "market_open": raw.get("is_market_open"),
        "source": raw.get("source") or "Twelve Data",
    }


def _fetch_quote(db: Session, user_id: int, route: RouterResult) -> dict[str, Any]:
    sym = _symbol_for(route)
    if not sym:
        return {"ok": False, "called": False}
    raw = _call_tool(db, user_id, "get_market_quote", symbol=sym)
    qi = _quote_info(raw)
    if not qi["ok"]:
        _log(f"get_market_quote({sym}) unusable: {str(raw)[:200]}")
    qi["called"] = True
    return qi


def _quote_line(qi: dict[str, Any]) -> str:
    chg = f" ({qi['change_pct']:+.2f}% today)" if qi.get("change_pct") is not None else ""
    return (f"{qi.get('name') or qi.get('symbol')} is trading at "
            f"{qi['currency']} {qi['price']:,.2f}{chg} ({qi['source']}).").replace("  ", " ")


# ─── Summarisers (defensive: a shape mismatch must not break the LLM path) ────


def _safe(fn, data: dict, empty: str) -> str:
    if not data:
        return empty
    try:
        return fn(data)
    except Exception:
        return json.dumps(data, default=str)[:600]


def _summarise_profile(p: dict) -> str:
    return _safe(
        lambda p: (
            f"Balance: {_rs(p.get('balance', 0))}. "
            f"Monthly savings: {_rs(p.get('monthly_savings', 0))}. "
            f"Risk tolerance: {p.get('risk_tolerance', 'moderate')}. "
            f"Budget headroom: {_rs(p.get('total_budget_headroom', 0))}. "
            f"Upcoming expenses: {_rs(p.get('upcoming_expenses', 0))}."
        ),
        p,
        "No profile data available.",
    )


def _summarise_search(s: dict) -> str:
    def build(s: dict) -> str:
        prefix = "" if s.get("live") else "[MOCK - no live search API] "
        lines = [
            r if isinstance(r, str) else json.dumps(r, default=str)
            for r in (s.get("results") or [])[:3]
        ]
        if not lines and s.get("error"):
            lines = [f"search error: {s['error']}"]
        return prefix + " | ".join(line[:300] for line in lines)

    return _safe(build, s, "No market data available.")


def _summarise_history(h: dict) -> str:
    def build(h: dict) -> str:
        by_cat = h.get("spending_by_category", {}) or {}
        cat_str = ", ".join(f"{k}: {_rs(v)}" for k, v in list(by_cat.items())[:4])
        month_str = ", ".join(
            f"{m.get('month')}: {_rs(m.get('total', 0))}"
            for m in (h.get("monthly_totals") or [])
            if isinstance(m, dict)
        )
        return (
            f"Period spend: {_rs(h.get('total_period_spend', 0))}. "
            f"By category: {cat_str}. Monthly breakdown: {month_str}."
        )

    return _safe(build, h, "No spending history available.")


def _pack(route: RouterResult, answer: str, metrics: list, reasoning: list,
          caveats: list, verdict: str, confidence: int, sources: list,
          tools_used: list, alert_fired: bool = False) -> dict[str, Any]:
    """The ChatOut-compatible Recommendation object."""
    return {
        "answer": answer,
        "metrics": metrics,
        "insights": reasoning[:2],
        "sources": sources,
        "tools_used": tools_used,
        "verdict": verdict,
        "confidence": confidence,
        "reasoning": reasoning,
        "caveats": caveats,
        "intent": route.intent,
        "alert_fired": alert_fired,
    }


# ─── Deterministic fallback ───────────────────────────────────────────────────


def _fallback_answer(db: Session, user_id: int,
                     route: RouterResult, question: str) -> dict[str, Any]:
    """Rule-based path (no LLM). Still uses web_search."""

    profile = T.get_user_profile(db, user_id)
    history = T.get_spending_history(db, user_id)  # noqa: F841 (kept for parity)

    amount = _entity_amount(route)
    ticker = route.entities.get("ticker") or "the asset"

    balance = profile["balance"]
    headroom = profile["total_budget_headroom"]
    savings = profile["monthly_savings"]
    risk = profile.get("risk_tolerance", "moderate")

    # GOAL PLANNING / AFFORDABILITY
    if route.intent == "goal_planning":
        tools_used = ["get_user_profile", "get_spending_history"]

        if amount <= 0:
            verdict, confidence = "hold", 50
            reasoning = [
                "I could not identify a specific purchase amount.",
                f"Your current balance is {_rs(balance)}.",
                f"Your monthly savings are {_rs(savings)}.",
            ]
            caveats = ["Provide the purchase amount for a more precise affordability check."]
            answer = ("I need the purchase amount to determine whether you can "
                      "comfortably afford it.")

        elif amount > balance:
            verdict, confidence = "insufficient_funds", 95
            reasoning = [
                f"The purchase amount of {_rs(amount)} exceeds your balance of {_rs(balance)}.",
                "You currently do not have enough available balance for this purchase.",
                f"Your monthly savings are {_rs(savings)}.",
            ]
            caveats = ["Consider waiting until you have sufficient funds."]
            answer = f"No — {_rs(amount)} is greater than your current balance of {_rs(balance)}."

        else:
            remaining = balance - amount
            if amount > savings * 3:
                verdict, confidence = "hold", 80
                reasoning = [
                    f"The purchase would leave you with {_rs(remaining)}.",
                    f"The purchase is more than 3x your monthly savings of {_rs(savings)}.",
                    f"Your current balance is {_rs(balance)}.",
                ]
                caveats = [
                    "This is a relatively large purchase compared with your monthly savings.",
                    "Consider upcoming expenses and emergency savings before purchasing.",
                ]
                answer = (f"You can technically afford {_rs(amount)}, but it is a large "
                          f"purchase relative to your monthly savings. "
                          f"You would have {_rs(remaining)} left.")
            else:
                verdict, confidence = "buy", 85
                reasoning = [
                    f"The purchase would leave you with {_rs(remaining)}.",
                    f"Your current balance is {_rs(balance)}.",
                    f"Your monthly savings are {_rs(savings)}.",
                ]
                caveats = ["Also consider upcoming expenses and your emergency fund."]
                answer = (f"Yes — based on your current balance of {_rs(balance)}, you can "
                          f"afford {_rs(amount)}. You would have {_rs(remaining)} remaining.")

        return _pack(
            route, answer,
            [{"label": "Balance", "value": _rs(balance)},
             {"label": "Monthly Savings", "value": _rs(savings)},
             {"label": "Purchase Amount", "value": _rs(amount)},
             {"label": "Confidence", "value": f"{confidence}%"}],
            reasoning, caveats, verdict, confidence,
            ["User Profile", "Transactions"], tools_used)

    # INVESTMENT / IPO FALLBACK  (now with web_search)
    search = _call_tool(db, user_id, "web_search", query=_search_query(route, question))
    qi = _fetch_quote(db, user_id, route)
    live = qi["ok"] or _is_live(search)
    market_line = (_quote_line(qi) if qi["ok"]
                   else f"Market data: {_summarise_search(search)}"[:320])
    tools_fb = ["get_user_profile", "get_spending_history", "web_search"]
    if qi.get("called"):
        tools_fb.append("get_market_quote")
    live_bonus = 10 if live else 0
    data_caveat = [] if live else [
        "Live market data unavailable — verify the current price independently."]

    if amount > balance:
        verdict, confidence = "insufficient_funds", 90
        reasoning = [
            f"The purchase amount of {_rs(amount)} exceeds your balance of {_rs(balance)}.",
            "You do not have sufficient funds for this transaction.",
            f"Your monthly savings of {_rs(savings)} would not cover this in one go.",
            market_line,
        ]
        caveats = ["Consider saving up before making this investment."]
        answer = (f"Your balance of {_rs(balance)} is insufficient for a "
                  f"{_rs(amount)} investment in {ticker}.")

    elif amount > savings * 3:
        verdict, confidence = "hold", 60 + live_bonus
        reasoning = [
            f"The amount {_rs(amount)} is more than 3x your monthly savings of {_rs(savings)}.",
            f"Your {risk} risk tolerance suggests caution with large single investments.",
            f"Budget headroom across categories is {_rs(headroom)}.",
            market_line,
        ]
        caveats = ["Consider splitting into smaller SIP instalments."] + data_caveat
        answer = (f"A {_rs(amount)} investment in {ticker} is significant relative to your "
                  f"monthly savings of {_rs(savings)}. Proceed with caution.")

    elif amount > 0 and (amount <= headroom or amount <= savings):
        verdict, confidence = "buy", 55 + live_bonus
        reasoning = [
            f"The amount {_rs(amount)} is within your monthly savings of {_rs(savings)}.",
            f"Your balance of {_rs(balance)} can absorb this outflow.",
            f"Your risk tolerance is '{risk}'.",
            market_line,
        ]
        caveats = data_caveat + ["Past performance is not a guarantee of future returns."]
        answer = (f"Based on your finances, a {_rs(amount)} investment in {ticker} appears "
                  f"manageable" + ("." if live else ", but verify the live price before acting."))

    elif amount > 0:
        verdict, confidence = "hold", 50 + live_bonus
        reasoning = [
            f"The amount {_rs(amount)} is above one month of savings ({_rs(savings)}).",
            f"Your balance is {_rs(balance)}; budget headroom is {_rs(headroom)}.",
            market_line,
        ]
        caveats = data_caveat + ["Consider investing in smaller instalments."]
        answer = (f"{_rs(amount)} in {ticker} is more than a month of your savings; "
                  f"consider staggering it.")

    else:
        verdict, confidence = "hold", 45
        reasoning = [
            f"No investment amount was specified for {ticker}.",
            f"Your balance is {_rs(balance)}, monthly savings {_rs(savings)}.",
            market_line,
        ]
        caveats = ["Tell me how much you want to invest for a sharper answer."] + data_caveat
        answer = f"I need an amount to judge whether investing in {ticker} fits your finances."

    return _pack(
        route, answer,
        [{"label": "Balance", "value": _rs(balance)},
         {"label": "Monthly Savings", "value": _rs(savings)},
         {"label": "Budget Headroom", "value": _rs(headroom)},
         {"label": "Confidence", "value": f"{confidence}%"}],
        reasoning, caveats, verdict, confidence,
        ["User Profile",
         f"Market Quote ({qi['source']})" if qi["ok"]
         else ("Market Data" if live else "Market Data (mock/offline)"),
         "Transactions"],
        tools_fb)


# ─── Gemini confidence scorer ─────────────────────────────────────────────────


def _run_confidence_scorer(client: Any, types: Any, context_str: str) -> dict[str, Any]:
    """Gemini call: returns the parsed scorer JSON, or {} if unusable."""
    resp = client.models.generate_content(
        model=GEMINI_MODEL,
        contents=context_str,
        config=types.GenerateContentConfig(
            system_instruction=CONFIDENCE_SCORER_PROMPT,
            temperature=0.1,
            # Newer Gemini models spend output tokens on "thinking"; a small
            # limit can leave the JSON truncated or empty.
            max_output_tokens=2048,
            response_mime_type="application/json",
        ),
    )
    text = resp.text or ""
    parsed = _extract_json(text)
    if not parsed:
        _log(f"scorer output was not valid JSON: {text[:300]!r}")
        return {}
    return parsed


def _write_alert(db: Session, user_id: int, obj: Any) -> bool:
    if not isinstance(obj, dict) or not obj.get("title"):
        return False
    severity = obj.get("severity") if obj.get("severity") in ("low", "med", "high") else "med"
    try:
        db.add(Alert(
            user_id=user_id,
            type="investment",
            title=str(obj["title"])[:120],
            message=str(obj.get("message", ""))[:380],
            severity=severity,
            category="Investment",
        ))
        db.commit()
        return True
    except Exception as exc:
        db.rollback()
        _log(f"alert write failed: {type(exc).__name__}: {exc}")
        return False


# ─── Public entry point ───────────────────────────────────────────────────────


def handle(db: Session, user_id: int, question: str,
           route: RouterResult) -> dict[str, Any]:
    """Run the agentic path: gather evidence -> Gemini scorer -> guardrails."""

    if not GEMINI_API_KEY:
        _log("GEMINI_API_KEY is empty (restart the server after editing .env) -> fallback")
        return _fallback_answer(db, user_id, route, question)

    try:
        from google import genai
        from google.genai import types
    except ImportError as exc:
        _log(f"google-genai not installed (pip install google-genai) -> fallback: {exc}")
        return _fallback_answer(db, user_id, route, question)

    try:
        client = genai.Client(api_key=GEMINI_API_KEY)

        # 1. Evidence — always fetched, so web_search is guaranteed to run.
        profile = _call_tool(db, user_id, "get_user_profile")
        search = _call_tool(db, user_id, "web_search",
                            query=_search_query(route, question))
        history = _call_tool(db, user_id, "get_spending_history")
        qi = _fetch_quote(db, user_id, route)
        tools_used = ["get_user_profile", "web_search", "get_spending_history"]
        if qi.get("called"):
            tools_used.append("get_market_quote")

        amount = _entity_amount(route)
        context_str = json.dumps({
            "user_question": question,
            "amount_in_question": amount or None,
            "profile_summary": _summarise_profile(profile),
            "market_data": _summarise_search(search),
            "market_quote": qi if qi["ok"] else "unavailable",
            "spending_context": _summarise_history(history),
            "raw": {"get_user_profile": profile, "web_search": search,
                    "get_spending_history": history},
        }, default=str)

        # 2. Scorer
        scorer = _run_confidence_scorer(client, types, context_str)
        if not scorer:
            _log("scorer returned nothing usable -> fallback")
            return _fallback_answer(db, user_id, route, question)

        verdict = scorer.get("verdict")
        verdict = verdict if verdict in VERDICTS else "hold"
        confidence = _to_int(scorer.get("confidence"), 50)
        reasoning = _as_list(scorer.get("reasoning"))[:5]
        caveats = _as_list(scorer.get("caveats"))[:4]
        answer = str(scorer.get("answer") or "Analysis complete.")
        alert_obj = scorer.get("alert")

        # 3. Guardrails — deterministic, the LLM cannot override these.
        balance = float(profile.get("balance") or 0) if "error" not in profile else 0.0
        if amount and balance and amount > balance:
            if verdict != "insufficient_funds":
                verdict = "insufficient_funds"
                confidence = max(confidence, 90)
                reasoning.insert(
                    0, f"{_rs(amount)} exceeds your balance of {_rs(balance)}.")
                answer = (f"Your balance of {_rs(balance)} is insufficient for "
                          f"{_rs(amount)}.")
                if not (isinstance(alert_obj, dict) and alert_obj.get("title")):
                    alert_obj = {
                        "title": "Investment blocked: insufficient funds",
                        "message": f"{_rs(amount)} exceeds your balance of {_rs(balance)}.",
                        "severity": "high",
                    }
        elif verdict == "insufficient_funds":
            verdict = "hold"  # LLM claimed a shortfall the numbers don't show

        live = qi["ok"] or _is_live(search)
        if verdict == "buy" and not live:
            confidence = min(confidence, 60)
            caveats.append("Market data was not live; confirm the current price first.")

        # 4. Alert
        alert_fired = _write_alert(db, user_id, alert_obj)

        # 5. Response
        raw_metrics = scorer.get("metrics")
        metrics = [
            {"label": str(m["label"]), "value": str(m.get("value", ""))}
            for m in (raw_metrics if isinstance(raw_metrics, list) else [])
            if isinstance(m, dict) and m.get("label")
            and str(m["label"]).lower() != "confidence"
        ]
        if not metrics:
            metrics = [
                {"label": "Balance", "value": _rs(balance)},
                {"label": "Monthly Savings", "value": _rs(profile.get("monthly_savings", 0))},
            ]
        if qi["ok"]:
            price_metric = {"label": f"{qi.get('symbol') or 'Price'} Price",
                            "value": f"{qi['currency']} {qi['price']:,.2f}".strip()}
            metrics = [price_metric] + metrics[:2]
        metrics.append({"label": "Confidence", "value": f"{confidence}%"})

        return _pack(
            route, answer, metrics, reasoning, caveats, verdict, confidence,
            ["User Profile",
             f"Market Quote ({qi['source']})" if qi["ok"]
             else ("Market Data" if live else "Market Data (mock/offline)"),
             "Spending History"],
            tools_used, alert_fired)

    except Exception as exc:
        # Never let an agent failure break the API — but say why.
        _log(f"Gemini path failed -> fallback: {type(exc).__name__}: {exc}")
        traceback.print_exc()
        return _fallback_answer(db, user_id, route, question)