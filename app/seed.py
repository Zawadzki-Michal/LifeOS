import datetime as dt

from sqlalchemy.orm import Session

from app.models import (
    ExpenseCategory,
    Goal,
    GoalProgress,
    HouseholdMember,
    MetricDaily,
    SavedPlace,
    User,
    UserFact,
)

EXPENSE_CATEGORIES = [
    "transportation",
    "fuel",
    "groceries",
    "subscriptions",
    "bills",
    "loans",
    "mortgage",
    "insurance",
    "savings",
    "kids",
    "clothes",
    "events",
    "gadgets",
    "other",
]


def _seed_user(db: Session) -> None:
    if db.query(User).first() is not None:
        return
    db.add(
        User(
            name="Michał",
            tz="Europe/Warsaw",
            locale="en",
            tone_profile="coach-motivating",
        )
    )


def _seed_household(db: Session) -> None:
    if db.query(HouseholdMember).first() is not None:
        return
    db.add_all(
        [
            HouseholdMember(relation="wife", name="Ania"),
            HouseholdMember(relation="daughter", name="Martina", notes="age 7 (as of 2026)"),
            HouseholdMember(relation="son", name="Jakub (Kuba)", notes="age 5 (as of 2026)"),
        ]
    )


def _seed_goals(db: Session) -> None:
    if db.query(Goal).first() is not None:
        return
    goals = [
        Goal(
            kind="deadline",
            title="Pass CKA exam",
            target_date=dt.date(2026, 11, 30),
            cadence="daily study hrs, 3-5 hr/week target",
        ),
        Goal(
            kind="deadline",
            title="Pass CKAD exam (after CKA)",
            target_date=dt.date(2026, 11, 30),
            cadence="daily study hrs, 3-5 hr/week target",
        ),
        Goal(
            kind="trajectory",
            title="Lose weight 105→90 kg",
            target_value="90 kg",
            cadence="weekly weigh-in, ~0.4 kg/week",
        ),
        Goal(
            kind="trajectory",
            title="Save for Harley by 40th birthday",
            target_value="5-10k PLN own savings, ~40k PLN total",
            cadence="monthly deposit tracking",
        ),
        Goal(kind="frequency", title="Gym sessions", target_value="2-3/week", cadence="weekly"),
        Goal(kind="frequency", title="Squash sessions", target_value="2-3/week", cadence="weekly"),
        Goal(
            kind="frequency",
            title="Dedicated wife evening",
            target_value="1/week",
            cadence="weekly",
        ),
        Goal(
            kind="frequency",
            title="Weekend kids fun activity",
            target_value="1/week",
            cadence="weekly",
        ),
    ]
    db.add_all(goals)
    db.flush()

    weight_goal = next(g for g in goals if g.title.startswith("Lose weight"))
    db.add(
        GoalProgress(
            goal_id=weight_goal.id,
            ts=dt.datetime.now(dt.timezone.utc),
            value="105",
            note="starting weight, provided by user",
        )
    )


def _seed_metrics(db: Session) -> None:
    if db.query(MetricDaily).first() is not None:
        return
    db.add(MetricDaily(date=dt.date.today(), weight_kg=105))


def _seed_facts(db: Session) -> None:
    if db.query(UserFact).first() is not None:
        return
    now = dt.datetime.now(dt.timezone.utc)
    db.add_all(
        [
            UserFact(
                key="occupation",
                value="Junior System Engineer at Backbase, Kraków (Pawia Street office)",
                confidence=1,
                confirmed_bool=True,
                created_at=now,
            ),
            UserFact(
                key="squash_partners",
                value="Plays squash with trainer Janek and mom Maria",
                confidence=1,
                confirmed_bool=True,
                created_at=now,
            ),
        ]
    )


def _seed_expense_categories(db: Session) -> None:
    existing = {c.name for c in db.query(ExpenseCategory).all()}
    db.add_all(
        ExpenseCategory(name=name) for name in EXPENSE_CATEGORIES if name not in existing
    )


def _seed_places(db: Session) -> None:
    if db.query(SavedPlace).first() is not None:
        return
    db.add(
        SavedPlace(
            name="home",
            address="Juliusza Kossaka 30B, Nowy Wiśnicz, Poland",
        )
    )


def seed_initial_data(db: Session) -> None:
    _seed_user(db)
    _seed_household(db)
    _seed_goals(db)
    _seed_metrics(db)
    _seed_facts(db)
    _seed_expense_categories(db)
    _seed_places(db)
    db.commit()
