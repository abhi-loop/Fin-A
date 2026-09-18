"""Seed realistic Indian demo data: python -m app.seed"""
from datetime import date

from .database import Base, SessionLocal, engine
from .models import (Alert, Budget, Goal, Investment, Transaction,
                     UpcomingExpense, User)

TX = [
    (18, "Swiggy", "Food", -450), (18, "Metro Card", "Travel", -200),
    (17, "Amazon", "Shopping", -2300), (16, "Uber", "Travel", -320),
    (16, "Zomato", "Food", -680), (15, "Salary", "Salary", 60000),
    (14, "Electricity Bill", "Bills", -1850),
    (13, "BookMyShow", "Entertainment", -900),
    (12, "Big Bazaar", "Food", -3200), (11, "Myntra", "Shopping", -4500),
    (10, "Apollo Pharmacy", "Healthcare", -1240), (8, "Rent", "Bills", -12000),
    (6, "Udemy Course", "Education", -1499),
    (4, "Indigo Flight", "Travel", -3980),
    (2, "Netflix", "Entertainment", -649), (1, "Blinkit", "Food", -1120),
]
BUDGETS = [("Food", 10000), ("Travel", 8000), ("Shopping", 7000),
           ("Entertainment", 5000), ("Bills", 15000), ("Healthcare", 3000)]
GOALS = [("New Laptop", 120000, 70000, "March 2027"),
         ("Emergency Fund", 200000, 86000, "December 2027"),
         ("Goa Trip", 45000, 31500, "January 2027")]
UPCOMING = [("Rent (October)", 12000, "01 Oct"), ("Insurance premium", 4200, "05 Oct"),
            ("Broadband", 1200, "21 Sep"), ("Credit card due", 600, "25 Sep")]
INV = [("Nifty 50 Index Fund", "Equity", 60000, 71200),
       ("Parag Parikh Flexi Cap", "Equity", 40000, 47800),
       ("SBI Gold ETF", "Gold", 25000, 27400),
       ("Fixed Deposit", "Debt", 50000, 52600)]
ALERTS = [("budget", "Budget Warning",
           "Shopping spending has reached 97% of your monthly budget.",
           "high", "Budget"),
          ("goal", "Savings Insight",
           "You need about Rs 4,200/month to stay on track for New Laptop.",
           "med", "Goals"),
          ("pattern", "Spending Pattern",
           "Dining expenses rose 18% compared with last month.", "med", "Spending")]


def run() -> None:
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    user = User(name="Aarav", email="demo@finagent.in", password="demo1234",
                balance=85400, monthly_income=60000)
    db.add(user)
    db.flush()

    for day, desc, cat, amt in TX:
        db.add(Transaction(user_id=user.id, amount=amt,
                           type="income" if amt > 0 else "expense",
                           category=cat, description=desc,
                           date=date(2026, 9, day)))
    for cat, lim in BUDGETS:
        db.add(Budget(user_id=user.id, category=cat, limit_amount=lim,
                      month="2026-09"))
    for name, tgt, saved, dl in GOALS:
        db.add(Goal(user_id=user.id, name=name, target_amount=tgt,
                    saved_amount=saved, deadline=dl))
    for name, amt, due in UPCOMING:
        db.add(UpcomingExpense(user_id=user.id, name=name, amount=amt,
                               due_date=due))
    for asset, kind, inv, cur in INV:
        db.add(Investment(user_id=user.id, asset=asset, asset_type=kind,
                          invested_amount=inv, current_value=cur))
    for kind, title, msg, sev, cat in ALERTS:
        db.add(Alert(user_id=user.id, type=kind, title=title, message=msg,
                     severity=sev, category=cat))
    db.commit()
    db.close()
    print("Seeded demo user demo@finagent.in / demo1234")


if __name__ == "__main__":
    run()
