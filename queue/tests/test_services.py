import threading
from datetime import timedelta

import pytest

from app import db, services
from app.models import QueueEntry


@pytest.mark.parametrize(
    "name, masked",
    [("김철", "김○"), ("김철수", "김○수"), ("남궁민수", "남○○수")],
)
def test_mask_name(name, masked):
    assert services.mask_name(name) == masked


@pytest.mark.parametrize("name", ["김", "김철수영희", "김 수", "Kim", "김1", "김!", "ㄱㄴ", ""])
def test_invalid_name(name):
    with pytest.raises(services.ValidationError) as e:
        services.validate_entry(name, "1234")
    assert e.value.field == "name"


@pytest.mark.parametrize("phone", ["123", "12345", "12a4", "", "１２３４", "12 4"])
def test_invalid_phone(phone):
    with pytest.raises(services.ValidationError) as e:
        services.validate_entry("홍길동", phone)
    assert e.value.field == "phone"


def test_nfd_name_is_accepted():
    import unicodedata

    name, _ = services.validate_entry(unicodedata.normalize("NFD", "홍길동"), "1234")
    assert name == "홍길동"


def test_sequential_and_duplicate():
    a, created_a = services.issue_ticket("홍길동", "1111")
    b, created_b = services.issue_ticket("김철수", "2222")
    again, created_again = services.issue_ticket("홍길동", "1111")
    assert (a.ticket_no, b.ticket_no) == (1, 2)
    assert created_a and created_b and not created_again
    assert again.token == a.token


def test_can_register_again_after_done():
    a, _ = services.issue_ticket("홍길동", "1111")
    services.admin_action(a.id, "done")
    b, created = services.issue_ticket("홍길동", "1111")
    assert created and b.ticket_no == 2


def test_numbers_reset_per_day():
    a, _ = services.issue_ticket("홍길동", "1111")
    with db.SessionLocal() as s, s.begin():
        s.get(QueueEntry, a.id).date = services.today() - timedelta(days=1)
    b, _ = services.issue_ticket("김철수", "2222")
    assert b.ticket_no == 1


def test_concurrent_issue_has_no_duplicate_numbers():
    names = ["가나", "다라", "마바", "사아", "자차", "카타", "파하", "가다", "나라", "마사",
             "바아", "자카", "차타", "파가", "하나", "고노", "도로", "모보", "소오", "조초"]
    results, errors = [], []

    def worker(n):
        try:
            results.append(services.issue_ticket(n, "0000")[0].ticket_no)
        except Exception as e:  # pragma: no cover
            errors.append(e)

    threads = [threading.Thread(target=worker, args=(n,)) for n in names]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert not errors
    assert sorted(results) == list(range(1, len(names) + 1))


def test_closed_blocks_issue():
    services.set_open(False)
    with pytest.raises(services.ClosedError):
        services.issue_ticket("홍길동", "1111")
    services.set_open(True)
    assert services.issue_ticket("홍길동", "1111")[1]


def test_ticket_view_ahead_and_masking():
    services.issue_ticket("홍길동", "1111")
    services.issue_ticket("남궁민수", "2222")
    c, _ = services.issue_ticket("김철", "3333")
    view = services.get_ticket_view(c.token)
    assert view["ahead"] == 2
    assert [q["name"] for q in view["queue"]] == ["홍○동", "남○○수", "김○"]
    assert "1111" not in str(view)


def test_admin_transitions_and_stats():
    a, _ = services.issue_ticket("홍길동", "1111")
    b, _ = services.issue_ticket("김철수", "2222")
    c, _ = services.issue_ticket("이영희", "3333")
    assert services.admin_action(a.id, "call")
    assert not services.admin_action(a.id, "call")  # 이미 호출됨
    assert services.admin_action(a.id, "done")
    assert services.admin_action(b.id, "call")
    assert services.admin_action(b.id, "no_show")
    assert services.cancel_ticket(c.token)
    assert not services.cancel_ticket(c.token)
    stats = services.get_admin_state()["stats"]
    assert stats == {**stats, "total": 3, "done": 1, "no_show": 1, "cancelled": 1, "waiting": 0}
    assert stats["avg_wait_min"] is not None

    assert services.admin_action(b.id, "restore")
    assert services.get_ticket_view(b.token)["status"] == "called"


def test_purge_personal_data():
    old, _ = services.issue_ticket("홍길동", "1111")
    new, _ = services.issue_ticket("김철수", "2222")
    with db.SessionLocal() as s, s.begin():
        s.get(QueueEntry, old.id).date = services.today() - timedelta(days=31)
    assert services.purge_personal_data(30) == 1
    with db.SessionLocal() as s:
        o, n = s.get(QueueEntry, old.id), s.get(QueueEntry, new.id)
        assert (o.name, o.phone_last4) == (None, None)
        assert o.status == "waiting" and o.ticket_no == 1  # 통계용 값은 유지
        assert n.name == "김철수"
    assert services.purge_personal_data(30) == 0
