from datetime import date

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..agent import agent
from ..database import get_db
from ..models import (Alert, Budget, Goal, Investment, Transaction, User)
from ..schemas import (BudgetIn, ChatIn, ChatOut, GoalIn, LoginIn, RegisterIn,
                       TransactionIn, TransactionOut)
from ..tools import finance_tools as T

router = APIRouter(prefix="/api")

# Single-user demo auth. Swap for real JWT before anything leaves the hackathon.
DEMO_USER_ID = 1


def current_user_id() -> int:
    return DEMO_USER_ID


# ---------- auth ----------
@router.post("/auth/login")
def login(body: LoginIn, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == body.email).first()
    if not user or user.password != body.password:
        raise HTTPException(401, "Invalid email or password")
    return {"token": f"demo-token-{user.id}",
            "user": {"id": user.id, "name": user.name, "email": user.email}}


@router.post("/auth/register")
def register(body: RegisterIn, db: Session = Depends(get_db)):
    if db.query(User).filter(User.email == body.email).first():
        raise HTTPException(409, "Email already registered")
    user = User(name=body.name, email=body.email, password=body.password,
                balance=0, monthly_income=0)
    db.add(user)
    db.commit()
    return {"token": f"demo-token-{user.id}",
            "user": {"id": user.id, "name": user.name, "email": user.email}}


# ---------- dashboard ----------
@router.get("/dashboard")
def dashboard(db: Session = Depends(get_db), uid: int = Depends(current_user_id)):
    user = db.query(User).get(uid)
    savings = T.get_savings_rate(db, uid)
    return {
        "user": {"name": user.name},
        "balance": user.balance,
        "income": savings["income"],
        "expenses": savings["expenses"],
        "savings": savings["savings"],
        "savingsRatePct": savings["savings_rate_pct"],
        "spendingByCategory": T.get_spending_by_category(db, uid)["spending"],
        "budget": T.get_budget(db, uid)["budget"],
        "goals": T.get_goals(db, uid)["goals"],
        "recentTransactions": T.get_transactions(db, uid, limit=5)["transactions"],
        "alerts": [{"title": a.title, "message": a.message, "severity": a.severity}
                   for a in db.query(Alert).filter(Alert.user_id == uid)
                   .order_by(Alert.created_at.desc()).limit(3)],
        "trend": [28900, 31200, 29600, 34800, 30400,
                  T.get_monthly_expenses(db, uid)["total_expenses"]],
    }


# ---------- transactions ----------
@router.get("/transactions", response_model=list[TransactionOut])
def list_transactions(db: Session = Depends(get_db),
                      uid: int = Depends(current_user_id)):
    return (db.query(Transaction).filter(Transaction.user_id == uid)
            .order_by(Transaction.date.desc()).all())


@router.post("/transactions", response_model=TransactionOut, status_code=201)
def create_transaction(body: TransactionIn, db: Session = Depends(get_db),
                       uid: int = Depends(current_user_id)):
    amount = -abs(body.amount) if body.type == "expense" else abs(body.amount)
    tx = Transaction(user_id=uid, amount=amount, type=body.type,
                     category=body.category, description=body.description,
                     date=body.date or date.today())
    db.add(tx)
    db.commit()
    db.refresh(tx)
    return tx


@router.put("/transactions/{tx_id}", response_model=TransactionOut)
def update_transaction(tx_id: int, body: TransactionIn,
                       db: Session = Depends(get_db),
                       uid: int = Depends(current_user_id)):
    tx = db.query(Transaction).filter(Transaction.id == tx_id,
                                      Transaction.user_id == uid).first()
    if not tx:
        raise HTTPException(404, "Transaction not found")
    tx.amount = -abs(body.amount) if body.type == "expense" else abs(body.amount)
    tx.type, tx.category = body.type, body.category
    tx.description = body.description
    if body.date:
        tx.date = body.date
    db.commit()
    db.refresh(tx)
    return tx


@router.delete("/transactions/{tx_id}", status_code=204)
def delete_transaction(tx_id: int, db: Session = Depends(get_db),
                       uid: int = Depends(current_user_id)):
    tx = db.query(Transaction).filter(Transaction.id == tx_id,
                                      Transaction.user_id == uid).first()
    if not tx:
        raise HTTPException(404, "Transaction not found")
    db.delete(tx)
    db.commit()


# ---------- budget / goals / investments / alerts ----------
@router.get("/budget")
def get_budget(db: Session = Depends(get_db), uid: int = Depends(current_user_id)):
    return T.get_budget(db, uid)


@router.post("/budget", status_code=201)
def set_budget(body: BudgetIn, db: Session = Depends(get_db),
               uid: int = Depends(current_user_id)):
    row = db.query(Budget).filter(Budget.user_id == uid,
                                  Budget.category == body.category,
                                  Budget.month == body.month).first()
    if row:
        row.limit_amount = body.limit_amount
    else:
        db.add(Budget(user_id=uid, category=body.category,
                      limit_amount=body.limit_amount, month=body.month))
    db.commit()
    return T.get_budget(db, uid)


@router.get("/goals")
def list_goals(db: Session = Depends(get_db), uid: int = Depends(current_user_id)):
    return T.get_goals(db, uid)


@router.post("/goals", status_code=201)
def create_goal(body: GoalIn, db: Session = Depends(get_db),
                uid: int = Depends(current_user_id)):
    db.add(Goal(user_id=uid, name=body.name, target_amount=body.target_amount,
                saved_amount=body.saved_amount, deadline=body.deadline))
    db.commit()
    return T.get_goals(db, uid)


@router.put("/goals/{goal_id}")
def update_goal(goal_id: int, body: GoalIn, db: Session = Depends(get_db),
                uid: int = Depends(current_user_id)):
    g = db.query(Goal).filter(Goal.id == goal_id, Goal.user_id == uid).first()
    if not g:
        raise HTTPException(404, "Goal not found")
    g.name, g.target_amount = body.name, body.target_amount
    g.saved_amount, g.deadline = body.saved_amount, body.deadline
    db.commit()
    return T.get_goals(db, uid)


@router.get("/investments")
def list_investments(db: Session = Depends(get_db),
                     uid: int = Depends(current_user_id)):
    return T.get_investments(db, uid)


@router.get("/alerts")
def list_alerts(db: Session = Depends(get_db), uid: int = Depends(current_user_id)):
    rows = (db.query(Alert).filter(Alert.user_id == uid)
            .order_by(Alert.created_at.desc()).all())
    return [{"id": a.id, "title": a.title, "message": a.message,
             "severity": a.severity, "category": a.category, "read": a.read,
             "createdAt": a.created_at.isoformat()} for a in rows]


@router.put("/alerts/{alert_id}/read")
def mark_read(alert_id: int, db: Session = Depends(get_db),
              uid: int = Depends(current_user_id)):
    a = db.query(Alert).filter(Alert.id == alert_id, Alert.user_id == uid).first()
    if not a:
        raise HTTPException(404, "Alert not found")
    a.read = True
    db.commit()
    return {"ok": True}


# ---------- the agent ----------
@router.post("/ai/chat", response_model=ChatOut)
def ai_chat(body: ChatIn, db: Session = Depends(get_db),
            uid: int = Depends(current_user_id)):
    if not body.message.strip():
        raise HTTPException(400, "Message cannot be empty")
    return agent.answer(db, uid, body.message.strip())
