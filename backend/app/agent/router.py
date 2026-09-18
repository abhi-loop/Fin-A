"""Intent Router — LLM call #1.

Classifies the user's message into one of:
  expense_log | budget_query | investment_query | goal_planning | ipo_alert | out_of_scope

Returns a RouterResult dataclass with the intent and extracted entities.
Falls back to a fast regex heuristic when no API key is configured.
"""
import json
import re
from dataclasses import dataclass, field
from typing import Any

from ..config import ANTHROPIC_API_KEY, MODEL
from .prompts import ROUTER_PROMPT

VALID_INTENTS = {
    "expense_log", "budget_query", "investment_query",
    "goal_planning", "ipo_alert", "out_of_scope",
}


@dataclass
class RouterResult:
    intent: str
    entities: dict[str, Any] = field(default_factory=dict)


# ─── Regex fallback (no API key) ──────────────────────────────────────────────

def _regex_classify(message: str) -> RouterResult:
    q = message.lower()

    # Amount extraction
    m = re.search(r"[₹rs\s]*([\d,]+)", q.replace(",", ""))
    amount = float(m.group(1).replace(",", "")) if m else None

    # Ticker/company extraction (basic)
    ticker_match = re.search(
        r"\b(reliance|tcs|infosys|hdfc|sbi|apple|google|nifty|sensex|infy|wipro)\b", q)
    ticker = ticker_match.group(1).title() if ticker_match else None

    # Expense category
    cat = None
    for kw, cat_name in [
        ("food|grocery|restaurant|swiggy|zomato", "Food"),
        ("fuel|petrol|uber|ola|cab|auto", "Travel"),
        ("rent|electricity|bill|recharge", "Bills"),
        ("movie|netflix|amazon prime|entertainment", "Entertainment"),
        ("medical|hospital|pharmacy|doctor", "Healthcare"),
        ("book|course|school|college", "Education"),
        ("shopping|amazon|flipkart|myntra|clothes", "Shopping"),
    ]:
        if re.search(kw, q):
            cat = cat_name
            break

    if re.search(r"\b(ipo|initial public offering|listing|subscribe|allotment)\b", q):
        return RouterResult("ipo_alert", {"ticker": ticker, "amount": amount})

    if re.search(r"\b(buy|sell|invest|stock|share|fund|etf|should i get|should i purchase)\b", q):
        return RouterResult("investment_query",
                            {"amount": amount, "ticker": ticker, "category": cat})

    if re.search(r"\b(spent|spend|paid|bought|purchased|expense|cost me)\b", q) and amount:
        return RouterResult("expense_log",
                            {"amount": amount, "category": cat or "Other",
                             "description": message[:80]})

    if re.search(r"\b(budget|overspend|limit|left|remaining|how much did|where did)\b", q):
        return RouterResult("budget_query", {"category": cat})

    if re.search(r"\b(goal|save for|saving|afford|trip|vacation|target)\b", q):
        return RouterResult("goal_planning", {"amount": amount})

    return RouterResult("budget_query", {})  # safe fallback


# ─── LLM classification ────────────────────────────────────────────────────────

def classify(message: str) -> RouterResult:
    """Classify message intent. Uses LLM when API key is available, regex otherwise."""
    if not ANTHROPIC_API_KEY:
        return _regex_classify(message)

    try:
        from anthropic import Anthropic
        client = Anthropic(api_key=ANTHROPIC_API_KEY)
        resp = client.messages.create(
            model=MODEL,
            max_tokens=256,
            system=ROUTER_PROMPT,
            messages=[{"role": "user", "content": message}],
        )
        text = "".join(b.text for b in resp.content if b.type == "text")
        # Strip markdown fences if present
        text = re.sub(r"^```(?:json)?|```$", "", text.strip(), flags=re.M).strip()
        data = json.loads(text)
        intent = data.get("intent", "budget_query")
        if intent not in VALID_INTENTS:
            intent = "budget_query"
        return RouterResult(intent=intent, entities=data.get("entities", {}))
    except Exception:
        return _regex_classify(message)
