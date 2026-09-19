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
    "price_compare",
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
        if re.fullmatch(r"(19|20)\d\d", raw) and re.search(
                r"\b(in|of|by|since|during|year|fy)\s*$", head, re.I):
            continue  # "in 2026" is a year; "paid 2000" is money
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
# Shopping / price comparison
# ─────────────────────────────────────────────────────────────────────────────

_PRODUCT = (
    r"\b(phones?|mobiles?|smartphones?|iphones?|samsung|pixel|oneplus|redmi|"
    r"laptops?|macbooks?|notebooks?|watch(?:es)?|smartwatch(?:es)?|"
    r"headphones?|earbuds?|earphones?|airpods|tablets?|ipads?|tvs?|television|"
    r"cameras?|consoles?|playstation|ps5|monitors?|keyboards?|shoes|sneakers)\b"
)
_PRICE_STRONG = (
    r"\b(best price|lowest price|compare prices?|price comparison|"
    r"price compare|best deals?)\b")
_PRICE_WEAK = (
    r"\b(cheapest|cheaper|cheap|deals?|discounts?|offers?|"
    r"where (?:can i |to )?buy|price of|prices? for|how much (?:is|does|for)|"
    r"cost of|under|below|within|budget)\b")


# "I need an iPhone", "looking for a smartwatch", "want to buy a laptop"
_NEED = (
    r"\b(i need|i want|i'?m looking for|im looking for|looking for|"
    r"looking to buy|want to buy|need to buy|wanna buy|planning to buy|"
    r"plan to buy|thinking of buying|thinking about buying|get me|find me)\b")

# Messages about money already spent / bills are never shopping requests.
_NOT_SHOPPING = (
    r"\b(spent|spend|paid|pay|bought|purchased|expenses?|cost me|ordered|"
    r"bills?|recharge|spending|transactions?|savings?)\b")


def _is_price_compare(q: str) -> bool:
    if re.search(r"\bafford", q):
        return False  # affordability is goal_planning
    if re.search(_PRICE_STRONG, q):
        return True
    if re.search(_NOT_SHOPPING, q):
        return False
    has_product = bool(re.search(_PRODUCT, q))
    if has_product and (re.search(_PRICE_WEAK, q) or re.search(_NEED, q)):
        return True
    # bare product mention: "apple watch", "iphone 15"
    return has_product and len(q.split()) <= 5 and not _is_question(q)


def _extract_product(message: str) -> str:
    """'best price for iPhone 15 under 60k' -> 'iPhone 15'."""
    q = re.sub(r"[?!]", " ", message)
    q = re.sub(
        r"\b(?:under|below|within|less than|upto|up to|around|budget of|"
        r"max(?:imum)?)\b\s*(?:₹|rs\.?|inr)?\s*\d[\d,]*(?:\.\d+)?"
        r"\s*(?:k|thousand|lakhs?|lacs?)?", " ", q, flags=re.I)
    q = re.sub(
        r"\b(?:what(?:'s| is)|whats|show me|find me|find|get me|"
        r"looking to buy|want to buy|need to buy|wanna buy|planning to buy|"
        r"plan to buy|thinking of buying|thinking about buying|"
        r"i want to|i want|i need to|i need|i'm looking for|im looking for|"
        r"looking for|can you|please|"
        r"tell me|best price(?: for| of| on)?|lowest price(?: for| of| on)?|"
        r"compare prices?(?: for| of| on)?|price comparison(?: for| of)?|"
        r"price compare|price of|prices? for|cost of|best deals?(?: on| for)?|"
        r"deals?(?: on| for)?|discounts?(?: on| for)?|offers?(?: on| for)?|"
        r"where (?:can i |to )?buy|how much (?:is|does|for)|cheap(?:est|er)?|"
        r"buy|purchase|online|in india|for me|the|an?|to|on|for|of)\b",
        " ", q, flags=re.I)
    q = re.sub(r"[.,]", " ", q)
    return re.sub(r"\s+", " ", q).strip()[:80]


def _add_shopping_entities(entities: dict[str, Any], message: str) -> None:
    entities["product"] = _extract_product(message)
    # The number right after "under/below/within...", so a model number
    # like "iPhone 15" is never mistaken for the budget.
    m = re.search(
        rf"\b(?:under|below|within|less than|upto|up to|max(?:imum)?|"
        rf"budget(?: of)?)\s*(?:₹|rs\.?|inr)?\s*{_NUM}{_MULT}",
        message, re.I)
    entities["max_price"] = _to_amount(m.group(1), m.group(2)) if m else None


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

    if re.search(_STRONG_INVEST, q):
        return RouterResult("investment_query", entities)

    if _is_price_compare(q):
        _add_shopping_entities(entities, message)
        return RouterResult("price_compare", entities)

    if re.search(_PRODUCT, q):   # "Apple Watch" is a product, not the AAPL stock
        ticker = None
        entities["ticker"] = None

    if ticker and re.search(_TICKER_DECISION, q):
        return RouterResult("investment_query", entities)

    if re.search(_GOAL, q):
        return RouterResult("goal_planning", entities)

    # buy/sell/purchase: a ticker means investing, otherwise a purchase decision
    if re.search(r"\b(buy|sell|purchase)\b", q):
        return RouterResult(
            "investment_query" if ticker else "goal_planning", entities)

    # Completed expense (statements only: "have I spent 5000?" is a question)
    if (
        re.search(r"\b(spent|spend|paid|pay|bought|purchased|expense|cost me|ordered)\b", q)
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

    # Explicit price-comparison wording beats the LLM's looser guesses.
    if regex_intent == "price_compare" and intent in {
            "goal_planning", "budget_query", "investment_query"}:
        intent = "price_compare"

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

    if intent == "price_compare":
        _add_shopping_entities(entities, message)

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
   "spend 500 on food"
   "pay 2000 for electricity"

   A short command with an amount ("spend 500") means the user is
   recording an expense. A QUESTION about spending ("should I spend 500?",
   "how much did I spend?") is not expense_log.

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

7. price_compare
   The user wants the best price / cheapest deal for a product
   (phone, laptop, watch, headphones...) across shops.

   Examples:
   "Best price for iPhone 15"
   "Cheapest laptop under 60k"
   "Where can I buy AirPods Pro for less?"

   "Can I afford an iPhone?" is goal_planning, NOT price_compare.

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


# ─────────────────────────────────────────────────────────────────────────────
# Money coming IN ("add 10000 to my account")  --  add-only block
# ─────────────────────────────────────────────────────────────────────────────

_INCOME_ADD_TO = (
    r"\b(?:add|put|deposit|credit|transfer|top ?up|load)\b.{0,40}?"
    r"\b(?:to|into|in)\s+(?:my\s+)?(?:acc|account|a/c|balance|wallet|bank|"
    r"savings(?!\s+goal))\b")
_INCOME_VERBS = (
    r"\b(deposit(?:ed)?|credited|received|recieved|earned|refund(?:ed)?|"
    r"got paid|salary\s+(?:credited|received|came)|got (?:my )?salary)\b")


def _income_amount(message: str):
    """Rs 10,000 / ₹5k / 1.5 lakh / 10000 -> float, or None."""
    m = re.search(
        r"(?:₹|\brs\.?|\binr\b)?\s*(\d[\d,]*(?:\.\d+)?)\s*(k|thousand|lakhs?|lacs?|crores?|cr)?\b",
        message, re.I)
    if not m:
        return None
    try:
        value = float(m.group(1).replace(",", "").rstrip("."))
    except ValueError:
        return None
    mult = {"k": 1e3, "thousand": 1e3, "lakh": 1e5, "lakhs": 1e5, "lac": 1e5,
            "lacs": 1e5, "crore": 1e7, "crores": 1e7, "cr": 1e7}
    value *= mult.get((m.group(2) or "").lower(), 1)
    return value if value > 0 else None


def _is_income(message: str) -> bool:
    q = message.lower().strip()
    if q.endswith("?") or re.match(
            r"(how|what|which|did|have|has|am|is|are|do|does|can|could|"
            r"should|show|tell|where|when|why|list)\b", q):
        return False  # a question, not a deposit
    if _income_amount(message) is None:
        return False
    return bool(re.search(_INCOME_ADD_TO, q) or re.search(_INCOME_VERBS, q))


_classify_before_income = classify   # keep your existing classify() untouched


def classify(message: str) -> "RouterResult":          # noqa: F811
    if _is_income(message):
        q = message.lower()
        category = ("Salary" if "salary" in q
                    else "Refund" if "refund" in q else "Income")
        return RouterResult("income_log", {
            "amount": _income_amount(message), "ticker": None,
            "category": category, "description": message[:160]})
    return _classify_before_income(message)