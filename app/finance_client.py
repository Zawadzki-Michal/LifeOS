import calendar
import datetime as dt
from zoneinfo import ZoneInfo

from sqlalchemy import func

from app.db import SessionLocal
from app.models import Bill, Expense, ExpenseCategory

TZ = ZoneInfo("Europe/Warsaw")


def _period_bounds(period: str) -> tuple[dt.datetime, str]:
    now_local = dt.datetime.now(TZ)
    if period == "today":
        start_local = now_local.replace(hour=0, minute=0, second=0, microsecond=0)
        label = "today"
    elif period == "week":
        start_local = (now_local - dt.timedelta(days=now_local.weekday())).replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        label = "this week"
    else:
        start_local = now_local.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        label = "this month"
    return start_local.astimezone(dt.timezone.utc), label


def _get_or_create_category(db, name: str) -> ExpenseCategory:
    cat = db.query(ExpenseCategory).filter(ExpenseCategory.name.ilike(name)).first()
    if cat is None:
        cat = ExpenseCategory(name=name)
        db.add(cat)
        db.flush()
    return cat


def _safe_date(year: int, month: int, day: int) -> dt.date:
    last_day = calendar.monthrange(year, month)[1]
    return dt.date(year, month, min(day, last_day))


def _advance_due(due: dt.date, recurrence: str) -> dt.date:
    if recurrence == "yearly":
        return _safe_date(due.year + 1, due.month, due.day)
    if due.month == 12:
        return _safe_date(due.year + 1, 1, due.day)
    return _safe_date(due.year, due.month + 1, due.day)


def _compute_next_due(due_day: int, today: dt.date | None = None) -> dt.date:
    today = today or dt.date.today()
    if due_day >= today.day:
        return _safe_date(today.year, today.month, due_day)
    if today.month == 12:
        return _safe_date(today.year + 1, 1, due_day)
    return _safe_date(today.year, today.month + 1, due_day)


def _post_due_bills(db) -> tuple[list[str], list[str]]:
    """Auto-log an expense for any fixed-amount bill whose due date has arrived,
    then roll it forward to the next cycle. Variable-amount bills are left
    alone (not advanced) until confirmed via log_bill_payment — they're
    reported back as awaiting confirmation instead."""
    today = dt.date.today()
    posted, awaiting = [], []
    dirty = False
    for bill in db.query(Bill).filter(Bill.next_due <= today).all():
        if not bill.amount_is_fixed:
            awaiting.append(bill.name)
            continue
        cat = db.get(ExpenseCategory, bill.category_id) if bill.category_id else None
        if cat is None:
            cat = _get_or_create_category(db, bill.name.strip().lower())
            bill.category_id = cat.id
        due_ts = dt.datetime.combine(bill.next_due, dt.time(12, 0), tzinfo=dt.timezone.utc)
        db.add(
            Expense(
                ts=due_ts,
                amount_pln=bill.amount_pln,
                category_id=cat.id,
                merchant=bill.name,
                note="auto-posted recurring bill",
            )
        )
        posted.append(bill.name)
        bill.next_due = _advance_due(bill.next_due, bill.recurrence)
        dirty = True
    if dirty:
        db.commit()
    return posted, awaiting


async def log_expense(
    amount_pln: float,
    category: str,
    merchant: str | None = None,
    note: str | None = None,
    raw_text: str | None = None,
) -> str:
    category_name = category.strip().lower()
    with SessionLocal() as db:
        cat = _get_or_create_category(db, category_name)
        db.add(
            Expense(
                ts=dt.datetime.now(dt.timezone.utc),
                amount_pln=amount_pln,
                category_id=cat.id,
                merchant=merchant,
                note=note,
                raw_text=raw_text,
            )
        )
        db.commit()
    where = f" at {merchant}" if merchant else ""
    return f"Logged {amount_pln:.2f} PLN under '{category_name}'{where}."


async def add_expense_category(name: str, monthly_budget: float | None = None) -> str:
    name_norm = name.strip().lower()
    with SessionLocal() as db:
        existing = db.query(ExpenseCategory).filter(ExpenseCategory.name.ilike(name_norm)).first()
        if existing:
            if monthly_budget is not None:
                existing.monthly_budget = monthly_budget
                db.commit()
                return f"Category '{name_norm}' already existed — updated its budget to {monthly_budget:.2f} PLN/month."
            return f"Category '{name_norm}' already exists."
        db.add(ExpenseCategory(name=name_norm, monthly_budget=monthly_budget))
        db.commit()
    budget_note = f" with a {monthly_budget:.2f} PLN/month budget" if monthly_budget is not None else ""
    return f"Added new expense category '{name_norm}'{budget_note}."


async def get_spending_summary(period: str = "month", category: str | None = None) -> str:
    start_utc, label = _period_bounds(period)
    with SessionLocal() as db:
        _, awaiting = _post_due_bills(db)
        query = (
            db.query(ExpenseCategory.name, func.sum(Expense.amount_pln), func.count(Expense.id))
            .join(Expense, Expense.category_id == ExpenseCategory.id)
            .filter(Expense.ts >= start_utc)
        )
        if category:
            query = query.filter(ExpenseCategory.name.ilike(category.strip().lower()))
        rows = (
            query.group_by(ExpenseCategory.name)
            .order_by(func.sum(Expense.amount_pln).desc())
            .all()
        )
        budgets = (
            {c.name: c.monthly_budget for c in db.query(ExpenseCategory).all()}
            if period == "month"
            else {}
        )

    awaiting_note = (
        f"\n(Awaiting confirmation, not yet counted: {', '.join(awaiting)} — use "
        f"log_bill_payment once you know the actual amount.)"
        if awaiting
        else ""
    )

    if not rows:
        scope = f" on '{category}'" if category else ""
        return f"No expenses logged {label}{scope}.{awaiting_note}"

    total = sum(float(r[1]) for r in rows)

    if category and len(rows) == 1:
        name, amount, count = rows[0]
        return (
            f"Spent {float(amount):.2f} PLN on '{name}' {label} "
            f"({count} expense{'s' if count != 1 else ''}).{awaiting_note}"
        )

    lines = []
    for name, amount, count in rows:
        amount = float(amount)
        line = f"- {name}: {amount:.2f} PLN ({count})"
        budget = budgets.get(name)
        if budget:
            pct = amount / float(budget) * 100
            line += f" — {pct:.0f}% of {float(budget):.2f} PLN budget"
        lines.append(line)

    return f"Total spending {label}: {total:.2f} PLN\n" + "\n".join(lines) + awaiting_note


async def get_fixed_monthly_overhead() -> str:
    """Total committed recurring cost per month, independent of what's actually
    been posted — i.e. what's locked in before any discretionary spending."""
    with SessionLocal() as db:
        bills = db.query(Bill, ExpenseCategory.name).outerjoin(
            ExpenseCategory, Bill.category_id == ExpenseCategory.id
        ).all()

    if not bills:
        return "No recurring bills on file yet."

    lines = []
    total = 0.0
    for bill, cat_name in bills:
        monthly_equiv = float(bill.amount_pln) if bill.recurrence == "monthly" else float(bill.amount_pln) / 12
        total += monthly_equiv
        tag = "" if bill.amount_is_fixed else " (variable, estimated)"
        lines.append(f"- {bill.name} ({cat_name or 'uncategorized'}): {monthly_equiv:.2f} PLN/month{tag}")

    return f"Fixed monthly overhead: {total:.2f} PLN/month\n" + "\n".join(lines)


async def list_bills(days_ahead: int = 30) -> str:
    with SessionLocal() as db:
        _post_due_bills(db)
        bills = db.query(Bill).order_by(Bill.next_due).all()
        data = [
            (b.id, b.name, float(b.amount_pln), b.next_due, b.recurrence, b.amount_is_fixed)
            for b in bills
        ]

    if not data:
        return "No bills on file yet."

    cutoff = dt.date.today() + dt.timedelta(days=days_ahead)
    upcoming = [b for b in data if b[3] <= cutoff]
    if not upcoming:
        return f"No bills due in the next {days_ahead} days."

    lines = []
    for bill_id, name, amount, due, recurrence, is_fixed in upcoming:
        tag = "" if is_fixed else " (variable amount — needs confirmation when due)"
        lines.append(f"- [{bill_id}] {name}: {amount:.2f} PLN due {due.isoformat()} ({recurrence}){tag}")
    return f"Upcoming bills (next {days_ahead} days):\n" + "\n".join(lines)


async def list_recent_expenses(limit: int = 10, category: str | None = None) -> str:
    with SessionLocal() as db:
        query = db.query(Expense, ExpenseCategory.name).join(
            ExpenseCategory, Expense.category_id == ExpenseCategory.id
        )
        if category:
            query = query.filter(ExpenseCategory.name.ilike(category.strip().lower()))
        rows = query.order_by(Expense.ts.desc()).limit(limit).all()

    if not rows:
        scope = f" in '{category}'" if category else ""
        return f"No expenses logged{scope}."

    lines = []
    for expense, cat_name in rows:
        where = f" at {expense.merchant}" if expense.merchant else ""
        lines.append(
            f"- [{expense.id}] {expense.ts.date().isoformat()}: "
            f"{float(expense.amount_pln):.2f} PLN, {cat_name}{where}"
        )
    return "Recent expenses (id in brackets, needed to delete one):\n" + "\n".join(lines)


async def delete_expense(expense_id: int) -> str:
    with SessionLocal() as db:
        expense = db.get(Expense, expense_id)
        if expense is None:
            return f"No expense found with id {expense_id}."
        db.delete(expense)
        db.commit()
    return f"Deleted expense {expense_id}."


async def delete_bill(name: str | None = None, bill_id: int | None = None) -> str:
    with SessionLocal() as db:
        if bill_id is not None:
            bill = db.get(Bill, bill_id)
            if bill is None:
                return f"No bill found with id {bill_id}."
            bill_name = bill.name
            db.delete(bill)
            db.commit()
            return f"Deleted bill '{bill_name}' (id {bill_id}). It will no longer auto-post as an expense."

        if not name:
            return "Need either a bill name or id to delete."

        matches = db.query(Bill).filter(Bill.name.ilike(name.strip())).all()
        if not matches:
            return f"No bill found named '{name}'."
        if len(matches) > 1:
            options = ", ".join(f"[{b.id}] {b.name} ({b.amount_pln:.2f} PLN)" for b in matches)
            return f"Multiple bills named '{name}' — specify bill_id: {options}"

        bill = matches[0]
        bill_name = bill.name
        db.delete(bill)
        db.commit()
    return f"Deleted bill '{bill_name}'. It will no longer auto-post as an expense."


async def add_bill(
    name: str,
    amount_pln: float,
    due_day: int,
    category: str,
    recurrence: str = "monthly",
    amount_is_fixed: bool = True,
) -> str:
    next_due = _compute_next_due(due_day)

    category_name = category.strip().lower()
    with SessionLocal() as db:
        cat = _get_or_create_category(db, category_name)
        db.add(
            Bill(
                name=name,
                amount_pln=amount_pln,
                due_day=due_day,
                recurrence=recurrence,
                next_due=next_due,
                category_id=cat.id,
                amount_is_fixed=amount_is_fixed,
            )
        )
        db.commit()

    if amount_is_fixed:
        posting_note = "It'll be counted as an expense automatically each cycle once due — no need to log it manually."
    else:
        posting_note = (
            "Since its amount varies, it won't auto-post — when it's due you'll be "
            "asked to confirm the actual amount via log_bill_payment."
        )
    return (
        f"Added bill '{name}': {amount_pln:.2f} PLN under '{category_name}', due day "
        f"{due_day} of each {'month' if recurrence == 'monthly' else 'year'} (next due "
        f"{next_due.isoformat()}). {posting_note}"
    )


async def update_bill(
    name: str,
    new_name: str | None = None,
    amount_pln: float | None = None,
    due_day: int | None = None,
    recurrence: str | None = None,
    category: str | None = None,
    amount_is_fixed: bool | None = None,
) -> str:
    with SessionLocal() as db:
        matches = db.query(Bill).filter(Bill.name.ilike(name.strip())).all()
        if not matches:
            return f"No bill found named '{name}'."
        if len(matches) > 1:
            options = ", ".join(f"[{b.id}] {b.name} ({b.amount_pln:.2f} PLN)" for b in matches)
            return f"Multiple bills named '{name}' — be more specific: {options}"

        bill = matches[0]
        changes = []
        if new_name is not None:
            bill.name = new_name
            changes.append(f"name -> '{new_name}'")
        if amount_pln is not None:
            bill.amount_pln = amount_pln
            changes.append(f"amount -> {amount_pln:.2f} PLN")
        if due_day is not None:
            bill.due_day = due_day
            bill.next_due = _compute_next_due(due_day)
            changes.append(f"due day -> {due_day} (next due {bill.next_due.isoformat()})")
        if recurrence is not None:
            bill.recurrence = recurrence
            changes.append(f"recurrence -> {recurrence}")
        if category is not None:
            cat = _get_or_create_category(db, category.strip().lower())
            bill.category_id = cat.id
            changes.append(f"category -> {category.strip().lower()}")
        if amount_is_fixed is not None:
            bill.amount_is_fixed = amount_is_fixed
            changes.append(f"amount_is_fixed -> {amount_is_fixed}")

        if not changes:
            return "Nothing to update."

        bill_name = bill.name
        db.commit()
    return f"Updated bill '{bill_name}': " + ", ".join(changes) + "."


async def log_bill_payment(name: str, amount_pln: float) -> str:
    """Confirm the actual amount for a due variable-amount bill (or override a
    fixed one for a single cycle), post it as an expense, and roll the bill's
    due date forward."""
    with SessionLocal() as db:
        matches = db.query(Bill).filter(Bill.name.ilike(name.strip())).all()
        if not matches:
            return f"No bill found named '{name}'."
        if len(matches) > 1:
            options = ", ".join(f"[{b.id}] {b.name}" for b in matches)
            return f"Multiple bills named '{name}' — specify which: {options}"

        bill = matches[0]
        cat = db.get(ExpenseCategory, bill.category_id) if bill.category_id else None
        if cat is None:
            cat = _get_or_create_category(db, bill.name.strip().lower())
            bill.category_id = cat.id

        due_ts = dt.datetime.combine(bill.next_due, dt.time(12, 0), tzinfo=dt.timezone.utc)
        db.add(
            Expense(
                ts=due_ts,
                amount_pln=amount_pln,
                category_id=cat.id,
                merchant=bill.name,
                note="bill payment (confirmed)",
            )
        )
        bill_name = bill.name
        bill.next_due = _advance_due(bill.next_due, bill.recurrence)
        next_due = bill.next_due
        db.commit()
    return f"Logged {amount_pln:.2f} PLN for '{bill_name}'. Next due {next_due.isoformat()}."


# --- Used by the daily proactive scheduler (app/scheduler.py), not LLM tools ---


def bills_due_for_reminder(db) -> list[Bill]:
    """Bills exactly reminder_days_before days from due — fires once per cycle
    since the gap only equals that value on one specific day."""
    today = dt.date.today()
    return [
        b
        for b in db.query(Bill).all()
        if (b.next_due - today).days == b.reminder_days_before
    ]


def check_budget_alerts(db) -> list[str]:
    """Returns human-readable alert messages for categories that just crossed
    the 80% or 100% monthly-budget threshold for the first time this month."""
    start_utc, _ = _period_bounds("month")
    month_key = dt.date.today().strftime("%Y-%m")
    alerts = []

    categories = db.query(ExpenseCategory).filter(ExpenseCategory.monthly_budget.isnot(None)).all()
    for cat in categories:
        spent = (
            db.query(func.sum(Expense.amount_pln))
            .filter(Expense.category_id == cat.id, Expense.ts >= start_utc)
            .scalar()
        )
        spent = float(spent or 0)
        budget = float(cat.monthly_budget)
        if budget <= 0:
            continue
        pct = spent / budget * 100
        tier = 100 if pct >= 100 else (80 if pct >= 80 else None)
        if tier is None:
            continue

        last = cat.last_budget_alert or ""
        last_month, _, last_tier = last.partition(":")
        already_alerted = last_month == month_key and last_tier and int(last_tier) >= tier
        if already_alerted:
            continue

        cat.last_budget_alert = f"{month_key}:{tier}"
        verb = "blown past" if tier == 100 else "hit"
        alerts.append(
            f"Budget alert: '{cat.name}' has {verb} {tier}% of its {budget:.2f} PLN "
            f"monthly budget ({spent:.2f} PLN spent so far)."
        )

    if alerts:
        db.commit()
    return alerts
