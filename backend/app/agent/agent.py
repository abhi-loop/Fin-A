"""Agent loop & Intent Router: Structured Path for expense logging, fallback for agentic paths."""
import json
import re
from typing import Any

from sqlalchemy.orm import Session

from ..config import LLM_API_KEY, LLM_BASE_URL, MODEL
from ..tools import TOOL_SCHEMAS, finance_tools as T, run_tool
from . import fallback
from .prompts import EXPENSE_EXTRACTOR_PROMPT, INTENT_ROUTER_PROMPT, SYSTEM_PROMPT

MAX_TURNS = 6


def _extract_json(text: str) -> dict[str, Any] | None:
    if not text:
        return None
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


def answer(db: Session, user_id: int, question: str) -> dict[str, Any]:
    """Route intent and execute Structured Path or Agentic tool loop."""
    if not LLM_API_KEY:
        return fallback.answer(db, user_id, question)

    try:
        from openai import OpenAI
    except ImportError:
        return fallback.answer(db, user_id, question)

    client = OpenAI(api_key=LLM_API_KEY, base_url=LLM_BASE_URL)

    # Step 1: Intent Routing (LLM Call #1)
    intent = "unknown"
    try:
        router_resp = client.chat.completions.create(
            model=MODEL,
            max_tokens=200,
            messages=[
                {"role": "system", "content": INTENT_ROUTER_PROMPT},
                {"role": "user", "content": question}
            ]
        )
        r_text = router_resp.choices[0].message.content or ""
        parsed_r = _extract_json(r_text)
        if parsed_r and "intent" in parsed_r:
            intent = parsed_r["intent"]
    except Exception as e:
        print(f"Router error: {e}")
        intent = "unknown"

    # Step 2: Handle Intent
    # Out of Scope Intent
    if intent == "out_of_scope_domain":
        return {
            "answer": "Loans, insurance, travel booking, and career advice are currently out of scope and coming soon! Right now, I can help you log expenses, track budgets, and manage savings goals.",
            "metrics": [],
            "insights": ["Domain is out of current scope (roadmap feature)."],
            "sources": ["Scope Policy"],
            "tools_used": []
        }

    # Structured Path: Expense Logging
    if intent == "expense_log":
        try:
            ext_resp = client.chat.completions.create(
                model=MODEL,
                max_tokens=300,
                messages=[
                    {"role": "system", "content": EXPENSE_EXTRACTOR_PROMPT},
                    {"role": "user", "content": question}
                ]
            )
            ext_text = ext_resp.choices[0].message.content or ""
            ext_json = _extract_json(ext_text)
            if ext_json and "amount" in ext_json:
                amt = float(ext_json["amount"])
                cat = ext_json.get("category", "Other")
                desc = ext_json.get("description") or question
                res = T.add_expense_transaction(db, user_id, amt, cat, desc)
                alert = res.get("alert")

                answer_str = f"Logged expense of Rs {round(amt):,} for {cat}."
                if res["category_limit"]:
                    answer_str += f" You have spent Rs {round(res['category_spent']):,} of Rs {round(res['category_limit']):,} budget in {cat} ({res['used_pct']}% used)."

                insights = [f"Recorded transaction under category '{cat}'."]
                if alert and alert.get("message"):
                    insights.append(alert["message"])

                metrics = [
                    {"label": "Logged Expense", "value": f"Rs {round(amt):,}"},
                    {"label": f"{cat} Spend", "value": f"Rs {round(res['category_spent']):,}"},
                    {"label": "Remaining Balance", "value": f"Rs {round(res['new_balance']):,}"}
                ]
                if res["category_limit"]:
                    metrics.insert(2, {"label": "Budget Limit", "value": f"Rs {round(res['category_limit']):,}"})

                return {
                    "answer": answer_str,
                    "metrics": metrics,
                    "insights": insights,
                    "sources": ["Transactions", "Budget"],
                    "tools_used": ["add_expense_transaction", "check_and_trigger_budget_alert"]
                }
        except Exception as e:
            print(f"Expense extraction error: {e}")
            pass
        return fallback.answer(db, user_id, question)

    # Step 3: Agentic Path / General Tool Loop
    messages: list[dict[str, Any]] = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": question}
    ]
    used: list[str] = []

    try:
        for _ in range(MAX_TURNS):
            resp = client.chat.completions.create(
                model=MODEL,
                max_tokens=1500,
                tools=TOOL_SCHEMAS,
                messages=messages,
            )
            
            message = resp.choices[0].message
            messages.append(message.model_dump(exclude_unset=True))

            calls = message.tool_calls
            if not calls:
                text = message.content or ""
                parsed = _extract_json(text)
                if parsed:
                    parsed.setdefault("metrics", [])
                    parsed.setdefault("insights", [])
                    parsed.setdefault("sources", [])
                    parsed["tools_used"] = used
                    return parsed
                return {"answer": text or "I could not analyse that.",
                        "metrics": [], "insights": [], "sources": [],
                        "tools_used": used}

            for call in calls:
                used.append(call.function.name)
                try:
                    args = json.loads(call.function.arguments)
                    out = run_tool(call.function.name, db, user_id, **args)
                except Exception as exc:
                    out = {"error": str(exc)}
                messages.append({
                    "role": "tool",
                    "tool_call_id": call.id,
                    "content": json.dumps(out, default=str)
                })
    except Exception as e:
        print(f"Agentic loop error: {e}")
        pass

    return fallback.answer(db, user_id, question)
