import pytest
from models import db, User, Order


def test_auth_login_and_role_boundaries(client):
    """
    Test A: Emergency Ward user can log in and access Emergency Ward dashboard
    but cannot access admin pages or another room's dashboard.
    """
    # 1. Unauthenticated access to ward redirects to login
    res = client.get("/ward/emergency")
    assert res.status_code == 302
    assert "/login" in res.headers["Location"]

    # 2. Login as emergency ward user
    login_res = client.post("/login", data={
        "username": "emergency",
        "password": "emergency123"
    }, follow_redirects=True)
    assert login_res.status_code == 200
    assert b"Emergency Ward" in login_res.data

    # 3. Can access Emergency Ward dashboard
    ward_res = client.get("/ward/emergency")
    assert ward_res.status_code == 200
    assert b"Emergency Ward" in ward_res.data

    # 4. Cannot access Admin Panel (Forbidden or redirected)
    admin_res = client.get("/admin", follow_redirects=False)
    # Role check redirects back or returns 302/403
    assert admin_res.status_code in [302, 403]

    # 5. Cannot access Medicine Manager Station
    mgr_res = client.get("/manager", follow_redirects=False)
    assert mgr_res.status_code in [302, 403]

    # 6. Cannot access another ward's dashboard (/ward/general_1)
    other_ward_res = client.get("/ward/general_1", follow_redirects=False)
    assert other_ward_res.status_code in [302, 403]


def test_inactive_user_cannot_login(client):
    """
    Deactivated user cannot log in.
    """
    user = User.query.filter_by(username="ward1").first()
    user.active = False
    db.session.commit()

    res = client.post("/login", data={
        "username": "ward1",
        "password": "ward123"
    }, follow_redirects=True)

    assert b"This account has been deactivated" in res.data
