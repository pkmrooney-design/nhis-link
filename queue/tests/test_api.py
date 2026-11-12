def test_issue_and_ticket_flow(client):
    r = client.post("/api/tickets", json={"name": "홍길동", "phone": "1234"})
    assert r.status_code == 201
    token = r.json()["token"]
    assert client.cookies.get("qtoken") == token

    # 쿠키가 있으면 첫 화면이 내 번호 화면으로 이동
    r = client.get("/", follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == f"/t/{token}"

    assert client.get(f"/t/{token}").status_code == 200
    view = client.get(f"/api/ticket/{token}").json()
    assert view["ticket_no"] == 1 and view["status"] == "waiting" and view["name"] == "홍○동"

    r = client.post("/api/tickets", json={"name": "홍길동", "phone": "1234"})
    assert r.status_code == 200 and r.json()["existing"] and r.json()["token"] == token

    assert client.post(f"/api/ticket/{token}/cancel").status_code == 200
    assert client.get("/", follow_redirects=False).status_code == 200


def test_server_side_validation(client):
    r = client.post("/api/tickets", json={"name": "Kim", "phone": "1234"})
    assert r.status_code == 422 and r.json()["field"] == "name"
    r = client.post("/api/tickets", json={"name": "홍길동", "phone": "12"})
    assert r.status_code == 422 and r.json()["field"] == "phone"
    r = client.post("/api/tickets", json={"name": ["홍길동"], "phone": 1234})
    assert r.status_code == 422


def test_unknown_token(client):
    assert client.get("/t/nope").status_code == 404
    assert client.get("/api/ticket/nope").status_code == 404


def test_public_api_hides_phone(client):
    client.post("/api/tickets", json={"name": "홍길동", "phone": "9876"})
    body = client.get("/api/queue").text
    assert "9876" not in body and "홍길동" not in body


def test_admin_requires_login(client):
    assert "관리자 로그인" in client.get("/admin").text
    assert client.get("/admin/api/state").status_code == 401
    assert client.post("/admin/login", json={"password": "wrong"}).status_code == 401


def test_admin_requires_csrf(admin):
    token = admin.headers.pop("X-CSRF-Token")
    assert admin.post("/admin/api/open", json={"open": False}).status_code == 403
    admin.headers["X-CSRF-Token"] = token
    assert admin.post("/admin/api/open", json={"open": False}).status_code == 200


def test_admin_flow(admin):
    r = admin.post("/api/tickets", json={"name": "홍길동", "phone": "1234"})
    token = r.json()["token"]
    state = admin.get("/admin/api/state").json()
    entry = state["active"][0]
    assert (entry["name"], entry["phone"]) == ("홍길동", "1234")

    assert admin.post(f"/admin/api/entries/{entry['id']}/call").status_code == 200
    assert admin.get(f"/api/ticket/{token}").json()["status"] == "called"
    assert admin.post(f"/admin/api/entries/{entry['id']}/call").status_code == 409
    assert admin.post(f"/admin/api/entries/{entry['id']}/bogus").status_code == 409
    assert admin.post(f"/admin/api/entries/{entry['id']}/done").status_code == 200
    state = admin.get("/admin/api/state").json()
    assert state["active"] == [] and state["stats"]["done"] == 1


def test_closed_rejects_registration(admin):
    admin.post("/admin/api/open", json={"open": False})
    r = admin.post("/api/tickets", json={"name": "홍길동", "phone": "1234"})
    assert r.status_code == 409
    assert "접수가 마감" in admin.get("/").text
