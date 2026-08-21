from .conftest import signup_instructor_with_specialty

CARD = {"card_name": "Jordan Lee", "card_number": "4242 4242 4242 4242", "card_expiry": "12/28", "card_cvc": "123"}
CITY = "New York, NY"


def _booking_payload(**overrides):
    payload = {"specialty": "yoga", "package": "single", "city": CITY, **CARD}
    payload.update(overrides)
    return payload


def _make_matched_booking(client, customer_auth_headers, email="reviewed_instructor@example.com", name="Reviewed Instructor"):
    """Signs up an instructor, submits a booking, and confirms it —
    returns (instructor_headers, booking_id)."""
    token = signup_instructor_with_specialty(client, email=email, specialty="yoga", name=name)
    headers = {"Authorization": f"Bearer {token}"}
    res = client.post("/api/customer/bookings", json=_booking_payload(), headers=customer_auth_headers)
    booking_id = res.json()["id"]
    client.put(f"/api/client-requests/bookings/{booking_id}/confirm", headers=headers)
    return headers, booking_id


def test_create_review_requires_customer_auth(client):
    res = client.post("/api/customer/reviews", json={"booking_id": 1, "rating": 5})
    assert res.status_code == 401


def test_cannot_review_a_pending_booking(client, customer_auth_headers):
    signup_instructor_with_specialty(client, email="pending_review@example.com", specialty="yoga")
    res = client.post("/api/customer/bookings", json=_booking_payload(), headers=customer_auth_headers)
    booking_id = res.json()["id"]

    review_res = client.post(
        "/api/customer/reviews", json={"booking_id": booking_id, "rating": 5}, headers=customer_auth_headers,
    )
    assert review_res.status_code == 400


def test_create_review_on_matched_booking(client, customer_auth_headers):
    _, booking_id = _make_matched_booking(client, customer_auth_headers)

    res = client.post(
        "/api/customer/reviews",
        json={"booking_id": booking_id, "rating": 5, "comment": "Loved it!"},
        headers=customer_auth_headers,
    )
    assert res.status_code == 201
    body = res.json()
    assert body["rating"] == 5
    assert body["comment"] == "Loved it!"
    assert body["customer_name"] == "Test Customer"


def test_create_review_on_matched_lesson_request(client, customer_auth_headers):
    token = signup_instructor_with_specialty(client, email="lesson_review@example.com", specialty="yoga")
    headers = {"Authorization": f"Bearer {token}"}
    client.post("/api/availability", json={"day_of_week": 1, "start_time": "08:00", "end_time": "12:00"}, headers=headers)
    res = client.post("/api/customer/lesson-requests", json={
        "specialty": "yoga", "city": CITY, "duration_minutes": 30,
        "requested_day": 1, "requested_start_time": "09:00", "requested_end_time": "11:00", **CARD,
    }, headers=customer_auth_headers)
    lesson_request_id = res.json()["id"]
    client.put(f"/api/client-requests/lesson-requests/{lesson_request_id}/confirm", headers=headers)

    review_res = client.post(
        "/api/customer/reviews", json={"lesson_request_id": lesson_request_id, "rating": 4}, headers=customer_auth_headers,
    )
    assert review_res.status_code == 201
    assert review_res.json()["rating"] == 4


def test_cannot_review_same_booking_twice(client, customer_auth_headers):
    _, booking_id = _make_matched_booking(client, customer_auth_headers, email="double_review@example.com")
    client.post("/api/customer/reviews", json={"booking_id": booking_id, "rating": 5}, headers=customer_auth_headers)

    second = client.post("/api/customer/reviews", json={"booking_id": booking_id, "rating": 3}, headers=customer_auth_headers)
    assert second.status_code == 400


def test_cannot_review_another_customers_booking(client, customer_auth_headers):
    _, booking_id = _make_matched_booking(client, customer_auth_headers, email="not_yours@example.com")

    other_token = client.post("/api/customer/auth/signup", json={
        "name": "Other Customer", "email": "other_reviewer@example.com", "phone": "555-010-5555", "password": "custpass123",
    }).json()["access_token"]
    other_headers = {"Authorization": f"Bearer {other_token}"}

    res = client.post("/api/customer/reviews", json={"booking_id": booking_id, "rating": 1}, headers=other_headers)
    assert res.status_code == 404


def test_reject_review_without_booking_or_lesson_request_id(client, customer_auth_headers):
    res = client.post("/api/customer/reviews", json={"rating": 5}, headers=customer_auth_headers)
    assert res.status_code == 400


def test_reject_review_with_both_ids(client, customer_auth_headers):
    res = client.post(
        "/api/customer/reviews", json={"booking_id": 1, "lesson_request_id": 1, "rating": 5}, headers=customer_auth_headers,
    )
    assert res.status_code == 400


def test_reject_invalid_rating(client, customer_auth_headers):
    _, booking_id = _make_matched_booking(client, customer_auth_headers, email="bad_rating@example.com")
    res = client.post("/api/customer/reviews", json={"booking_id": booking_id, "rating": 7}, headers=customer_auth_headers)
    assert res.status_code == 400


def test_my_reviews_requires_instructor_auth(client):
    res = client.get("/api/profile/reviews")
    assert res.status_code == 401


def test_my_reviews_lists_only_this_instructors_reviews(client, customer_auth_headers):
    headers, booking_id = _make_matched_booking(client, customer_auth_headers, email="my_reviews@example.com")
    client.post("/api/customer/reviews", json={"booking_id": booking_id, "rating": 5}, headers=customer_auth_headers)

    mine = client.get("/api/profile/reviews", headers=headers).json()
    assert len(mine) == 1
    assert mine[0]["rating"] == 5

    other_token = signup_instructor_with_specialty(client, email="unrelated_instructor@example.com", specialty="yoga")
    other_headers = {"Authorization": f"Bearer {other_token}"}
    assert client.get("/api/profile/reviews", headers=other_headers).json() == []


def test_average_rating_appears_on_matched_instructor(client, customer_auth_headers):
    _, booking_id = _make_matched_booking(client, customer_auth_headers, email="avg_rating@example.com")
    client.post("/api/customer/reviews", json={"booking_id": booking_id, "rating": 4}, headers=customer_auth_headers)

    my_booking = client.get("/api/customer/bookings/me", headers=customer_auth_headers).json()
    assert my_booking["instructor"]["average_rating"] == 4.0
    assert my_booking["instructor"]["review_count"] == 1


def test_no_reviews_yet_means_null_average_not_zero(client, customer_auth_headers):
    signup_instructor_with_specialty(client, email="no_reviews_yet@example.com", specialty="yoga")
    res = client.post("/api/customer/bookings", json=_booking_payload(), headers=customer_auth_headers)
    booking_id = res.json()["id"]
    token = client.post("/api/auth/login", data={"username": "no_reviews_yet@example.com", "password": "testpass123"}).json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    client.put(f"/api/client-requests/bookings/{booking_id}/confirm", headers=headers)

    my_booking = client.get("/api/customer/bookings/me", headers=customer_auth_headers).json()
    assert my_booking["instructor"]["average_rating"] is None
    assert my_booking["instructor"]["review_count"] == 0
