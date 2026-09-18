from datetime import date
from typing import Literal, Optional
from pydantic import BaseModel, EmailStr


class LoginIn(BaseModel):
    email: EmailStr
    password: str


class RegisterIn(LoginIn):
    name: str


class TransactionIn(BaseModel):
    amount: float
    type: Literal["income", "expense"]
    category: str
    description: str
    date: Optional[date] = None


class TransactionOut(TransactionIn):
    id: int
    date: date

    model_config = {"from_attributes": True}


class BudgetIn(BaseModel):
    category: str
    limit_amount: float
    month: str


class GoalIn(BaseModel):
    name: str
    target_amount: float
    saved_amount: float = 0
    deadline: str


class ChatIn(BaseModel):
    message: str


class Metric(BaseModel):
    label: str
    value: str


class ChatOut(BaseModel):
    answer: str
    metrics: list[Metric] = []
    insights: list[str] = []
    sources: list[str] = []
    tools_used: list[str] = []
