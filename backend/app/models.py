from datetime import date, datetime
from sqlalchemy import String, Float, Integer, Boolean, Date, DateTime, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column
from .database import Base


class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(80))
    email: Mapped[str] = mapped_column(String(160), unique=True, index=True)
    supabase_uid: Mapped[str | None] = mapped_column(String(255), unique=True, index=True, nullable=True)
    balance: Mapped[float] = mapped_column(Float, default=0)
    monthly_income: Mapped[float] = mapped_column(Float, default=0)


class Transaction(Base):
    __tablename__ = "transactions"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    amount: Mapped[float] = mapped_column(Float)          # negative = expense
    type: Mapped[str] = mapped_column(String(10))          # income | expense
    category: Mapped[str] = mapped_column(String(40))
    description: Mapped[str] = mapped_column(String(160))
    date: Mapped[date] = mapped_column(Date, default=date.today)


class Budget(Base):
    __tablename__ = "budgets"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    category: Mapped[str] = mapped_column(String(40))
    limit_amount: Mapped[float] = mapped_column(Float)
    month: Mapped[str] = mapped_column(String(7))          # YYYY-MM


class Goal(Base):
    __tablename__ = "goals"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    name: Mapped[str] = mapped_column(String(80))
    target_amount: Mapped[float] = mapped_column(Float)
    saved_amount: Mapped[float] = mapped_column(Float, default=0)
    deadline: Mapped[str] = mapped_column(String(40))


class UpcomingExpense(Base):
    __tablename__ = "upcoming_expenses"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    name: Mapped[str] = mapped_column(String(80))
    amount: Mapped[float] = mapped_column(Float)
    due_date: Mapped[str] = mapped_column(String(40))


class Investment(Base):
    __tablename__ = "investments"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    asset: Mapped[str] = mapped_column(String(80))
    asset_type: Mapped[str] = mapped_column(String(30))
    quantity: Mapped[float] = mapped_column(Float, default=1)
    invested_amount: Mapped[float] = mapped_column(Float)
    current_value: Mapped[float] = mapped_column(Float)


class Alert(Base):
    __tablename__ = "alerts"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    type: Mapped[str] = mapped_column(String(40))
    title: Mapped[str] = mapped_column(String(120))
    message: Mapped[str] = mapped_column(String(400))
    severity: Mapped[str] = mapped_column(String(10), default="med")
    category: Mapped[str] = mapped_column(String(40), default="General")
    read: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
