"""Deterministic router over the same tool layer.

Used when no ANTHROPIC_API_KEY is configured or the LLM call fails, so the
demo always produces a correct, grounded answer.
"""
import re
from typing import Any

from sqlalchemy.orm import Session

from ..tools import finance_tools as T


def rs(n: float) -> str:
    return "Rs " + f"{round(abs(n)):,}".replace(",", "_").replace("_", ",")


def answer(db: Session, user_id: int, q: str) -> dict[str, Any]:
    ql = q.lower()

    # 1. Check Out-of-Scope Intent (Loans, Insurance, Travel Booking, Career)
    if re.search(r"loan|mortgage|insurance|policy|flight|hotel|book a trip|career|job search", ql):
        return {
            "answer": "Loans, insurance, travel booking, and career advice are currently out of scope and coming soon! Right now, I can help you log expenses, track budgets, and manage savings goals.",
            "metrics": [],
            "insights": ["Domain is out of current scope (roadmap feature)."],
            "sources": ["Scope Policy"],
            "tools_used": []
        }

    # 2. Extract Amount if present
    amount = None
    m = re.search(r"(\d[\d,]{0,})", q.replace("Rs", " ").replace("\u20b9", " "))
    if m:
        try:
            amount = float(m.group(1).replace(",", ""))
        except ValueError:
            amount = None

    # 3. Check Structured Path: Expense Logging Intent
    is_expense_log = bool(amount and amount > 0 and re.search(r"spent|spend|paid|bought|cost|expense|log|purchased", ql))
    if is_expense_log and not re.search(r"afford|buy|should i", ql):
        # Determine Category
        category = "Other"
        if re.search(r"food|fuel|petrol|diesel|dinner|lunch|coffee|grocery|groceries|restaurant|eating out", ql):
            category = "Food" if not re.search(r"fuel|petrol|diesel", ql) else "Travel"
        elif re.search(r"shoes|clothes|shopping|amazon|flipkart|phone|laptop|gear", ql):
            category = "Shopping"
        elif re.search(r"travel|flight|uber|ola|cab|taxi|train|bus", ql):
            category = "Travel"
        elif re.search(r"bill|rent|electricity|wifi|water|recharge", ql):
            category = "Bills"
        elif re.search(r"movie|cinema|netflix|game|party", ql):
            category = "Entertainment"
        elif re.search(r"doctor|hospital|medicine|pharma", ql):
            category = "Healthcare"

        # Determine description
        description = q.strip()
        if len(description) > 60:
            description = f"Expense in {category}"

        res = T.add_expense_transaction(db, user_id, amount, category, description)
        alert = res.get("alert")

        answer_str = f"Logged expense of {rs(amount)} for {category}."
        if res["category_limit"]:
            answer_str += f" You have spent {rs(res['category_spent'])} of {rs(res['category_limit'])} budget in {category} ({res['used_pct']}% used)."

        insights = [f"Recorded transaction under category '{category}'."]
        if alert and alert.get("message"):
            insights.append(alert["message"])

        metrics = [
            {"label": "Logged Expense", "value": rs(amount)},
            {"label": f"{category} Spend", "value": rs(res["category_spent"])},
            {"label": "Remaining Balance", "value": rs(res["new_balance"])}
        ]
        if res["category_limit"]:
            metrics.insert(2, {"label": "Budget Limit", "value": rs(res["category_limit"])})

        return {
            "answer": answer_str,
            "metrics": metrics,
            "insights": insights,
            "sources": ["Transactions", "Budget"],
            "tools_used": ["add_expense_transaction", "check_and_trigger_budget_alert"]
        }

    # 4. Affordability simulation (Agentic/Fallback)
    if amount and re.search(r"afford|buy|purchase|should i get", ql):
        r = T.simulate_purchase(db, user_id, amount)
        s = T.get_savings_rate(db, user_id)
        return {
            "answer": (f"With a balance of {rs(r['balance'])} and "
                       f"{rs(r['upcoming_expenses'])} of committed upcoming "
                       f"expenses, a {rs(amount)} purchase would leave about "
                       f"{rs(r['remaining_after'])} available."),
            "metrics": [
                {"label": "Current Balance", "value": rs(r["balance"])},
                {"label": "Upcoming Expenses", "value": rs(r["upcoming_expenses"])},
                {"label": "Purchase", "value": rs(amount)},
                {"label": "Remaining", "value": rs(r["remaining_after"])}],
            "insights": [
                "The purchase fits within your available balance."
                if r["affordable"] else
                "This purchase would exceed your available balance.",
                f"Your monthly savings are currently {rs(s['savings'])}."],
            "sources": ["Balance", "Upcoming Expenses", "Budget"],
            "tools_used": ["simulate_purchase", "get_savings_rate"]}

    # 5. Category spending query
    if re.search(r"most|biggest|where|category|food|spend on", ql):
        c = T.get_spending_by_category(db, user_id)
        e = T.get_monthly_expenses(db, user_id)["total_expenses"]
        for cat, val in c["spending"].items():
            if cat.lower() in ql:
                return {"answer": f"You have spent {rs(val)} on {cat} this month, "
                                  f"{round(val / e * 100) if e else 0}% of total expenses.",
                        "metrics": [{"label": f"{cat} Spending", "value": rs(val)},
                                    {"label": "Total Expenses", "value": rs(e)}],
                        "insights": [f"{cat} is one of your tracked categories."],
                        "sources": ["Transactions"],
                        "tools_used": ["get_spending_by_category"]}
        return {"answer": (f"Your largest spending category is {c['top_category']} "
                           f"at {rs(c['top_amount'])}, out of {rs(e)} total."),
                "metrics": [{"label": k, "value": rs(v)}
                            for k, v in list(c["spending"].items())[:4]],
                "insights": [f"{c['top_category']} is "
                             f"{round(c['top_amount'] / e * 100) if e else 0}% of spending."],
                "sources": ["Transactions"],
                "tools_used": ["get_spending_by_category", "get_monthly_expenses"]}

    # 6. Goals query
    if re.search(r"goal|on track|save for", ql):
        goals = T.get_goals(db, user_id)["goals"]
        if goals:
            g = goals[0]
            s = T.get_savings_rate(db, user_id)
            months = (round(g["remaining"] / s["savings"])
                      if s["savings"] > 0 else None)
            return {"answer": (f"Your {g['name']} goal is {g['progress_pct']}% funded "
                               f"- {rs(g['saved'])} of {rs(g['target'])}, with "
                               f"{rs(g['remaining'])} left by {g['deadline']}."),
                    "metrics": [{"label": "Target", "value": rs(g["target"])},
                                {"label": "Saved", "value": rs(g["saved"])},
                                {"label": "Remaining", "value": rs(g["remaining"])},
                                {"label": "Monthly Savings", "value": rs(s["savings"])}],
                    "insights": ([f"At {rs(s['savings'])}/month you would cover the "
                                  f"remainder in about {months} months."] if months
                                 else ["You are not saving anything this month."]),
                    "sources": ["Goals", "Transactions"],
                    "tools_used": ["get_goals", "get_savings_rate"]}

    # 7. Budget status query
    if re.search(r"overspend|too much|budget|limit", ql):
        b = T.get_budget(db, user_id)
        near = b["over_or_near_limit"]
        return {"answer": (f"You are at or near the limit in: {', '.join(near)}."
                           if near else
                           "You are within budget in every category this month."),
                "metrics": [{"label": x["category"], "value": f"{x['used_pct']}%"}
                            for x in b["budget"][:4]],
                "insights": [f"Total budget is {rs(b['total_budget'])}."],
                "sources": ["Budget", "Transactions"],
                "tools_used": ["get_budget"]}

    # Default fallback summary
    s = T.get_savings_rate(db, user_id)
    bal = T.get_balance(db, user_id)["balance"]
    return {"answer": (f"This month you earned {rs(s['income'])}, spent "
                       f"{rs(s['expenses'])} and saved {rs(s['savings'])}. "
                       f"Your balance is {rs(bal)}."),
            "metrics": [{"label": "Income", "value": rs(s["income"])},
                        {"label": "Expenses", "value": rs(s["expenses"])},
                        {"label": "Savings", "value": rs(s["savings"])},
                        {"label": "Balance", "value": rs(bal)}],
            "insights": [f"Your savings rate is {s['savings_rate_pct']}% of income."],
            "sources": ["Balance", "Transactions"],
            "tools_used": ["get_savings_rate", "get_balance"]}
