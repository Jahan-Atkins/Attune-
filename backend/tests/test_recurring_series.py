from datetime import date, timedelta

from .conftest import add_availability, signup_instructor_with_specialty

CARD = {"card_name": "Jordan Lee", "card_number": "4242 4242 4242 4242", "card_expiry": "12/28", "card_cvc": "123"}
TUESDAY = 1


def _matched_lesson_request(client, customer_auth_headers, instructor_headers, day=TUESDAY, start="09:00", end="11:00", duration=30):
    add_availability(client, instructor_headers, day, start, end)
    lr = client.post("/api/customer/lesson-requests", json={
        "specialty": "yoga", "city": "New York, NY", "duration_minutes": duration,
        "requested_day": day, "requested_start_time": start, "requested_end_time": end,
        **CARD,
    }, headers=customer_auth_headers).json()
    confirmed = client.put(f"/api/client-requests/lesson-requests/{lr['id']}/confirm", headers=instructor_headers)
    assert confirmed.status_code == 200, confirmed.text
    return lr["id"]


def _next_occurrence_dates(day_of_week, count=4):
    today = date.today()
    days_until_next = (day_of_week - today.weekday()) % 7
    first = today + timedelta(days=days_until_next)
    return [(first + timedelta(weeks=i)).isoformat() for i in range(count)]


def test_create_requires_customer_auth(client):
    res = client.post("/api/customer/recurring-series", json={"lesson_request_id": 1})
    assert res.status_code == 401


def test_create_rejects_unmatched_lesson_request(client, customer_auth_headers):
    lr = client.post("/api/customer/lesson-requests", json={
        "specialty": "yoga", "city": "New York, NY", "duration_minutes": 30,
        "requested_day": TUESDAY, "requested_start_time": "09:00", "requested_end_time": "11:00", **CARD,
    }, headers=customer_auth_headers).json()

    res = client.post("/api/customer/recurring-series", json={"lesson_request_id": lr["id"]}, headers=customer_auth_headers)
    assert res.status_code == 400


def test_create_rejects_someone_elses_lesson_request(client, customer_auth_headers):
    instructor_token = signup_instructor_with_specialty(client, email="rs_other@example.com", specialty="yoga")
    instructor_headers = {"Authorization": f"Bearer {instructor_token}"}
    lr_id = _matched_lesson_request(client, customer_auth_headers, instructor_headers)

    other_token = client.post("/api/customer/auth/signup", json={
        "name": "Other", "email": "rs_intruder@example.com", "phone": "555-010-9999", "password": "custpass123",
    }).json()["access_token"]
    other_headers = {"Authorization": f"Bearer {other_token}"}

    res = client.post("/api/customer/recurring-series", json={"lesson_request_id": lr_id}, headers=other_headers)
    assert res.status_code == 404


def test_create_series_copies_fields_and_generates_occurrences(client, customer_auth_headers):
    instructor_token = signup_instructor_with_specialty(client, email="rs_create@example.com", specialty="yoga")
    instructor_headers = {"Authorization": f"Bearer {instructor_token}"}
    lr_id = _matched_lesson_request(client, customer_auth_headers, instructor_headers, duration=45)

    res = client.post("/api/customer/recurring-series", json={"lesson_request_id": lr_id}, headers=customer_auth_headers)
    assert res.status_code == 201
    body = res.json()
    assert body["specialty"] == "yoga"
    assert body["duration_minutes"] == 45
    assert body["day_of_week"] == TUESDAY
    assert body["status"] == "active"
    assert body["customer_name"] == "Test Customer"
    assert body["instructor"]["name"] == "Test Instructor"

    history = client.get("/api/customer/lesson-requests", headers=customer_auth_headers).json()
    occurrence_dates = sorted(lr["occurrence_date"] for lr in history if lr["occurrence_date"])
    assert occurrence_dates == sorted(_next_occurrence_dates(TUESDAY))
    generated = [lr for lr in history if lr["occurrence_date"]]
    assert all(lr["status"] == "matched" and lr["paid"] is True for lr in generated)


def test_create_rejects_duplicate_active_series_for_same_slot(client, customer_auth_headers):
    instructor_token = signup_instructor_with_specialty(client, email="rs_dup@example.com", specialty="yoga")
    instructor_headers = {"Authorization": f"Bearer {instructor_token}"}
    add_availability(client, instructor_headers, TUESDAY, "09:00", "11:00")

    def _confirm_new_lesson_request():
        lr = client.post("/api/customer/lesson-requests", json={
            "specialty": "yoga", "city": "New York, NY", "duration_minutes": 30,
            "requested_day": TUESDAY, "requested_start_time": "09:00", "requested_end_time": "11:00", **CARD,
        }, headers=customer_auth_headers).json()
        client.put(f"/api/client-requests/lesson-requests/{lr['id']}/confirm", headers=instructor_headers)
        return lr["id"]

    first_id = _confirm_new_lesson_request()
    client.post("/api/customer/recurring-series", json={"lesson_request_id": first_id}, headers=customer_auth_headers)

    second_id = _confirm_new_lesson_request()
    res = client.post("/api/customer/recurring-series", json={"lesson_request_id": second_id}, headers=customer_auth_headers)
    assert res.status_code == 400


def test_list_isolated_between_customers(client, customer_auth_headers):
    instructor_token = signup_instructor_with_specialty(client, email="rs_isolation@example.com", specialty="yoga")
    instructor_headers = {"Authorization": f"Bearer {instructor_token}"}
    lr_id = _matched_lesson_request(client, customer_auth_headers, instructor_headers)
    client.post("/api/customer/recurring-series", json={"lesson_request_id": lr_id}, headers=customer_auth_headers)

    other_token = client.post("/api/customer/auth/signup", json={
        "name": "Other", "email": "rs_list_other@example.com", "phone": "555-010-8888", "password": "custpass123",
    }).json()["access_token"]
    other_headers = {"Authorization": f"Bearer {other_token}"}

    assert len(client.get("/api/customer/recurring-series", headers=customer_auth_headers).json()) == 1
    assert len(client.get("/api/customer/recurring-series", headers=other_headers).json()) == 0


def test_pause_stops_new_occurrences(client, customer_auth_headers):
    instructor_token = signup_instructor_with_specialty(client, email="rs_pause@example.com", specialty="yoga")
    instructor_headers = {"Authorization": f"Bearer {instructor_token}"}
    lr_id = _matched_lesson_request(client, customer_auth_headers, instructor_headers)
    series = client.post("/api/customer/recurring-series", json={"lesson_request_id": lr_id}, headers=customer_auth_headers).json()
    before = len(client.get("/api/customer/lesson-requests", headers=customer_auth_headers).json())

    paused = client.put(f"/api/customer/recurring-series/{series['id']}/pause", headers=customer_auth_headers)
    assert paused.status_code == 200
    assert paused.json()["status"] == "paused"

    after = len(client.get("/api/customer/lesson-requests", headers=customer_auth_headers).json())
    assert after == before  # a paused series generates nothing new


def test_cannot_pause_already_paused_series(client, customer_auth_headers):
    instructor_token = signup_instructor_with_specialty(client, email="rs_double_pause@example.com", specialty="yoga")
    instructor_headers = {"Authorization": f"Bearer {instructor_token}"}
    lr_id = _matched_lesson_request(client, customer_auth_headers, instructor_headers)
    series = client.post("/api/customer/recurring-series", json={"lesson_request_id": lr_id}, headers=customer_auth_headers).json()
    client.put(f"/api/customer/recurring-series/{series['id']}/pause", headers=customer_auth_headers)

    res = client.put(f"/api/customer/recurring-series/{series['id']}/pause", headers=customer_auth_headers)
    assert res.status_code == 400


def test_resume_reactivates_and_generates_again(client, customer_auth_headers):
    instructor_token = signup_instructor_with_specialty(client, email="rs_resume@example.com", specialty="yoga")
    instructor_headers = {"Authorization": f"Bearer {instructor_token}"}
    lr_id = _matched_lesson_request(client, customer_auth_headers, instructor_headers)
    series = client.post("/api/customer/recurring-series", json={"lesson_request_id": lr_id}, headers=customer_auth_headers).json()
    client.put(f"/api/customer/recurring-series/{series['id']}/pause", headers=customer_auth_headers)

    resumed = client.put(f"/api/customer/recurring-series/{series['id']}/resume", headers=customer_auth_headers)
    assert resumed.status_code == 200
    assert resumed.json()["status"] == "active"

    res = client.put(f"/api/customer/recurring-series/{series['id']}/resume", headers=customer_auth_headers)
    assert res.status_code == 400  # already active, can't resume again


def test_customer_cancel_is_a_soft_cancel(client, customer_auth_headers):
    instructor_token = signup_instructor_with_specialty(client, email="rs_cancel@example.com", specialty="yoga")
    instructor_headers = {"Authorization": f"Bearer {instructor_token}"}
    lr_id = _matched_lesson_request(client, customer_auth_headers, instructor_headers)
    series = client.post("/api/customer/recurring-series", json={"lesson_request_id": lr_id}, headers=customer_auth_headers).json()

    res = client.delete(f"/api/customer/recurring-series/{series['id']}", headers=customer_auth_headers)
    assert res.status_code == 200
    assert res.json()["status"] == "cancelled"
    # Still listed, not actually gone.
    listed = client.get("/api/customer/recurring-series", headers=customer_auth_headers).json()
    assert any(s["id"] == series["id"] and s["status"] == "cancelled" for s in listed)


def test_instructor_sees_own_hosted_series(client, customer_auth_headers):
    instructor_token = signup_instructor_with_specialty(client, email="rs_hosted@example.com", specialty="yoga")
    instructor_headers = {"Authorization": f"Bearer {instructor_token}"}
    lr_id = _matched_lesson_request(client, customer_auth_headers, instructor_headers)
    client.post("/api/customer/recurring-series", json={"lesson_request_id": lr_id}, headers=customer_auth_headers)

    res = client.get("/api/recurring-series", headers=instructor_headers)
    assert res.status_code == 200
    body = res.json()
    assert len(body) == 1
    assert body[0]["customer_name"] == "Test Customer"


def test_instructor_hosted_list_excludes_other_instructors(client, customer_auth_headers):
    instructor_token = signup_instructor_with_specialty(client, email="rs_hosted_mine@example.com", specialty="yoga")
    instructor_headers = {"Authorization": f"Bearer {instructor_token}"}
    lr_id = _matched_lesson_request(client, customer_auth_headers, instructor_headers)
    client.post("/api/customer/recurring-series", json={"lesson_request_id": lr_id}, headers=customer_auth_headers)

    other_token = signup_instructor_with_specialty(client, email="rs_hosted_bystander@example.com", specialty="yoga")
    other_headers = {"Authorization": f"Bearer {other_token}"}
    assert client.get("/api/recurring-series", headers=other_headers).json() == []


def test_instructor_cancel_stops_hosting(client, customer_auth_headers):
    instructor_token = signup_instructor_with_specialty(client, email="rs_instr_cancel@example.com", specialty="yoga")
    instructor_headers = {"Authorization": f"Bearer {instructor_token}"}
    lr_id = _matched_lesson_request(client, customer_auth_headers, instructor_headers)
    series = client.post("/api/customer/recurring-series", json={"lesson_request_id": lr_id}, headers=customer_auth_headers).json()

    res = client.put(f"/api/recurring-series/{series['id']}/cancel", headers=instructor_headers)
    assert res.status_code == 200
    assert res.json()["status"] == "cancelled"
    # A cancelled series drops out of the instructor's own hosted list.
    assert client.get("/api/recurring-series", headers=instructor_headers).json() == []


def test_instructor_cannot_cancel_another_instructors_series(client, customer_auth_headers):
    instructor_token = signup_instructor_with_specialty(client, email="rs_wrong_instr@example.com", specialty="yoga")
    instructor_headers = {"Authorization": f"Bearer {instructor_token}"}
    lr_id = _matched_lesson_request(client, customer_auth_headers, instructor_headers)
    series = client.post("/api/customer/recurring-series", json={"lesson_request_id": lr_id}, headers=customer_auth_headers).json()

    other_token = signup_instructor_with_specialty(client, email="rs_wrong_instr_2@example.com", specialty="yoga")
    other_headers = {"Authorization": f"Bearer {other_token}"}
    res = client.put(f"/api/recurring-series/{series['id']}/cancel", headers=other_headers)
    assert res.status_code == 404


def test_generated_occurrences_never_appear_in_pending_client_requests(client, customer_auth_headers):
    """Occurrences are created directly as "matched" — they must never
    show up in the broadcast/pending queue, for this instructor or any
    other one."""
    instructor_token = signup_instructor_with_specialty(client, email="rs_no_broadcast@example.com", specialty="yoga")
    instructor_headers = {"Authorization": f"Bearer {instructor_token}"}
    lr_id = _matched_lesson_request(client, customer_auth_headers, instructor_headers)
    client.post("/api/customer/recurring-series", json={"lesson_request_id": lr_id}, headers=customer_auth_headers)

    assert client.get("/api/client-requests", headers=instructor_headers).json() == []
