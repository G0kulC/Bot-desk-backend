from __future__ import annotations

API = "/api/v1"


async def _create_client(api, auth, **overrides):
    body = {
        "name": "Smile Care Dental",
        "niche": "dental_clinic",
        "city": "Chennai",
        "owner_name": "Dr. Priya",
        "owner_phone": "98400 12345",
        "status": "trial",
        "package": "business",
        "languages": ["English", "Tamil"],
        **overrides,
    }
    r = await api.post(f"{API}/clients", json=body, headers=auth)
    assert r.status_code == 201, r.text
    return r.json()


async def test_auth_required(api, session):
    r = await api.get(f"{API}/clients")
    assert r.status_code == 401
    assert r.json()["error"]["code"] == "unauthorized"


async def test_login_wrong_password(api, admin):
    r = await api.post(f"{API}/auth/login", json={"email": "admin@test.in", "password": "nope"})
    assert r.status_code == 401
    assert r.json()["error"]["code"] == "invalid_credentials"


async def test_me(api, auth):
    r = await api.get(f"{API}/auth/me", headers=auth)
    assert r.status_code == 200
    assert r.json()["email"] == "admin@test.in"


async def test_clients_crud(api, auth):
    c = await _create_client(api, auth)
    # Package defaults fill fees; phone normalised to E.164.
    assert c["setup_fee"] == "7999.00"
    assert c["monthly_fee"] == "3999.00"
    assert c["owner_phone"] == "+919840012345"
    assert c["effective_provider"] == "own"

    # Custom fees win over package defaults.
    c2 = await _create_client(api, auth, name="Glow Studio", package="starter", monthly_fee="1500")
    assert c2["monthly_fee"] == "1500.00"
    assert c2["setup_fee"] == "3999.00"

    r = await api.get(f"{API}/clients", headers=auth, params={"q": "smile"})
    assert r.status_code == 200
    page = r.json()
    assert page["total"] == 1 and page["items"][0]["id"] == c["id"]

    r = await api.patch(
        f"{API}/clients/{c['id']}", json={"package": "growth", "provider_override": "aisensy"}, headers=auth
    )
    assert r.status_code == 200, r.text
    upd = r.json()
    assert upd["monthly_fee"] == "6999.00" and upd["setup_fee"] == "12999.00"
    assert upd["effective_provider"] == "aisensy"

    r = await api.delete(f"{API}/clients/{c['id']}", headers=auth)
    assert r.status_code == 200
    r = await api.get(f"{API}/clients/{c['id']}", headers=auth)
    assert r.status_code == 404
    assert r.json()["error"]["code"] == "not_found"
    r = await api.get(f"{API}/clients", headers=auth)
    assert r.json()["total"] == 1


async def test_client_validation_error_shape(api, auth):
    r = await api.post(f"{API}/clients", json={"name": "", "owner_phone": "12"}, headers=auth)
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "validation_error"


async def test_knowledge_save_approve_version_reset(api, auth):
    c = await _create_client(api, auth)
    url = f"{API}/clients/{c['id']}/knowledge"

    r = await api.get(url, headers=auth)
    assert r.status_code == 404

    r = await api.put(url, json={"address": "Anna Nagar", "services": "Cleaning: ₹1,200"}, headers=auth)
    assert r.status_code == 200, r.text
    kb = r.json()
    assert kb["version"] == 1 and kb["approved"] is False

    r = await api.post(f"{url}/approve", json={"approved_by_name": "Dr. Priya"}, headers=auth)
    assert r.status_code == 200
    assert r.json()["approved"] is True and r.json()["approved_by_name"] == "Dr. Priya"

    # Changing timings keeps approval.
    r = await api.put(url, json={"timings": "10am-8pm"}, headers=auth)
    assert r.json()["version"] == 2 and r.json()["approved"] is True

    # Changing services resets approval.
    r = await api.put(url, json={"services": "Cleaning: ₹1,500"}, headers=auth)
    assert r.json()["version"] == 3 and r.json()["approved"] is False

    r = await api.get(f"{url}/versions", headers=auth)
    versions = r.json()
    assert [v["version"] for v in versions] == [3, 2, 1]
    assert versions[-1]["content"]["services"] == "Cleaning: ₹1,200"

    r = await api.post(f"{url}/restore/1", headers=auth)
    assert r.status_code == 200
    restored = r.json()
    assert restored["version"] == 4
    assert restored["services"] == "Cleaning: ₹1,200"
    assert restored["timings"] == ""

    r = await api.post(f"{url}/restore/99", headers=auth)
    assert r.status_code == 404


async def test_knowledge_template(api, auth):
    r = await api.get(f"{API}/knowledge/templates/dental_clinic", headers=auth)
    assert r.status_code == 200
    body = r.json()
    assert "Sample" in body["label"]
    assert "₹" in body["knowledge"]["services"]
    r = await api.get(f"{API}/knowledge/templates/restaurant", headers=auth)
    assert r.status_code == 200


async def test_payments(api, auth):
    c = await _create_client(api, auth, status="live", live_date="2026-01-15")
    r = await api.post(
        f"{API}/payments",
        json={
            "client_id": c["id"],
            "type": "monthly",
            "amount": "3999",
            "for_month": "2026-02-15",
            "method": "UPI",
        },
        headers=auth,
    )
    assert r.status_code == 201, r.text
    pay = r.json()
    assert pay["for_month"] == "2026-02-01"
    assert pay["paid_on"]  # defaulted to today

    r = await api.post(
        f"{API}/payments",
        json={"client_id": c["id"], "type": "monthly", "amount": "3999", "method": "cash"},
        headers=auth,
    )
    assert r.status_code == 422

    r = await api.post(
        f"{API}/payments",
        json={
            "client_id": c["id"],
            "type": "setup",
            "amount": "7999",
            "paid_on": "2026-01-10",
            "method": "bank",
        },
        headers=auth,
    )
    assert r.status_code == 201
    assert r.json()["for_month"] is None

    r = await api.get(f"{API}/payments", params={"client_id": c["id"]}, headers=auth)
    assert len(r.json()) == 2
    r = await api.get(f"{API}/payments", params={"month": "2026-02"}, headers=auth)
    assert len(r.json()) == 1
    r = await api.get(f"{API}/payments", params={"type": "setup"}, headers=auth)
    assert len(r.json()) == 1

    r = await api.delete(f"{API}/payments/{pay['id']}", headers=auth)
    assert r.status_code == 200
    r = await api.get(f"{API}/payments", params={"client_id": c["id"]}, headers=auth)
    assert len(r.json()) == 1


async def test_config(api, auth):
    r = await api.get(f"{API}/config", headers=auth)
    assert r.status_code == 200
    body = r.json()
    assert body["default_provider"] == "own"
    assert body["packages"]["starter"]["monthly"] == "1999.00"
    assert "dental_clinic" in body["niches"]


async def test_health(api):
    r = await api.get("/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok", "db": True, "default_provider": "own"}
