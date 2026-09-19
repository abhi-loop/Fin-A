from . import agentic, structured
from .router import classify

_STRUCTURED_INTENTS = {
    "expense_log",
    "budget_query",
}

_AGENTIC_INTENTS = {
    "investment_query",
    "goal_planning",
    "ipo_alert",
}

_OUT_OF_SCOPE_REPLY = {
    "answer": (
        "I can help with your expenses, budgets, investments, "
        "financial goals, and IPO alerts."
    ),
    "intent": "out_of_scope",
    "tools_used": [],
}


def answer(db, user_id, question):
    route = classify(question)

    if route.intent in _STRUCTURED_INTENTS:
        return structured.handle(
            db,
            user_id,
            route,
        )

    if route.intent in _AGENTIC_INTENTS:
        return agentic.handle(
            db,
            user_id,
            question,
            route,
        )

    return _OUT_OF_SCOPE_REPLY