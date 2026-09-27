from __future__ import annotations

from datetime import date

import pytest

from app.services.billing import add_months, compute_billing, current_period_index

D = date


@pytest.mark.parametrize(
    ("anchor", "months", "expected"),
    [
        (D(2026, 1, 31), 1, D(2026, 2, 28)),  # month-end clamp
        (D(2028, 1, 31), 1, D(2028, 2, 29)),  # leap year
        (D(2026, 1, 31), 2, D(2026, 3, 31)),  # back to 31 after a short month (anchored, not chained)
        (D(2026, 1, 30), 1, D(2026, 2, 28)),
        (D(2026, 3, 31), 1, D(2026, 4, 30)),
        (D(2026, 11, 15), 2, D(2027, 1, 15)),  # year rollover
        (D(2026, 5, 10), 0, D(2026, 5, 10)),
    ],
)
def test_add_months(anchor, months, expected):
    assert add_months(anchor, months) == expected


def test_period_index_clamped_month():
    # live 31 Jan; on 28 Feb the current period is 28 Feb (k=1).
    assert current_period_index(D(2026, 1, 31), D(2026, 2, 28)) == 1
    assert current_period_index(D(2026, 1, 31), D(2026, 2, 27)) == 0


def test_upcoming_future_live_date():
    info = compute_billing(D(2026, 10, 1), D(2026, 9, 27), [])
    assert info.status == "upcoming" and info.due_date == D(2026, 10, 1)


def test_upcoming_no_live_date():
    assert compute_billing(None, D(2026, 9, 27), []).status == "upcoming"


def test_first_month_due_on_live_date():
    info = compute_billing(D(2026, 9, 27), D(2026, 9, 27), [])
    assert info.status == "due" and info.due_date == D(2026, 9, 27)


def test_first_month_due_within_grace():
    info = compute_billing(D(2026, 9, 24), D(2026, 9, 27), [])  # 3 days after
    assert info.status == "due" and info.due_date == D(2026, 9, 24)


def test_overdue_after_grace():
    info = compute_billing(D(2026, 9, 23), D(2026, 9, 27), [])  # 4 days after
    assert info.status == "overdue" and info.due_date == D(2026, 9, 23)


def test_first_month_paid_next_far():
    info = compute_billing(D(2026, 9, 20), D(2026, 9, 27), [D(2026, 9, 1)])
    assert info.status == "paid" and info.due_date == D(2026, 10, 20)


def test_paid_but_next_due_within_5_days():
    info = compute_billing(D(2026, 8, 30), D(2026, 9, 25), [D(2026, 8, 1)])
    # P = 30 Aug (paid); N = 30 Sep is 5 days away.
    assert info.status == "due" and info.due_date == D(2026, 9, 30)


def test_paid_next_due_6_days_is_paid():
    info = compute_billing(D(2026, 8, 30), D(2026, 9, 24), [D(2026, 8, 1)])
    assert info.status == "paid" and info.due_date == D(2026, 9, 30)


def test_previous_month_paid_current_unpaid_overdue():
    info = compute_billing(D(2026, 6, 10), D(2026, 9, 20), [D(2026, 6, 1), D(2026, 7, 1), D(2026, 8, 1)])
    assert info.status == "overdue" and info.due_date == D(2026, 9, 10)


def test_month_end_clamp_feb_due():
    # live 31 Jan 2026, today 1 Mar: P = 28 Feb unpaid, 1 day late -> due.
    info = compute_billing(D(2026, 1, 31), D(2026, 3, 1), [D(2026, 1, 1)])
    assert info.status == "due" and info.due_date == D(2026, 2, 28)


def test_leap_year_feb_29():
    info = compute_billing(D(2028, 1, 31), D(2028, 2, 29), [D(2028, 1, 1)])
    assert info.status == "due" and info.due_date == D(2028, 2, 29)


def test_leap_year_paid_next_is_march_31():
    info = compute_billing(D(2028, 1, 31), D(2028, 3, 2), [D(2028, 1, 1), D(2028, 2, 1)])
    assert info.status == "paid" and info.due_date == D(2028, 3, 31)


def test_payment_month_normalised():
    # A payment recorded with for_month on a non-first day still counts for that month.
    info = compute_billing(D(2026, 9, 5), D(2026, 9, 10), [D(2026, 9, 15)])
    assert info.status == "paid"


def test_setup_paid_passthrough():
    info = compute_billing(D(2026, 9, 5), D(2026, 9, 10), [], setup_paid=True)
    assert info.setup_paid is True and info.status == "overdue"


def test_year_rollover_period():
    info = compute_billing(D(2025, 12, 31), D(2026, 1, 2), [])
    assert info.status == "due" and info.due_date == D(2025, 12, 31)


def test_wrong_month_payment_does_not_count():
    info = compute_billing(D(2026, 7, 1), D(2026, 9, 10), [D(2026, 8, 1)])
    assert info.status == "overdue" and info.due_date == D(2026, 9, 1)


async def test_renewals_endpoint(api, auth):
    base = "/api/v1"
    r = await api.post(
        f"{base}/clients",
        json={"name": "Live Co", "status": "live", "live_date": "2020-01-15", "package": "starter"},
        headers=auth,
    )
    cid = r.json()["id"]
    await api.post(
        f"{base}/clients", json={"name": "Trial Co", "status": "trial", "package": "starter"}, headers=auth
    )
    await api.post(
        f"{base}/payments",
        json={"client_id": cid, "type": "setup", "amount": "3999", "method": "UPI"},
        headers=auth,
    )
    r = await api.get(f"{base}/billing/renewals", headers=auth)
    assert r.status_code == 200
    rows = r.json()
    assert len(rows) == 1
    assert rows[0]["client_id"] == cid and rows[0]["setup_paid"] is True
    assert rows[0]["amount"] == "1999.00"
    assert rows[0]["status"] in {"due", "overdue"}

    r = await api.get(f"{base}/clients/{cid}", headers=auth)
    assert r.json()["billing_status"] == rows[0]["status"]
    assert r.json()["next_due_date"] == rows[0]["due_date"]
