"""The agent's tool layer.

Every number the assistant reports comes from here. The LLM decides *which*
tools to call; Python does *all* of the arithmetic, so the model can never
hallucinate a figure.
"""
import datetime
from collections import defaultdict
from datetime import date
from typing import Any, Callable

from sqlalchemy.orm import Session

from ..config import SERPER_API_KEY, TAVILY_API_KEY
from ..models import (Alert, Budget, Goal, Investment, Transaction,
                      UpcomingExpense, User)


def _user(db: Session, user_id: int) -> User:
    return db.query(User).filter(User.id == user_id).one()


def get_balance(db: Session, user_id: int) -> dict[str, Any]:
    """Current total account balance in INR."""
    return {"balance": _user(db, user_id).balance}


def get_monthly_income(db: Session, user_id: int) -> dict[str, Any]:
    """The user's recurring monthly income."""
    return {"monthly_income": _user(db, user_id).monthly_income}


def get_transactions(db: Session, user_id: int, limit: int = 50) -> dict[str, Any]:
    """Recent transactions, newest first."""
    rows = (db.query(Transaction).filter(Transaction.user_id == user_id)
            .order_by(Transaction.date.desc()).limit(limit).all())
    return {"transactions": [
        {"date": str(r.date), "description": r.description,
         "category": r.category, "amount": r.amount} for r in rows]}


def get_monthly_expenses(db: Session, user_id: int) -> dict[str, Any]:
    """Total spent this period, and the transaction count."""
    rows = db.query(Transaction).filter(
        Transaction.user_id == user_id, Transaction.amount < 0).all()
    return {"total_expenses": round(sum(-r.amount for r in rows), 2),
            "transaction_count": len(rows)}


def get_spending_by_category(db: Session, user_id: int) -> dict[str, Any]:
    """Spending broken down by category, plus the largest category."""
    rows = db.query(Transaction).filter(
        Transaction.user_id == user_id, Transaction.amount < 0).all()
    agg: dict[str, float] = defaultdict(float)
    for r in rows:
        agg[r.category] += -r.amount
    ordered = sorted(agg.items(), key=lambda kv: kv[1], reverse=True)
    return {
        "spending": {k: round(v, 2) for k, v in ordered},
        "top_category": ordered[0][0] if ordered else None,
        "top_amount": round(ordered[0][1], 2) if ordered else 0,
    }


def get_budget(db: Session, user_id: int) -> dict[str, Any]:
    """Each category budget with amount spent and percentage used."""
    spending = get_spending_by_category(db, user_id)["spending"]
    rows = db.query(Budget).filter(Budget.user_id == user_id).all()
    out = []
    for b in rows:
        spent = spending.get(b.category, 0.0)
        out.append({"category": b.category, "limit": b.limit_amount,
                    "spent": round(spent, 2),
                    "remaining": round(b.limit_amount - spent, 2),
                    "used_pct": round(spent / b.limit_amount * 100, 1)
                    if b.limit_amount else 0})
    return {"budget": out,
            "total_budget": sum(b.limit_amount for b in rows),
            "over_or_near_limit": [x["category"] for x in out
                                   if x["used_pct"] >= 85]}


def get_upcoming_expenses(db: Session, user_id: int) -> dict[str, Any]:
    """Committed expenses not yet paid (rent, bills, premiums)."""
    rows = db.query(UpcomingExpense).filter(
        UpcomingExpense.user_id == user_id).all()
    return {"upcoming": [{"name": r.name, "amount": r.amount,
                          "due_date": r.due_date} for r in rows],
            "total_upcoming": round(sum(r.amount for r in rows), 2)}


def get_goals(db: Session, user_id: int) -> dict[str, Any]:
    """Savings goals with progress and the amount still required."""
    rows = db.query(Goal).filter(Goal.user_id == user_id).all()
    return {"goals": [
        {"name": g.name, "target": g.target_amount, "saved": g.saved_amount,
         "remaining": round(g.target_amount - g.saved_amount, 2),
         "progress_pct": round(g.saved_amount / g.target_amount * 100, 1)
         if g.target_amount else 0, "deadline": g.deadline} for g in rows]}


def get_investments(db: Session, user_id: int) -> dict[str, Any]:
    """Investment holdings with invested versus current value."""
    rows = db.query(Investment).filter(Investment.user_id == user_id).all()
    invested = sum(r.invested_amount for r in rows)
    current = sum(r.current_value for r in rows)
    return {"holdings": [
        {"asset": r.asset, "type": r.asset_type,
         "invested": r.invested_amount, "current": r.current_value}
        for r in rows],
        "total_invested": round(invested, 2),
        "total_current": round(current, 2),
        "unrealised_gain": round(current - invested, 2)}


def get_savings_rate(db: Session, user_id: int) -> dict[str, Any]:
    """Monthly income minus expenses, and the savings rate."""
    income = _user(db, user_id).monthly_income
    expenses = get_monthly_expenses(db, user_id)["total_expenses"]
    saved = income - expenses
    return {"income": income, "expenses": expenses, "savings": round(saved, 2),
            "savings_rate_pct": round(saved / income * 100, 1) if income else 0}


def simulate_purchase(db: Session, user_id: int, amount: float) -> dict[str, Any]:
    """Model the effect of a one-off purchase on the user's available money."""
    balance = get_balance(db, user_id)["balance"]
    upcoming = get_upcoming_expenses(db, user_id)["total_upcoming"]
    remaining = balance - upcoming - amount
    return {"balance": balance, "upcoming_expenses": upcoming,
            "purchase_amount": amount, "remaining_after": round(remaining, 2),
            "affordable": remaining > 0}


def create_alert(db: Session, user_id: int, title: str, message: str,
                 severity: str = "med", category: str = "General",
                 alert_type: str = "agent") -> dict[str, Any]:
    """Save a new alert for the user."""
    a = Alert(user_id=user_id, type=alert_type, title=title, message=message,
              severity=severity, category=category)
    db.add(a)
    db.commit()
    return {"created": True, "id": a.id, "title": title, "message": message}


def check_and_trigger_budget_alert(db: Session, user_id: int, category: str) -> dict[str, Any] | None:
    """Check if category spend exceeds budget and trigger an Alert if over threshold."""
    spending = get_spending_by_category(db, user_id)["spending"]
    spent = spending.get(category, 0.0)
    
    b = db.query(Budget).filter(Budget.user_id == user_id, Budget.category == category).first()
    if not b or not b.limit_amount:
        return None
        
    limit = b.limit_amount
    used_pct = round(spent / limit * 100, 1)
    
    if spent >= limit:
        title = f"Budget Alert: {category}"
        msg = f"You've spent ₹{round(spent):,} of your ₹{round(limit):,} budget in {category} ({used_pct}% used)."
        existing = db.query(Alert).filter(
            Alert.user_id == user_id, Alert.category == category, Alert.read == False
        ).first()
        if not existing:
            a = Alert(user_id=user_id, type="budget_overrun", title=title, message=msg,
                      severity="high", category=category)
            db.add(a)
            db.commit()
            return {"triggered": True, "title": title, "message": msg, "severity": "high", "used_pct": used_pct}
        return {"triggered": True, "title": title, "message": msg, "severity": "high", "used_pct": used_pct}
    elif used_pct >= 90:
        title = f"Near Budget Limit: {category}"
        msg = f"Warning: You have reached {used_pct}% of your {category} budget (₹{round(spent):,}/₹{round(limit):,})."
        existing = db.query(Alert).filter(
            Alert.user_id == user_id, Alert.category == category, Alert.read == False
        ).first()
        if not existing:
            a = Alert(user_id=user_id, type="budget_warning", title=title, message=msg,
                      severity="med", category=category)
            db.add(a)
            db.commit()
            return {"triggered": True, "title": title, "message": msg, "severity": "med", "used_pct": used_pct}
        return {"triggered": True, "title": title, "message": msg, "severity": "med", "used_pct": used_pct}
    return None


def add_expense_transaction(db: Session, user_id: int, amount: float, category: str,
                             description: str, tx_date: date | None = None) -> dict[str, Any]:
    """Log an expense transaction, update user balance, and trigger budget alerts if over budget."""
    if tx_date is None:
        tx_date = date.today()
        
    abs_amt = abs(amount)
    tx = Transaction(user_id=user_id, amount=-abs_amt, type="expense",
                     category=category, description=description, date=tx_date)
    db.add(tx)
    
    user = db.query(User).filter(User.id == user_id).first()
    if user:
        user.balance -= abs_amt
        
    db.commit()
    db.refresh(tx)
    
    alert_info = check_and_trigger_budget_alert(db, user_id, category)
    
    b = db.query(Budget).filter(Budget.user_id == user_id, Budget.category == category).first()
    spending = get_spending_by_category(db, user_id)["spending"]
    spent = spending.get(category, 0.0)
    limit = b.limit_amount if b else 0.0
    
    return {
        "transaction": {"id": tx.id, "amount": abs_amt, "category": category,
                        "description": description, "date": str(tx.date)},
        "new_balance": user.balance if user else 0.0,
        "category_spent": spent,
        "category_limit": limit,
        "used_pct": round(spent / limit * 100, 1) if limit else 0,
        "alert": alert_info,
    }


# ── Agentic-path tools ────────────────────────────────────────────────────────

def get_user_profile(db: Session, user_id: int) -> dict[str, Any]:
    """Return the user's financial profile: balance, income, budget headroom per category, active goals, and risk tolerance."""
    u = _user(db, user_id)
    savings = get_savings_rate(db, user_id)
    budget_info = get_budget(db, user_id)
    goals_info = get_goals(db, user_id)
    upcoming = get_upcoming_expenses(db, user_id)

    headroom = [
        {"category": b["category"],
         "headroom": b["remaining"],
         "used_pct": b["used_pct"]}
        for b in budget_info["budget"]
    ]
    return {
        "balance": u.balance,
        "monthly_income": u.monthly_income,
        "monthly_savings": savings["savings"],
        "savings_rate_pct": savings["savings_rate_pct"],
        "risk_tolerance": getattr(u, "risk_tolerance", "moderate"),
        "budget_headroom": headroom,
        "total_budget_headroom": sum(h["headroom"] for h in headroom if h["headroom"] > 0),
        "upcoming_expenses": upcoming["total_upcoming"],
        "active_goals": goals_info["goals"],
    }


def web_search(db: Session, user_id: int, query: str) -> dict[str, Any]:
    """Search the web for live stock price, IPO news, or market data for the given query."""
    # 1) Try Tavily
    if TAVILY_API_KEY:
        try:
            import urllib.request, json as _json
            payload = _json.dumps({"api_key": TAVILY_API_KEY, "query": query,
                                   "search_depth": "basic", "max_results": 3}).encode()
            req = urllib.request.Request(
                "https://api.tavily.com/search",
                data=payload, headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=10) as r:
                data = _json.loads(r.read())
            results = data.get("results", [])
            snippets = [f"{r['title']}: {r['content'][:200]}" for r in results[:3]]
            return {"source": "tavily", "query": query,
                    "results": snippets, "live": True}
        except Exception as e:
            pass  # fall through to next provider

    # 2) Try Serper
    if SERPER_API_KEY:
        try:
            import urllib.request, json as _json
            payload = _json.dumps({"q": query}).encode()
            req = urllib.request.Request(
                "https://google.serper.dev/search",
                data=payload,
                headers={"X-API-KEY": SERPER_API_KEY,
                          "Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=10) as r:
                data = _json.loads(r.read())
            snippets = [
                f"{item.get('title', '')}: {item.get('snippet', '')[:200]}"
                for item in data.get("organic", [])[:3]
            ]
            return {"source": "serper", "query": query,
                    "results": snippets, "live": True}
        except Exception:
            pass

    # 3) Realistic mock — clearly marked so confidence scorer can cap confidence
    today = datetime.date.today().isoformat()
    mock_results = [
        f"[MOCK DATA — no search API key configured] Query: '{query}'",
        f"Market data unavailable. Date: {today}.",
        "Confidence will be reduced due to missing live market data.",
    ]
    return {"source": "mock", "query": query,
            "results": mock_results, "live": False}


def get_spending_history(db: Session, user_id: int,
                         category: str = "", months: int = 3) -> dict[str, Any]:
    """Return recent spending history by category for the last N months, useful for understanding discretionary cash-flow patterns."""
    rows = db.query(Transaction).filter(
        Transaction.user_id == user_id,
        Transaction.amount < 0
    ).order_by(Transaction.date.desc()).all()

    by_category: dict[str, float] = defaultdict(float)
    by_month: dict[str, float] = defaultdict(float)
    for r in rows:
        by_category[r.category] += -r.amount
        month_key = str(r.date)[:7]  # YYYY-MM
        by_month[month_key] += -r.amount

    # Filter to requested category if given
    cat_filter = category.strip().lower()
    if cat_filter:
        filtered = {k: v for k, v in by_category.items()
                    if k.lower() == cat_filter}
    else:
        filtered = dict(by_category)

    sorted_months = sorted(by_month.items(), reverse=True)[:months]

    return {
        "spending_by_category": {k: round(v, 2) for k, v in
                                  sorted(filtered.items(), key=lambda x: x[1], reverse=True)},
        "monthly_totals": [{"month": m, "total": round(v, 2)} for m, v in sorted_months],
        "total_period_spend": round(sum(v for _, v in sorted_months), 2),
        "months_analysed": months,
    }


TOOLS: dict[str, Callable[..., dict[str, Any]]] = {
    f.__name__: f for f in [
        get_balance, get_monthly_income, get_transactions,
        get_monthly_expenses, get_spending_by_category, get_budget,
        get_upcoming_expenses, get_goals, get_investments,
        get_savings_rate, simulate_purchase, create_alert,
        # Agentic path tools
        get_user_profile, web_search, get_spending_history,
    ]
}

_EXTRA_PARAMS = {
    "simulate_purchase": {
        "amount": {"type": "number", "description": "Purchase amount in INR"},
    },
    "create_alert": {
        "title": {"type": "string"},
        "message": {"type": "string"},
        "severity": {"type": "string", "enum": ["low", "med", "high"]},
    },
    "web_search": {
        "query": {"type": "string", "description": "Search query for live stock price or IPO news"},
    },
    "get_spending_history": {
        "category": {"type": "string",
                     "description": "Expense category to filter by (empty = all categories)"},
        "months": {"type": "integer",
                   "description": "Number of months of history to return (default 3)"},
    },
}
_REQUIRED = {"simulate_purchase": ["amount"],
             "create_alert": ["title", "message"],
             "web_search": ["query"]}

TOOL_SCHEMAS = [
    {
        "type": "function",
        "function": {
            "name": name,
            "description": (fn.__doc__ or "").strip(),
            "parameters": {
                "type": "object",
                "properties": _EXTRA_PARAMS.get(name, {}),
                "required": _REQUIRED.get(name, []),
            }
        }
    }
    for name, fn in TOOLS.items()
]


def run_tool(name: str, db: Session, user_id: int, **kwargs) -> dict[str, Any]:
    if name not in TOOLS:
        return {"error": f"unknown tool {name}"}
    return TOOLS[name](db, user_id, **kwargs)
