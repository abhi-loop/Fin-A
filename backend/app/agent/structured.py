"""Structured Path — deterministic handler for expense_log and budget_query.

No LLM reasoning calls. All logic is rule-based Python:
  - Parses entities from the router result
  - Writes expense to DB
  - Recomputes month-to-date budget spend
  - Triggers an alert if spend exceeds 85% of any category budget
  - Returns a ChatOut-compatible dict
"""
import re
from datetime import date
from typing import Any

from sqlalchemy.orm import Session

from ..models import Alert, Budget, Transaction
from ..tools import finance_tools as T
from .router import RouterResult


def _rs(n: float) -> str:
    return "Rs " + f"{round(abs(n)):,}"


BUDGET_ALERT_THRESHOLD = 0.85  # 85 %


# ─── Expense Log ──────────────────────────────────────────────────────────────

def _handle_expense_log(db: Session, user_id: int,
                        route: RouterResult) -> dict[str, Any]:
    entities = route.entities or {}
    amount = entities.get("amount")
    category = (entities.get("category") or "Other").strip().title()
    description = (entities.get("description") or "Expense logged by assistant").strip()
    tx_date_str = entities.get("date")
    tx_date = date.today()
    if tx_date_str:
        try:
            tx_date = date.fromisoformat(tx_date_str)
        except ValueError:
            pass

    alert_fired = False
    alert_detail = None

    if amount and amount > 0:
        # Write the transaction
        tx = Transaction(
            user_id=user_id,
            amount=-abs(amount),
            type="expense",
            category=category,
            description=description,
            date=tx_date,
        )
        db.add(tx)
        db.commit()

        # Recompute budget status for this category
        budget_row = (
            db.query(Budget)
            .filter(Budget.user_id == user_id, Budget.category == category)
            .first()
        )
        if budget_row:
            spending = T.get_spending_by_category(db, user_id)["spending"]
            cat_spent = spending.get(category, 0.0)
            used_pct = cat_spent / budget_row.limit_amount if budget_row.limit_amount else 0
            if used_pct >= BUDGET_ALERT_THRESHOLD:
                msg = (f"You have used {round(used_pct * 100, 1)}% of your "
                       f"{category} budget ({_rs(cat_spent)} of "
                       f"{_rs(budget_row.limit_amount)}).")
                severity = "high" if used_pct >= 1.0 else "med"
                a = Alert(
                    user_id=user_id, type="budget_overrun",
                    title=f"{category} budget {('exceeded' if used_pct >= 1.0 else 'near limit')}",
                    message=msg, severity=severity, category=category,
                )
                db.add(a)
                db.commit()
                alert_fired = True
                alert_detail = {"title": a.title, "message": msg, "severity": severity}

        # Build response
        savings = T.get_savings_rate(db, user_id)
        bal = T.get_balance(db, user_id)["balance"]
        budget_info = T.get_budget(db, user_id)

        cat_budget = next(
            (b for b in budget_info["budget"] if b["category"] == category), None)

        answer = (f"Logged: {_rs(amount)} on {category}. "
                  f"Your balance is now {_rs(bal)}.")
        if cat_budget:
            answer += (f" You've used {cat_budget['used_pct']}% "
                       f"({_rs(cat_budget['spent'])} of {_rs(cat_budget['limit'])}) "
                       f"of your {category} budget this month.")
        if alert_fired:
            answer += f" ⚠️ {alert_detail['title']}."

        metrics = [
            {"label": "Amount Logged", "value": _rs(amount)},
            {"label": "New Balance", "value": _rs(bal)},
            {"label": "Monthly Savings", "value": _rs(savings["savings"])},
        ]
        if cat_budget:
            metrics.append({"label": f"{category} Budget Used",
                            "value": f"{cat_budget['used_pct']}%"})

        return {
            "answer": answer,
            "metrics": metrics,
            "insights": [
                f"Expense recorded in {category} for {tx_date.strftime('%d %b %Y')}.",
                f"Your savings rate this month is {savings['savings_rate_pct']}%.",
            ],
            "sources": ["Transactions", "Budget"],
            "tools_used": ["expense_log", "get_budget"],
            "intent": "expense_log",
            "alert_fired": alert_fired,
        }

    # Couldn't parse an amount
    return {
        "answer": ("I couldn't detect an expense amount in your message. "
                   "Try: \"I spent ₹800 on food today\"."),
        "metrics": [], "insights": [], "sources": [],
        "tools_used": [], "intent": "expense_log", "alert_fired": False,
    }


# ─── Budget Query ─────────────────────────────────────────────────────────────

def _handle_budget_query(db: Session, user_id: int,
                         route: RouterResult) -> dict[str, Any]:
    entities = route.entities or {}
    category_filter = (entities.get("category") or "").strip().lower()

    budget_info = T.get_budget(db, user_id)
    savings = T.get_savings_rate(db, user_id)
    bal = T.get_balance(db, user_id)["balance"]

    budget_lines = budget_info["budget"]
    near_limit = budget_info["over_or_near_limit"]

    if category_filter:
        matching = [b for b in budget_lines
                    if b["category"].lower() == category_filter]
        if matching:
            b = matching[0]
            answer = (f"In {b['category']} you've spent {_rs(b['spent'])} "
                      f"of your {_rs(b['limit'])} budget "
                      f"({b['used_pct']}% used, {_rs(b['remaining'])} remaining).")
            return {
                "answer": answer,
                "metrics": [
                    {"label": "Spent", "value": _rs(b["spent"])},
                    {"label": "Budget Limit", "value": _rs(b["limit"])},
                    {"label": "Remaining", "value": _rs(b["remaining"])},
                    {"label": "Used", "value": f"{b['used_pct']}%"},
                ],
                "insights": [
                    f"{'Over limit!' if b['used_pct'] >= 100 else ('Near limit.' if b['used_pct'] >= 85 else 'Within budget.')}"
                ],
                "sources": ["Budget", "Transactions"],
                "tools_used": ["get_budget"],
                "intent": "budget_query",
                "alert_fired": False,
            }

    # General budget overview
    if near_limit:
        answer = (f"You're at or near the limit in: {', '.join(near_limit)}. "
                  f"Your balance is {_rs(bal)} and you've saved {_rs(savings['savings'])} this month.")
    else:
        answer = (f"You're within budget in all categories. "
                  f"Balance: {_rs(bal)}, monthly savings: {_rs(savings['savings'])}.")

    return {
        "answer": answer,
        "metrics": [{"label": b["category"], "value": f"{b['used_pct']}%"}
                    for b in budget_lines[:4]],
        "insights": [
            f"Total budget this month: {_rs(budget_info['total_budget'])}.",
            f"Savings rate: {savings['savings_rate_pct']}% of income.",
        ],
        "sources": ["Budget", "Transactions"],
        "tools_used": ["get_budget", "get_savings_rate"],
        "intent": "budget_query",
        "alert_fired": False,
    }


# ─── Public dispatch ──────────────────────────────────────────────────────────

def handle(db: Session, user_id: int, route: RouterResult) -> dict[str, Any]:
    """Dispatch to the correct structured handler based on intent."""
    if route.intent == "expense_log":
        return _handle_expense_log(db, user_id, route)
    return _handle_budget_query(db, user_id, route)
