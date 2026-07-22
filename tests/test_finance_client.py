import datetime as dt

import pytest

from app import finance_client
from app.db import SessionLocal
from app.models import Bill, ExpenseCategory


async def test_log_expense_auto_creates_category():
    reply = await finance_client.log_expense(42.50, "Groceries", merchant="Biedronka")
    assert "42.50" in reply
    assert "groceries" in reply

    with SessionLocal() as db:
        cat = db.query(ExpenseCategory).filter(ExpenseCategory.name == "groceries").one()
        assert cat is not None


async def test_log_expense_reuses_existing_category_case_insensitive():
    await finance_client.add_expense_category("Fuel")
    await finance_client.log_expense(100, "fuel")
    await finance_client.log_expense(50, "FUEL")

    with SessionLocal() as db:
        cats = db.query(ExpenseCategory).filter(ExpenseCategory.name == "fuel").all()
        assert len(cats) == 1


async def test_spending_summary_reports_budget_percentage():
    await finance_client.add_expense_category("subscriptions", monthly_budget=100)
    await finance_client.log_expense(80, "subscriptions")

    summary = await finance_client.get_spending_summary("month")
    assert "80% of 100.00 PLN budget" in summary


async def test_spending_summary_empty_state():
    summary = await finance_client.get_spending_summary("today")
    assert "No expenses logged" in summary


@pytest.mark.parametrize(
    "due_day,today,expected_month_offset",
    [
        (15, dt.date(2026, 7, 10), 0),  # due day hasn't passed yet this month
        (5, dt.date(2026, 7, 10), 1),  # due day already passed -> next month
    ],
)
def test_compute_next_due(due_day, today, expected_month_offset):
    result = finance_client._compute_next_due(due_day, today)
    expected_month = today.month + expected_month_offset
    assert result.month == expected_month
    assert result.day == due_day


def test_compute_next_due_clamps_when_rolling_into_a_shorter_month():
    # due_day 30, already past on Jan 31 -> rolls to Feb, which has no 30th
    # in 2026 (not a leap year) -> must clamp to Feb 28, not crash.
    result = finance_client._compute_next_due(30, dt.date(2026, 1, 31))
    assert result == dt.date(2026, 2, 28)


def test_safe_date_clamps_to_last_day_of_month():
    assert finance_client._safe_date(2026, 2, 31) == dt.date(2026, 2, 28)
    assert finance_client._safe_date(2024, 2, 30) == dt.date(2024, 2, 29)  # leap year


def test_advance_due_rolls_over_year_boundary():
    result = finance_client._advance_due(dt.date(2026, 12, 20), "monthly")
    assert result == dt.date(2027, 1, 20)


def test_advance_due_yearly():
    result = finance_client._advance_due(dt.date(2026, 3, 10), "yearly")
    assert result == dt.date(2027, 3, 10)


async def test_fixed_bill_auto_posts_when_due_and_rolls_forward():
    await finance_client.add_bill(
        "Mortgage", 2550, due_day=1, category="mortgage", recurrence="monthly"
    )
    with SessionLocal() as db:
        bill = db.query(Bill).filter(Bill.name == "Mortgage").one()
        bill.next_due = dt.date.today() - dt.timedelta(days=1)  # force it overdue
        db.commit()
        old_due = bill.next_due

    # get_spending_summary calls _post_due_bills internally, same as the
    # real on-demand and scheduled paths.
    summary = await finance_client.get_spending_summary("month")
    assert "2550.00" in summary or "mortgage" in summary.lower()

    with SessionLocal() as db:
        bill = db.query(Bill).filter(Bill.name == "Mortgage").one()
        assert bill.next_due > old_due


async def test_variable_bill_does_not_auto_post():
    await finance_client.add_bill(
        "Electricity",
        150,
        due_day=1,
        category="bills",
        recurrence="monthly",
        amount_is_fixed=False,
    )
    with SessionLocal() as db:
        bill = db.query(Bill).filter(Bill.name == "Electricity").one()
        bill.next_due = dt.date.today() - dt.timedelta(days=1)
        db.commit()
        original_due = bill.next_due

    summary = await finance_client.get_spending_summary("month")
    assert "Electricity" in summary
    assert "Awaiting confirmation" in summary

    with SessionLocal() as db:
        bill = db.query(Bill).filter(Bill.name == "Electricity").one()
        # Variable bills must NOT be advanced or posted until confirmed.
        assert bill.next_due == original_due


async def test_log_bill_payment_posts_expense_and_advances_due():
    await finance_client.add_bill(
        "Water", 80, due_day=1, category="bills", recurrence="monthly", amount_is_fixed=False
    )
    with SessionLocal() as db:
        bill = db.query(Bill).filter(Bill.name == "Water").one()
        original_due = bill.next_due

    reply = await finance_client.log_bill_payment("Water", 95.30)
    assert "95.30" in reply

    with SessionLocal() as db:
        bill = db.query(Bill).filter(Bill.name == "Water").one()
        assert bill.next_due > original_due

    expenses = await finance_client.list_recent_expenses(limit=5)
    assert "95.30" in expenses


async def test_delete_bill_by_name_stops_further_autopost():
    await finance_client.add_bill("Netflix", 45, due_day=10, category="subscriptions")
    reply = await finance_client.delete_bill(name="Netflix")
    assert "Deleted bill 'Netflix'" in reply

    with SessionLocal() as db:
        assert db.query(Bill).filter(Bill.name == "Netflix").first() is None


async def test_delete_bill_ambiguous_name_asks_for_id():
    await finance_client.add_bill("Insurance", 50, due_day=1, category="insurance")
    await finance_client.add_bill("Insurance", 30, due_day=15, category="insurance")

    reply = await finance_client.delete_bill(name="Insurance")
    assert "Multiple bills named" in reply

    with SessionLocal() as db:
        assert db.query(Bill).filter(Bill.name == "Insurance").count() == 2


def test_check_budget_alerts_fires_once_per_threshold():
    with SessionLocal() as db:
        cat = ExpenseCategory(name="groceries", monthly_budget=100)
        db.add(cat)
        db.commit()
        db.refresh(cat)
        cat_id = cat.id

    import asyncio

    asyncio.run(finance_client.log_expense(85, "groceries"))

    with SessionLocal() as db:
        alerts = finance_client.check_budget_alerts(db)
        assert len(alerts) == 1
        assert "80%" in alerts[0]

        # Same spend level again shouldn't re-fire the same threshold.
        alerts_again = finance_client.check_budget_alerts(db)
        assert alerts_again == []
