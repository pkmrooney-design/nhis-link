from app import config, netinfo, services


def test_board_state_orders_and_masks():
    a, _ = services.issue_ticket("홍길동", "1111")
    b, _ = services.issue_ticket("김철수", "2222")
    services.issue_ticket("남궁민수", "3333")
    services.admin_action(a.id, "call")
    services.admin_action(b.id, "call")
    state = services.get_board_state()
    assert [c["no"] for c in state["called"]] == [2, 1]  # 최근 호출이 먼저
    assert state["waiting"] == [{"no": 3, "name": "남○○수"}]
    assert state["waiting_count"] == 1
    assert "1111" not in str(state) and "홍길동" not in str(state)


def test_board_page_and_api(client):
    client.post("/api/tickets", json={"name": "홍길동", "phone": "1234"})
    assert client.get("/board").status_code == 200
    body = client.get("/api/board").json()
    assert body["waiting"][0]["name"] == "홍○동"
    assert "1234" not in str(body)


def test_qr_png(client):
    r = client.get("/qr.png")
    assert r.status_code == 200 and r.content[:8] == b"\x89PNG\r\n\x1a\n"


def test_public_url(monkeypatch):
    monkeypatch.setattr(config, "PUBLIC_URL", "")
    monkeypatch.setattr(netinfo, "lan_ip", lambda: "192.168.0.10")
    assert netinfo.public_base_url("http://localhost:8000/", "localhost", 8000) == "http://192.168.0.10:8000/"
    assert netinfo.public_base_url("http://192.168.0.5:8000/", "192.168.0.5", 8000) == "http://192.168.0.5:8000/"
    monkeypatch.setattr(config, "PUBLIC_URL", "https://queue.example.com")
    assert netinfo.public_base_url("http://localhost:8000/", "localhost", 8000) == "https://queue.example.com/"
