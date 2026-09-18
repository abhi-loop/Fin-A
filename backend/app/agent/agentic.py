"""Agentic Path — investment/goal/IPO tool-calling loop + Confidence Scorer.

Flow:
  1. Tool-calling loop (LLM with get_user_profile, web_search, get_spending_history)
     → LLM decides which tools to call; Python executes them
  2. Confidence Scorer (LLM call #2, strict JSON) → verdict, confidence, reasoning, caveats
  3. If alert in scorer output → write to alerts table
  4. Return ChatOut-compatible dict with full Recommendation Object

Falls back to a deterministic rules-based path when no API key is set.
"""
import json
import re
from typing import Any

from sqlalchemy.orm import Session

from ..config import ANTHROPIC_API_KEY, MODEL
from ..models import Alert
from ..tools import finance_tools as T
from .prompts import AGENTIC_SYSTEM_PROMPT, CONFIDENCE_SCORER_PROMPT
from .router import RouterResult

MAX_TURNS = 6

# Agentic-path tool schemas (subset of all tools — only the 3 designated tools)
_AGENTIC_TOOLS = ["get_user_profile", "web_search", "get_spending_history"]


def _rs(n: float) -> str:
    return "Rs " + f"{round(abs(n)):,}"


def _extract_json(text: str) -> dict[str, Any] | None:
    text = re.sub(r"^```(?:json)?|```$", "", text.strip(), flags=re.M).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", text, re.S)
        if match:
            try:
                return json.loads(match.group(0))
            except json.JSONDecodeError:
                return None
    return None


# ─── Deterministic fallback for investment queries ────────────────────────────

def _fallback_answer(db: Session, user_id: int,
                     route: RouterResult, question: str) -> dict[str, Any]:
    """Rule-based fallback when no Anthropic key is available."""
    profile = T.get_user_profile(db, user_id)
    amount = route.entities.get("amount") or 0
    ticker = route.entities.get("ticker") or "the asset"
    history = T.get_spending_history(db, user_id)

    balance = profile["balance"]
    headroom = profile["total_budget_headroom"]
    savings = profile["monthly_savings"]
    risk = profile.get("risk_tolerance", "moderate")

    # Simple rule-based verdict
    if amount > balance:
        verdict = "insufficient_funds"
        confidence = 90
        reasoning = [
            f"The purchase amount of {_rs(amount)} exceeds your balance of {_rs(balance)}.",
            "You do not have sufficient funds for this transaction.",
            f"Your monthly savings of {_rs(savings)} would not cover this in one go.",
        ]
        caveats = ["Consider saving up before making this investment."]
        answer = (f"Your balance of {_rs(balance)} is insufficient for a "
                  f"{_rs(amount)} investment in {ticker}.")
    elif amount > savings * 3:
        verdict = "hold"
        confidence = 60
        reasoning = [
            f"The amount {_rs(amount)} is more than 3× your monthly savings of {_rs(savings)}.",
            f"Your {risk} risk tolerance suggests caution with large single investments.",
            f"Budget headroom across categories is {_rs(headroom)}.",
        ]
        caveats = [
            "Consider splitting into smaller SIP instalments.",
            "Live market data is not available — get current price before deciding.",
        ]
        answer = (f"A {_rs(amount)} investment in {ticker} is significant relative "
                  f"to your monthly savings of {_rs(savings)}. Proceed with caution.")
    elif amount > 0 and amount <= headroom:
        verdict = "buy"
        confidence = 55  # capped — no live market data
        reasoning = [
            f"The amount {_rs(amount)} fits within your budget headroom of {_rs(headroom)}.",
            f"Your savings this month ({_rs(savings)}) can absorb this outflow.",
            f"Your risk tolerance is '{risk}', which aligns with equity investments.",
        ]
        caveats = [
            "Live market data unavailable — verify current price independently.",
            "Past performance is not a guarantee of future returns.",
        ]
        answer = (f"Based on your finances, a {_rs(amount)} investment in {ticker} "
                  f"appears manageable, but verify the live price before acting.")
    else:
        verdict = "hold"
        confidence = 45
        reasoning = [
            f"Insufficient context to give a strong recommendation for {ticker}.",
            f"Your balance is {_rs(balance)}, monthly savings {_rs(savings)}.",
            "No live market data available to assess the current price.",
        ]
        caveats = ["Check live price and news before investing."]
        answer = (f"I can see your financial standing but lack live market data "
                  f"to give a confident verdict on {ticker}.")

    return {
        "answer": answer,
        "metrics": [
            {"label": "Balance", "value": _rs(balance)},
            {"label": "Monthly Savings", "value": _rs(savings)},
            {"label": "Budget Headroom", "value": _rs(headroom)},
            {"label": "Confidence", "value": f"{confidence}%"},
        ],
        "insights": reasoning[:2],
        "sources": ["User Profile", "Budget", "Transactions"],
        "tools_used": ["get_user_profile", "get_spending_history"],
        "verdict": verdict,
        "confidence": confidence,
        "reasoning": reasoning,
        "caveats": caveats,
        "intent": route.intent,
        "alert_fired": False,
    }


# ─── LLM tool-calling loop ────────────────────────────────────────────────────

def _run_tool_loop(client: Any, db: Session, user_id: int,
                   question: str, tool_schemas: list) -> tuple[str, list[str]]:
    """Run the tool-calling loop. Returns (context_json_str, tools_used_list)."""
    from ..tools.finance_tools import run_tool

    messages: list[dict[str, Any]] = [{"role": "user", "content": question}]
    used: list[str] = []
    gathered: dict[str, Any] = {}

    for _ in range(MAX_TURNS):
        resp = client.messages.create(
            model=MODEL,
            max_tokens=1000,
            system=AGENTIC_SYSTEM_PROMPT,
            tools=tool_schemas,
            messages=messages,
        )
        messages.append({"role": "assistant", "content": resp.content})

        calls = [b for b in resp.content if b.type == "tool_use"]
        if not calls:
            # LLM stopped calling tools — extract its context summary
            text = "".join(b.text for b in resp.content if b.type == "text")
            parsed = _extract_json(text)
            if parsed:
                gathered.update(parsed)
            break

        results = []
        for call in calls:
            used.append(call.name)
            try:
                out = run_tool(call.name, db, user_id, **(call.input or {}))
                # Cache for context
                gathered[call.name] = out
            except Exception as exc:
                out = {"error": str(exc)}
            results.append({
                "type": "tool_result",
                "tool_use_id": call.id,
                "content": json.dumps(out, default=str),
            })
        messages.append({"role": "user", "content": results})

    # Build structured context string for the confidence scorer
    context = {
        "user_question": question,
        "profile_summary": _summarise_profile(gathered.get("get_user_profile", {})),
        "market_data": _summarise_search(gathered.get("web_search", {})),
        "spending_context": _summarise_history(gathered.get("get_spending_history", {})),
        "amount_in_question": gathered.get("amount_in_question"),
        "raw": gathered,
    }
    return json.dumps(context, default=str), used


def _summarise_profile(p: dict) -> str:
    if not p:
        return "No profile data available."
    return (
        f"Balance: {_rs(p.get('balance', 0))}. "
        f"Monthly savings: {_rs(p.get('monthly_savings', 0))}. "
        f"Risk tolerance: {p.get('risk_tolerance', 'moderate')}. "
        f"Budget headroom: {_rs(p.get('total_budget_headroom', 0))}. "
        f"Upcoming expenses: {_rs(p.get('upcoming_expenses', 0))}."
    )


def _summarise_search(s: dict) -> str:
    if not s:
        return "No market data available."
    results = s.get("results", [])
    live = s.get("live", False)
    prefix = "" if live else "[MOCK — no live search API] "
    return prefix + " | ".join(results[:3])


def _summarise_history(h: dict) -> str:
    if not h:
        return "No spending history available."
    totals = h.get("monthly_totals", [])
    by_cat = h.get("spending_by_category", {})
    period = h.get("total_period_spend", 0)
    cat_str = ", ".join(f"{k}: {_rs(v)}" for k, v in list(by_cat.items())[:4])
    month_str = ", ".join(f"{m['month']}: {_rs(m['total'])}" for m in totals)
    return (f"Period spend: {_rs(period)}. By category: {cat_str}. "
            f"Monthly breakdown: {month_str}.")


# ─── Confidence Scorer (LLM call #2) ─────────────────────────────────────────

def _run_confidence_scorer(client: Any, context_str: str,
                           db: Session, user_id: int) -> dict[str, Any]:
    """LLM call #2: scores confidence and returns full Recommendation Object."""
    resp = client.messages.create(
        model=MODEL,
        max_tokens=800,
        system=CONFIDENCE_SCORER_PROMPT,
        messages=[{"role": "user", "content": context_str}],
    )
    text = "".join(b.text for b in resp.content if b.type == "text")
    parsed = _extract_json(text)
    if not parsed:
        return {}

    # If an alert was requested, write it to DB
    alert_obj = parsed.get("alert")
    alert_fired = False
    if alert_obj and isinstance(alert_obj, dict) and alert_obj.get("title"):
        a = Alert(
            user_id=user_id,
            type="investment",
            title=alert_obj.get("title", "Investment Alert"),
            message=alert_obj.get("message", ""),
            severity=alert_obj.get("severity", "med"),
            category="Investment",
        )
        db.add(a)
        db.commit()
        alert_fired = True

    return {**parsed, "alert_fired": alert_fired}


# ─── Public entry point ───────────────────────────────────────────────────────

def handle(db: Session, user_id: int,
           question: str, route: RouterResult) -> dict[str, Any]:
    """Run the full agentic path: tool loop → confidence scorer → Recommendation Object."""
    if not ANTHROPIC_API_KEY:
        return _fallback_answer(db, user_id, route, question)

    try:
        from anthropic import Anthropic
    except ImportError:
        return _fallback_answer(db, user_id, route, question)

    # Build tool schemas for just the 3 agentic-path tools
    from ..tools.finance_tools import TOOL_SCHEMAS
    agentic_schemas = [s for s in TOOL_SCHEMAS if s["name"] in _AGENTIC_TOOLS]

    client = Anthropic(api_key=ANTHROPIC_API_KEY)

    try:
        context_str, tools_used = _run_tool_loop(
            client, db, user_id, question, agentic_schemas)

        scorer_result = _run_confidence_scorer(client, context_str, db, user_id)

        if not scorer_result:
            return _fallback_answer(db, user_id, route, question)

        # Build the final Recommendation Object / ChatOut dict
        verdict = scorer_result.get("verdict", "hold")
        confidence = int(scorer_result.get("confidence", 50))
        reasoning = scorer_result.get("reasoning", [])
        caveats = scorer_result.get("caveats", [])
        answer = scorer_result.get("answer", "Analysis complete.")
        raw_metrics = scorer_result.get("metrics", [])
        alert_fired = scorer_result.get("alert_fired", False)

        # Ensure confidence is in metrics
        has_conf = any(m.get("label", "").lower() == "confidence"
                       for m in raw_metrics)
        if not has_conf:
            raw_metrics.append({"label": "Confidence", "value": f"{confidence}%"})

        return {
            "answer": answer,
            "metrics": raw_metrics,
            "insights": reasoning[:2] if reasoning else [],
            "sources": ["User Profile", "Market Data", "Spending History"],
            "tools_used": tools_used,
            "verdict": verdict,
            "confidence": confidence,
            "reasoning": reasoning,
            "caveats": caveats,
            "intent": route.intent,
            "alert_fired": alert_fired,
        }

    except Exception:
        return _fallback_answer(db, user_id, route, question)
