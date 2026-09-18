from datetime import date
from typing import Optional
from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..agent import agent
from ..config import SUPABASE_JWT_SECRET
from ..database import get_db
from ..models import (Alert, Budget, Goal, Investment, Transaction, User)
from ..schemas import (BudgetIn, ChatIn, ChatOut, GoalIn,
                       TransactionIn, TransactionOut)
from ..tools import finance_tools as T

router = APIRouter(prefix="/api")

DEMO_USER_ID = 1


def current_user_id(authorization: Optional[str] = Header(None),
                    db: Session = Depends(get_db)) -> int:
    """Verify Supabase JWT → extract UUID → resolve to integer user_id.
    Falls back to DEMO_USER_ID when no token / no Supabase secret configured."""
    if not authorization or not authorization.startswith("Bearer "):
        return DEMO_USER_ID

    token = authorization.split(" ", 1)[1]

    # Legacy demo-token support (for local dev without Supabase)
    if token.startswith("demo-token-"):
        try:
            return int(token.replace("demo-token-", ""))
        except ValueError:
            return DEMO_USER_ID

    # Verify Supabase JWT using PyJWT
    if not SUPABASE_JWT_SECRET:
        return DEMO_USER_ID

    import jwt as pyjwt

    try:
        # Peek at the header to get the actual algorithm
        header = pyjwt.get_unverified_header(token)
        alg = header.get("alg", "HS256")
        print(f"[JWT] alg={alg}", flush=True)

        if alg in ("HS256", "HS384", "HS512"):
            payload = pyjwt.decode(
                token,
                SUPABASE_JWT_SECRET,
                algorithms=[alg],
                options={"verify_aud": False},
            )
        elif alg in ("RS256", "RS384", "RS512",
                     "ES256", "ES384", "ES512"):
            from ..config import SUPABASE_URL
            print(f"[JWT] RS alg — fetching JWKS from {SUPABASE_URL}", flush=True)
            jwks_url = f"{SUPABASE_URL}/auth/v1/.well-known/jwks.json"
            signing_key = pyjwt.PyJWKClient(jwks_url).get_signing_key_from_jwt(token).key
            payload = pyjwt.decode(
                token,
                signing_key,
                algorithms=[alg],
                options={"verify_aud": False},
            )
        else:
            raise HTTPException(401, f"Unsupported JWT algorithm: {alg}")

        supabase_uid = payload.get("sub")
        if not supabase_uid:
            raise HTTPException(401, "Invalid token: missing sub")
        print(f"[JWT] OK uid={supabase_uid[:8]}...", flush=True)
    except HTTPException:
        raise
    except Exception as exc:
        print(f"[JWT] FAILED {type(exc).__name__}: {exc}", flush=True)
        raise HTTPException(401, f"Token verification failed: {exc}")

    # Look up or auto-create the User row
    user = db.query(User).filter(User.supabase_uid == supabase_uid).first()
    if not user:
        # Auto-create from JWT claims
        email = payload.get("email", "")
        user = db.query(User).filter(User.email == email).first()
        if user:
            # Existing user by email — link their Supabase UID
            user.supabase_uid = supabase_uid
            db.commit()
        else:
            user = User(
                name=email.split("@")[0],
                email=email,
                supabase_uid=supabase_uid,
                balance=0,
                monthly_income=0,
            )
            db.add(user)
            db.commit()
            db.refresh(user)

    return user.id


# ---------- auth sync ----------
class SyncIn(BaseModel):
    name: str = ""


@router.post("/auth/sync")
def auth_sync(body: SyncIn, db: Session = Depends(get_db),
              uid: int = Depends(current_user_id)):
    """Ensure the backend User row exists and optionally update the name."""
    user = db.query(User).filter(User.id == uid).first()
    if not user:
        raise HTTPException(404, "User not found")
    if body.name and user.name != body.name:
        user.name = body.name
        db.commit()
    return {"id": user.id, "name": user.name, "email": user.email}


# ---------- dashboard ----------
@router.get("/dashboard")
def dashboard(db: Session = Depends(get_db), uid: int = Depends(current_user_id)):
    user = db.query(User).get(uid)
    savings = T.get_savings_rate(db, uid)
    
    # Calculate real 6-month trend
    today = date.today()
    expenses_by_month = {}
    for tx in db.query(Transaction).filter(Transaction.user_id == uid, Transaction.amount < 0).all():
        key = (tx.date.year, tx.date.month)
        expenses_by_month[key] = expenses_by_month.get(key, 0) + (-tx.amount)
        
    real_trend = []
    for i in range(5, -1, -1):
        m = today.month - i
        y = today.year
        if m <= 0:
            m += 12
            y -= 1
        real_trend.append(round(expenses_by_month.get((y, m), 0), 2))

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
        "trend": real_trend,
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
    
    # Update balance
    user = db.query(User).filter(User.id == uid).first()
    if user:
        user.balance += amount
        
    db.commit()
    db.refresh(tx)
    
    # Trigger budget check & alert if expense
    if body.type == "expense":
        T.check_and_trigger_budget_alert(db, uid, body.category)
        
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
