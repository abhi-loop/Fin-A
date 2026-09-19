"""Structured Path — deterministic handler for expense_log and budget_query.

No LLM reasoning calls. All logic is rule-based Python:
  - Parses entities from the router result
  - Writes expense to DB
  - Updates user's stored balance
  - Recomputes month-to-date budget spend
  - Triggers an alert if spend exceeds 85% of any category budget
  - Returns a ChatOut-compatible dict
"""

import re
from datetime import date
from typing import Any

from sqlalchemy.orm import Session

from ..models import Alert, Budget, Transaction, User
from ..tools import finance_tools as T
from .router import RouterResult


def _rs(n: float) -> str:
    return "Rs " + f"{round(abs(n)):,}"


def _out(answer: str, metrics: list | None = None, insights: list | None = None,
         sources: list | None = None, tools: list | None = None,
         intent: str = "budget_query", alert_fired: bool = False) -> dict[str, Any]:
    """Build a ChatOut-compatible dict."""
    return {
        "answer": answer,
        "metrics": metrics or [],
        "insights": insights or [],
        "sources": sources or [],
        "tools_used": tools or [],
        "intent": intent,
        "alert_fired": alert_fired,
    }


BUDGET_ALERT_THRESHOLD = 0.85


# ─── Category normalization ────────────────────────────────────────────────────

_CATEGORY_KEYWORDS = {
    "Food": ["food", "grocery", "groceries", "restaurant", "swiggy", "zomato",
             "lunch", "dinner", "breakfast", "snacks", "meal", "pizza", "burger"],
    "Travel": ["fuel", "petrol", "diesel", "uber", "ola", "cab", "auto", "metro",
               "bus", "train", "flight", "travel"],
    "Bills": ["rent", "electricity", "water bill", "internet", "wifi", "recharge",
              "phone bill", "bill"],
    "Entertainment": ["movie", "netflix", "prime", "spotify", "concert", "game",
                      "gaming", "entertainment"],
    "Healthcare": ["medical", "medicine", "pharmacy", "hospital", "doctor", "health"],
    "Education": ["book", "books", "course", "college", "school", "tuition",
                  "education"],
    "Shopping": ["shopping", "amazon", "flipkart", "myntra", "clothes", "shirt",
                 "pants", "shoes", "electronics"],
}

_VALID_CATEGORIES = {"Food", "Shopping", "Travel", "Bills", "Entertainment",
                     "Healthcare", "Education", "Other"}


def _normalize_category(category: str, description: str) -> str:
    """Router category first, keyword match on the description as a safety net."""
    text = f"{category} {description}".lower()

    category = category.strip().title()
    if category not in _VALID_CATEGORIES:
        category = "Other"

    for cat, keywords in _CATEGORY_KEYWORDS.items():
        for keyword in keywords:
            if re.search(rf"\b{re.escape(keyword)}\b", text):
                return cat

    return category


# ─── Expense Log ──────────────────────────────────────────────────────────────

def _handle_expense_log(db: Session, user_id: int,
                        route: RouterResult) -> dict[str, Any]:
    entities = route.entities or {}

    try:
        amount = float(entities["amount"]) if entities.get("amount") is not None else None
    except (TypeError, ValueError):
        amount = None

    description = (entities.get("description") or "Expense logged by assistant").strip()
    category = _normalize_category(entities.get("category") or "Other", description)

    tx_date = date.today()
    if entities.get("date"):
        try:
            tx_date = date.fromisoformat(entities["date"])
        except (ValueError, TypeError):
            pass

    if not amount or amount <= 0:
        return _out("I couldn't detect an expense amount in your message. "
                    "Try: \"I spent ₹800 on food today\".", intent="expense_log")

    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        return _out("I couldn't find your financial profile.", intent="expense_log")

    # ─── Create transaction (negative = expense) and reduce stored balance ────
    expense_amount = abs(amount)

    tx = Transaction(user_id=user_id, amount=-expense_amount, type="expense",
                     category=category, description=description, date=tx_date)
    db.add(tx)
    user.balance = float(user.balance or 0) - expense_amount
    db.commit()
    db.refresh(tx)

    # ─── Budget status / alert ────────────────────────────────────────────────
    alert_fired = False
    alert_detail = None

    budget_row = (db.query(Budget)
                  .filter(Budget.user_id == user_id, Budget.category == category)
                  .first())

    if budget_row and budget_row.limit_amount:
        spending = T.get_spending_by_category(db, user_id)["spending"]
        cat_spent = float(spending.get(category, 0.0))
        used_pct = cat_spent / float(budget_row.limit_amount)

        if used_pct >= BUDGET_ALERT_THRESHOLD:
            msg = (f"You have used {round(used_pct * 100, 1)}% of your "
                   f"{category} budget ({_rs(cat_spent)} of "
                   f"{_rs(budget_row.limit_amount)}).")
            severity = "high" if used_pct >= 1.0 else "med"

            alert = Alert(
                user_id=user_id,
                type="budget_overrun",
                title=f"{category} budget {'exceeded' if used_pct >= 1.0 else 'near limit'}",
                message=msg,
                severity=severity,
                category=category,
            )
            db.add(alert)
            db.commit()
            db.refresh(alert)

            alert_fired = True
            alert_detail = {"title": alert.title, "message": msg, "severity": severity}

    # ─── Recalculate ──────────────────────────────────────────────────────────
    savings = T.get_savings_rate(db, user_id)
    new_balance = float(user.balance or 0)
    budget_info = T.get_budget(db, user_id)
    cat_budget = next((b for b in budget_info["budget"]
                       if b["category"].lower() == category.lower()), None)

    answer = (f"Logged: {_rs(expense_amount)} on {category}. "
              f"Your balance is now {_rs(new_balance)}.")
    if cat_budget:
        answer += (f" You've used {cat_budget['used_pct']}% "
                   f"({_rs(cat_budget['spent'])} of {_rs(cat_budget['limit'])}) "
                   f"of your {category} budget this month.")
    if alert_fired and alert_detail:
        answer += f" ⚠️ {alert_detail['title']}."

    metrics = [
        {"label": "Amount Logged", "value": _rs(expense_amount)},
        {"label": "New Balance", "value": _rs(new_balance)},
        {"label": "Monthly Savings", "value": _rs(savings["savings"])},
    ]
    if cat_budget:
        metrics.append({"label": f"{category} Budget Used",
                        "value": f"{cat_budget['used_pct']}%"})

    return _out(
        answer, metrics,
        [f"Expense recorded in {category} for {tx_date.strftime('%d %b %Y')}.",
         f"Your savings rate this month is {savings['savings_rate_pct']}%."],
        ["Transactions", "Budget", "User Profile"],
        ["add_expense_transaction", "get_budget", "get_savings_rate"],
        intent="expense_log", alert_fired=alert_fired,
    )


# ─── Budget Query ─────────────────────────────────────────────────────────────

# Pattern groups for natural-language questions (matched on the user's message).
_RE_BALANCE = re.compile(
    r"\b(balance|how much (?:money|cash)(?: do i have| i have| is left| left)?|"
    r"how much do i have|money (?:do i have|i have|left)|cash (?:do i have|in hand))\b")
_RE_INCOME = re.compile(
    r"\b(monthly income|my income|how much do i (?:earn|make)|"
    r"how much (?:did i|have i) (?:earn|earned|make|made)|salary)\b")
_RE_EXPENSES = re.compile(
    r"\b(total expenses|monthly expenses|my expenses|total spending|total spent|"
    r"how much (?:did|have|do) i (?:spend|spent)|how much i(?:'ve| have)? spent|"
    r"how much am i spending|what (?:did|have) i (?:spend|spent)|"
    r"(?:spent|spending) so far)\b")
_RE_TRANSACTIONS = re.compile(
    r"\b(recent transactions|recent expenses|recent spending|transaction history|"
    r"expense history|latest transactions|show.*transactions|list.*transactions|"
    r"my transactions|(?:last|latest) (?:\d+ |few )?(?:transactions|expenses))\b")


def _handle_budget_query(db: Session, user_id: int,
                         route: RouterResult) -> dict[str, Any]:
    entities = route.entities or {}
    category_filter = (entities.get("category") or "").strip().lower()
    query_text = (entities.get("description") or "").lower().strip()

    # ─── Savings (any phrasing: save / saved / saving / savings) ──────────────
    if re.search(r"\bsav(?:e|es|ed|ing|ings)\b", query_text):
        s = T.get_savings_rate(db, user_id)
        so_far = re.search(
            r"till now|until now|so far|to date|this month|"
            r"(?:did|have|had) i (?:save|saved)|i saved", query_text)
        if so_far:
            answer = (f"So far this month you've saved {_rs(s['savings'])} "
                      f"(income {_rs(s['income'])} minus expenses "
                      f"{_rs(s['expenses'])}), a {s['savings_rate_pct']}% "
                      f"savings rate.")
        else:
            answer = (f"You're saving {_rs(s['savings'])} per month, "
                      f"which is a {s['savings_rate_pct']}% savings rate.")
        return _out(
            answer,
            [{"label": "Monthly Income", "value": _rs(s["income"])},
             {"label": "Monthly Expenses", "value": _rs(s["expenses"])},
             {"label": "Monthly Savings", "value": _rs(s["savings"])},
             {"label": "Savings Rate", "value": f"{s['savings_rate_pct']}%"}],
            [f"Your income is {_rs(s['income'])} and your recorded expenses "
             f"are {_rs(s['expenses'])}.",
             f"That leaves {_rs(s['savings'])} as savings."],
            ["Transactions", "User Profile"], ["get_savings_rate"])

    # ─── Balance / money available ────────────────────────────────────────────
    if _RE_BALANCE.search(query_text):
        bal = T.get_balance(db, user_id)["balance"]
        return _out(f"Your current balance is {_rs(bal)}.",
                    [{"label": "Current Balance", "value": _rs(bal)}],
                    sources=["User Profile"], tools=["get_balance"])

    # ─── Monthly income ───────────────────────────────────────────────────────
    if _RE_INCOME.search(query_text):
        income = T.get_monthly_income(db, user_id)["monthly_income"]
        return _out(f"Your monthly income is {_rs(income)}.",
                    [{"label": "Monthly Income", "value": _rs(income)}],
                    sources=["User Profile"], tools=["get_monthly_income"])

    # ─── Total expenses (only when no category was named) ─────────────────────
    if _RE_EXPENSES.search(query_text) and not category_filter:
        e = T.get_monthly_expenses(db, user_id)
        return _out(
            f"You've spent {_rs(e['total_expenses'])} this month across "
            f"{e['transaction_count']} transactions.",
            [{"label": "Total Expenses", "value": _rs(e["total_expenses"])},
             {"label": "Transactions", "value": str(e["transaction_count"])}],
            sources=["Transactions"], tools=["get_monthly_expenses"])

    # ─── Recent transactions ("last 5 transactions" honours the number) ───────
    if _RE_TRANSACTIONS.search(query_text):
        n = re.search(r"(?:last|latest|recent|top)\s+(\d+)", query_text)
        limit = min(max(int(n.group(1)), 1), 25) if n else 10

        transactions = T.get_transactions(db, user_id, limit=limit).get("transactions", [])

        if not transactions:
            answer = "You don't have any recorded transactions yet."
        else:
            lines = []
            for tx in transactions:
                amt = float(tx.get("amount", 0))
                sign = "-" if amt < 0 else "+"
                lines.append(f"{tx.get('date')} — {tx.get('category', 'Other')} — "
                             f"{sign}{_rs(amt)}")
            answer = "Here are your recent transactions:\n\n" + "\n".join(lines)

        return _out(answer,
                    [{"label": "Transactions Shown", "value": str(len(transactions))}],
                    ["Transactions are shown newest first."],
                    ["Transactions"], ["get_transactions"])

    # ─── Shared data for category / overview answers ──────────────────────────
    budget_info = T.get_budget(db, user_id)
    savings = T.get_savings_rate(db, user_id)
    bal = T.get_balance(db, user_id)["balance"]

    budget_lines = budget_info["budget"]
    near_limit = budget_info["over_or_near_limit"]

    # ─── Category-specific query (works even without a Budget row) ────────────
    if category_filter:
        spending = T.get_spending_by_category(db, user_id)["spending"]

        actual_category = next(
            (cat for cat in spending if cat.strip().lower() == category_filter), None)
        spent = float(spending.get(actual_category, 0.0)) if actual_category else 0.0

        b = next((x for x in budget_lines
                  if x["category"].strip().lower() == category_filter), None)

        if b:
            status = ("Over limit!" if b["used_pct"] >= 100
                      else "Near limit." if b["used_pct"] >= 85
                      else "Within budget.")
            return _out(
                f"In {b['category']} you've spent {_rs(spent)} of your "
                f"{_rs(b['limit'])} budget ({b['used_pct']}% used, "
                f"{_rs(b['remaining'])} remaining).",
                [{"label": "Spent", "value": _rs(spent)},
                 {"label": "Budget Limit", "value": _rs(b["limit"])},
                 {"label": "Remaining", "value": _rs(b["remaining"])},
                 {"label": "Used", "value": f"{b['used_pct']}%"}],
                [status], ["Budget", "Transactions"],
                ["get_budget", "get_spending_by_category"])

        if actual_category:
            return _out(
                f"You've spent {_rs(spent)} on {actual_category} this month. "
                f"No budget limit is configured for {actual_category} yet.",
                [{"label": f"{actual_category} Spent", "value": _rs(spent)},
                 {"label": "Budget Limit", "value": "Not set"},
                 {"label": "Current Balance", "value": _rs(bal)}],
                [f"{actual_category} spending is based on your recorded transactions.",
                 f"No {actual_category} budget has been configured yet."],
                ["Transactions"], ["get_spending_by_category"])

        return _out(
            f"I don't have any recorded spending for {category_filter.title()} "
            f"yet, and no budget is configured for that category.",
            [{"label": "Spent", "value": "Rs 0"},
             {"label": "Budget Limit", "value": "Not set"}],
            sources=["Transactions", "Budget"],
            tools=["get_spending_by_category", "get_budget"])

    # ─── General budget overview ──────────────────────────────────────────────
    if near_limit:
        answer = (f"You're at or near the limit in: {', '.join(near_limit)}. "
                  f"Your balance is {_rs(bal)} and you've saved "
                  f"{_rs(savings['savings'])} this month.")
    elif budget_lines:
        answer = (f"You're within budget in all categories. Balance: {_rs(bal)}, "
                  f"monthly savings: {_rs(savings['savings'])}.")
    else:
        answer = (f"No category budgets have been configured yet. Your balance is "
                  f"{_rs(bal)} and your monthly savings are {_rs(savings['savings'])}.")

    return _out(
        answer,
        [{"label": b["category"], "value": f"{b['used_pct']}%"} for b in budget_lines[:4]],
        [f"Total budget this month: {_rs(budget_info['total_budget'])}.",
         f"Savings rate: {savings['savings_rate_pct']}% of income."],
        ["Budget", "Transactions"], ["get_budget", "get_savings_rate"])


# ─── Public dispatch ──────────────────────────────────────────────────────────

def handle(db: Session, user_id: int, route: RouterResult) -> dict[str, Any]:
    """Dispatch to the correct structured handler based on intent."""
    if route.intent == "expense_log":
        return _handle_expense_log(db, user_id, route)
    return _handle_budget_query(db, user_id, route)