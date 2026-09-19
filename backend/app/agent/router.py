"""
Natural-language Intent Router.

The router's job is ONLY to understand what the user wants.
It does NOT calculate financial values.

High-level intents:
    expense_log | budget_query | investment_query | goal_planning
    ipo_alert   | out_of_scope

Classification priority: Anthropic (if key) -> Gemini (if key) -> regex.
Every path goes through _finalize(), which validates the intent, merges
deterministic entities, and applies safety rules (see below).
"""

import json
import os
import re
from dataclasses import dataclass, field
from typing import Any

from ..config import ANTHROPIC_API_KEY, MODEL, GEMINI_API_KEY
from .prompts import ROUTER_PROMPT


GEMINI_MODEL = os.getenv(
    "GEMINI_MODEL",
    "gemini-3.6-flash",
)


VALID_INTENTS = {
    "expense_log",
    "budget_query",
    "investment_query",
    "goal_planning",
    "ipo_alert",
    "out_of_scope",
}


@dataclass
class RouterResult:
    intent: str
    entities: dict[str, Any] = field(default_factory=dict)


# ─────────────────────────────────────────────────────────────────────────────
# Deterministic entity extraction
# ─────────────────────────────────────────────────────────────────────────────

_MULTIPLIERS = {
    "k": 1e3, "thousand": 1e3,
    "lakh": 1e5, "lakhs": 1e5, "lac": 1e5, "lacs": 1e5,
    "crore": 1e7, "crores": 1e7, "cr": 1e7,
}
_NUM = r"(\d[\d,]*(?:\.\d+)?)"
_MULT = r"(?:\s*(k|thousand|lakhs?|lacs?|crores?|cr)\b)?"
_NOT_MONEY_AFTER = re.compile(
    r"\s*(?:%|(?:months?|days?|weeks?|years?|yrs?|hours?|percent|shares?|"
    r"stocks?|units?|times|transactions?|expenses?|items?|categories|"
    r"st|nd|rd|th)\b)",
    re.I,
)
_NOT_MONEY_BEFORE = re.compile(
    r"\b(top|last|next|past|first|previous)\s*$", re.I)


def _to_amount(num: str, mult: str | None) -> float | None:
    try:
        value = float(num.replace(",", "").rstrip("."))
    except ValueError:
        return None
    value *= _MULTIPLIERS.get((mult or "").lower(), 1)
    return value if value > 0 else None


def _extract_amount(message: str) -> float | None:
    """Handles Rs 20,000 / ₹5k / 1.5 lakh / 500 rupees / bare numbers.

    Bare numbers are ignored when they are clearly not money
    ("last 30 days", "top 5 stocks", "in 2026", "3 months").
    """
    # 1) currency marker before the number
    m = re.search(rf"(?:₹|\brs\.?|\binr\b)\s*{_NUM}{_MULT}", message, re.I)
    if m:
        return _to_amount(m.group(1), m.group(2))

    # 2) currency word after the number
    m = re.search(rf"\b{_NUM}{_MULT}\s*(?:rupees|rs\b|inr\b)", message, re.I)
    if m:
        return _to_amount(m.group(1), m.group(2))

    # 3) number with a multiplier: 20k, 1 lakh, 2 crore
    m = re.search(
        rf"\b{_NUM}\s*(k|thousand|lakhs?|lacs?|crores?|cr)\b", message, re.I)
    if m:
        return _to_amount(m.group(1), m.group(2))

    # 4) bare number, unless it is obviously not an amount
    for m in re.finditer(r"\b(\d[\d,]*(?:\.\d+)?)\b", message):
        head, tail = message[:m.start()], message[m.end():]
        if _NOT_MONEY_AFTER.match(tail) or _NOT_MONEY_BEFORE.search(head):
            continue
        raw = m.group(1)
        if "," not in raw and re.fullmatch(r"(19|20)\d\d", raw):
            continue  # looks like a year
        amount = _to_amount(raw, None)
        if amount:
            return amount

    return None


def _extract_ticker(message: str) -> str | None:
    match = re.search(
        r"\b("
        r"reliance|tcs|infosys|infy|wipro|hdfc|icici|sbi|axis|itc|"
        r"adani|tata|bajaj|maruti|zomato|paytm|"
        r"apple|google|microsoft|amazon|tesla|nvidia|meta|netflix|"
        r"nifty|sensex|bitcoin|ethereum"
        r")\b",
        message.lower(),
    )

    return (
        match.group(1).title()
        if match
        else None
    )


def _extract_category(message: str) -> str | None:
    q = message.lower()

    categories = [
        (
            r"\b(food|grocery|groceries|restaurant|swiggy|zomato|"
            r"lunch|dinner|breakfast|snacks|meal|pizza|burger)\b",
            "Food",
        ),
        (
            r"\b(fuel|petrol|diesel|uber|ola|cab|auto|metro|"
            r"bus|train|flight|travel)\b",
            "Travel",
        ),
        (
            r"\b(rent|electricity|water\s*bill|internet|wifi|"
            r"recharge|phone\s*bill|bill)\b",
            "Bills",
        ),
        (
            r"\b(movie|netflix|amazon\s*prime|spotify|concert|"
            r"game|gaming|entertainment)\b",
            "Entertainment",
        ),
        (
            r"\b(medical|medicine|pharmacy|hospital|doctor|"
            r"healthcare|health)\b",
            "Healthcare",
        ),
        (
            r"\b(book|books|course|school|college|tuition|education)\b",
            "Education",
        ),
        (
            r"\b(shopping|amazon|flipkart|myntra|clothes|shirt|"
            r"pants|shoes|electronics|phone)\b",
            "Shopping",
        ),
    ]

    for pattern, category in categories:
        if re.search(pattern, q):
            return category

    return None


def _extract_entities(message: str) -> dict[str, Any]:
    return {
        "amount": _extract_amount(message),
        "ticker": _extract_ticker(message),
        "category": _extract_category(message),
        "description": message[:160],
    }


def _is_question(message: str) -> bool:
    q = message.strip().lower()
    return q.endswith("?") or bool(re.match(
        r"(how|what|which|did|have|has|am|is|are|do|does|can|could|"
        r"should|show|tell|where|when|why|list)\b", q))


def _num(v: Any) -> float | None:
    try:
        f = float(str(v).replace(",", ""))
        return f if f > 0 else None
    except (TypeError, ValueError):
        return None


# ─────────────────────────────────────────────────────────────────────────────
# Deterministic classifier (also used to sanity-check the LLMs)
# ─────────────────────────────────────────────────────────────────────────────

_IPO = r"\b(ipo|ipos|initial public offering|listing|subscribe|subscription|allotment|gmp)\b"

_STRONG_INVEST = (
    r"\b(invest\w*|stocks?|shares?|etfs?|mutual funds?|sips?|crypto\w*|"
    r"bitcoin|nifty|sensex|equity|equities)\b"
)

_TICKER_DECISION = (
    r"\b(buy|sell|hold|should|good|worth|price|outlook|target|safe|risky)\b")

_GOAL = (
    r"\b(afford\w*|should i spend|can i spend|worth (?:spending|buying|it)|"
    r"save for|saving for|savings goal|goals?|target|on track|"
    r"how (?:long|many months)|reach|enough (?:money|to))\b"
)

# Prefix-based on purpose: "overspending", "spend", "spent", "saving" all match.
_FINANCE_VOCAB = (
    r"\b(balance|budget\w*|sav\w*|spen\w*|overspen\w*|expens\w*|income|"
    r"salary|earn\w*|transaction\w*|money|financ\w*|remaining|left|limit|"
    r"cash|bills?|categor\w*|net worth|portfolio|holdings?|upcoming|due|"
    r"alerts?|emergency|how much (?:do i|did i|have i|am i|money|is my|are my))\b"
)


def _regex_classify(message: str) -> RouterResult:
    q = message.lower()
    entities = _extract_entities(message)
    amount = entities["amount"]
    ticker = entities["ticker"]

    if re.search(_IPO, q):
        return RouterResult("ipo_alert", entities)

    if re.search(_STRONG_INVEST, q) or (
            ticker and re.search(_TICKER_DECISION, q)):
        return RouterResult("investment_query", entities)

    if re.search(_GOAL, q):
        return RouterResult("goal_planning", entities)

    # buy/sell/purchase: a ticker means investing, otherwise a purchase decision
    if re.search(r"\b(buy|sell|purchase)\b", q):
        return RouterResult(
            "investment_query" if ticker else "goal_planning", entities)

    # Completed expense (statements only: "have I spent 5000?" is a question)
    if (
        re.search(r"\b(spent|paid|bought|purchased|expense|cost me|ordered)\b", q)
        and amount is not None
        and not _is_question(message)
    ):
        entities["category"] = entities["category"] or "Other"
        return RouterResult("expense_log", entities)

    if re.search(_FINANCE_VOCAB, q):
        return RouterResult("budget_query", entities)

    return RouterResult("out_of_scope", entities)


# ─────────────────────────────────────────────────────────────────────────────
# Shared post-processing for LLM output
# ─────────────────────────────────────────────────────────────────────────────

def _parse_json(text: str) -> dict[str, Any]:
    text = re.sub(r"^```(?:json)?|```$", "", text.strip(), flags=re.M).strip()
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", text, re.S)
        if not match:
            raise
        data = json.loads(match.group(0))
    if not isinstance(data, dict):
        raise ValueError("router JSON was not an object")
    return data


def _finalize(data: dict[str, Any], message: str,
              regex_intent: str) -> RouterResult:
    """Validate the LLM's answer and apply deterministic safety rules."""
    intent = data.get("intent", "budget_query")
    if intent not in VALID_INTENTS:
        intent = "budget_query"

    # An LLM "out_of_scope" on a message the regex recognises as finance
    # is almost always a false negative.
    if intent == "out_of_scope" and regex_intent != "out_of_scope":
        intent = regex_intent

    entities = data.get("entities")
    if not isinstance(entities, dict):
        entities = {}

    detected = _extract_entities(message)
    entities["description"] = message[:160]
    for key in ("amount", "ticker", "category"):
        if detected[key] is not None:
            entities[key] = detected[key]      # deterministic value wins
        else:
            entities.setdefault(key, None)     # else keep the LLM's value
    entities["amount"] = _num(entities.get("amount"))

    # Never log an expense from a question or without an amount.
    if intent == "expense_log":
        if entities["amount"] is None or _is_question(message):
            intent = "budget_query"
        else:
            entities["category"] = entities.get("category") or "Other"

    return RouterResult(intent=intent, entities=entities)


# ─────────────────────────────────────────────────────────────────────────────
# Gemini router
# ─────────────────────────────────────────────────────────────────────────────

GEMINI_ROUTER_PROMPT = """
You are the intent router for a personal finance application.

Your ONLY job is to classify the user's request.

Return ONLY valid JSON:

{
  "intent": "...",
  "entities": {
    "amount": number or null,
    "category": string or null,
    "ticker": string or null,
    "description": string
  }
}

Allowed intents:

1. expense_log
   The user is reporting an expense that already happened.

   Examples:
   "I spent 500 on food"
   "I paid 2000 for electricity"
   "Bought shoes for 3000"

2. budget_query
   The user wants factual information from their financial data.

   This includes:
   - current balance
   - savings
   - savings rate
   - monthly income
   - expenses
   - spending
   - spending by category
   - budgets
   - remaining budget
   - transactions
   - transaction history
   - recent expenses
   - financial summaries

   Examples:
   "What's my savings rate?"
   "Show me my savings"
   "How much have I spent?"
   "Show my recent transactions"
   "What's my food spending?"
   "What's my current budget?"
   "How much money do I have?"

3. investment_query
   The user is asking whether/how to invest in a stock, fund, ETF, etc.

   Examples:
   "Should I invest 20000 in Reliance?"
   "Should I buy TCS?"
   "Is Apple a good investment?"

4. goal_planning
   The user wants a decision involving affordability, a purchase,
   or a savings goal.

   Examples:
   "Can I afford a 10000 phone?"
   "Can I afford this trip?"
   "How much should I save for a car?"
   "Can I reach my 1 lakh savings goal?"

5. ipo_alert
   The user asks about an IPO, IPO subscription, listing,
   allotment, GMP, or IPO investment.

6. out_of_scope
   The request is unrelated to personal finance.

IMPORTANT:
A factual question about savings is NOT goal_planning.

For example:
"What's my savings rate?"
must be:
budget_query

"Show me my savings"
must be:
budget_query

"How much am I saving every month?"
must be:
budget_query

Only classify as goal_planning when the user is asking
about planning, affordability, or reaching a future goal.
"""


def _gemini_classify(message: str, regex_intent: str) -> RouterResult | None:
    if not GEMINI_API_KEY:
        return None

    try:
        from google import genai
        from google.genai import types

        client = genai.Client(api_key=GEMINI_API_KEY)

        response = client.models.generate_content(
            model=GEMINI_MODEL,
            contents=message,
            config=types.GenerateContentConfig(
                system_instruction=GEMINI_ROUTER_PROMPT,
                temperature=0,
                # Newer Gemini models spend output tokens on "thinking";
                # 300 could truncate the JSON and silently drop us to regex.
                max_output_tokens=1024,
                response_mime_type="application/json",
            ),
        )

        text = response.text or ""
        return _finalize(_parse_json(text), message, regex_intent)

    except Exception as exc:
        print(f"[router] Gemini router failed: {type(exc).__name__}: {exc}",
              flush=True)
        return None


def _anthropic_classify(message: str, regex_intent: str) -> RouterResult | None:
    if not ANTHROPIC_API_KEY:
        return None

    try:
        from anthropic import Anthropic

        client = Anthropic(api_key=ANTHROPIC_API_KEY)

        response = client.messages.create(
            model=MODEL,
            max_tokens=300,
            system=ROUTER_PROMPT,
            messages=[{"role": "user", "content": message}],
        )

        text = "".join(
            block.text for block in response.content if block.type == "text")
        return _finalize(_parse_json(text), message, regex_intent)

    except Exception as exc:
        print(f"[router] Anthropic failed: {type(exc).__name__}: {exc}",
              flush=True)
        return None


# ─────────────────────────────────────────────────────────────────────────────
# Public classifier
# ─────────────────────────────────────────────────────────────────────────────

def classify(message: str) -> RouterResult:
    """
    Classification priority:

    1. Anthropic if configured.
    2. Gemini if configured.
    3. Deterministic fallback.
    """
    regex = _regex_classify(message)

    result, via = _anthropic_classify(message, regex.intent), "anthropic"
    if result is None:
        result, via = _gemini_classify(message, regex.intent), "gemini"
    if result is None:
        result, via = regex, "regex"

    e = result.entities
    print(f"[router] via={via} intent={result.intent} "
          f"amount={e.get('amount')} ticker={e.get('ticker')} "
          f"category={e.get('category')}", flush=True)
    return result