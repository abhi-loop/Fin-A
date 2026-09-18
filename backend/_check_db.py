from app.database import engine
from sqlalchemy import text

e = engine.connect()
tables = [r[0] for r in e.execute(text("SELECT tablename FROM pg_tables WHERE schemaname='public'"))]
print('tables:', tables)
for t in ['users', 'transactions', 'budgets', 'goals', 'alerts']:
    if t in tables:
        n = e.execute(text(f'SELECT COUNT(*) FROM {t}')).scalar()
        print(f'{t} rows: {n}')
if 'users' in tables:
    for r in e.execute(text('SELECT id, email, supabase_uid FROM users')).fetchall():
        print(' user:', r)
