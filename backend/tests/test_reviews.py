from .conftest import create_booking_row, signup_customer, signup_instructor_with_specialty

CARD = {"card_name": "Jordan Lee", "card_number": "4242 4242 4242 4242", "card_expiry": "12/28", "card_cvc": "123"}
CITY = "New York, NY"


def _make_matched_booking(client, customer_auth_headers, email="reviewed_instructor@example.com", name="Reviewed Instructor"):
    """Signs up an instructor, seeds a (legacy, directly-inserted —
    Booking has no create route anymore) booking, and confirms it —
    returns (instructor_headers, booking_id)."""
    token = signup_instructor_with_specialty(client, email=email, specialty="yoga", name=name)
    headers = {"Authorization": f"Bearer {token}"}
    booking_id = create_booking_row(city=CITY)
    client.put(f"/api/client-requests/bookings/{booking_id}/confirm", headers=headers)
    return headers, booking_id


def test_create_review_requires_customer_auth(client):
    res = client.post("/api/customer/reviews", json={"booking_id": 1, "rating": 5})
    assert res.status_code == 401


def test_cannot_review_a_pending_booking(client, customer_auth_headers):
    signup_instructor_with_specialty(client, email="pending_review@example.com", specialty="yoga")
    booking_id = create_booking_row(city=CITY)

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
        "specialty": "yoga", "package": "single", "address": "123 Main St", "city": "New York", "state": "NY", "duration_minutes": 30,
        "availability_windows": [{"day_of_week": 1, "start_time": "09:00", "end_time": "11:00"}], **CARD,
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

    other_token = signup_customer(client, email="other_reviewer@example.com")
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
    assert res.status_code == 422


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
    booking_id = create_booking_row(city=CITY)
    token = client.post("/api/auth/login", data={"username": "no_reviews_yet@example.com", "password": "testpass123"}).json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    client.put(f"/api/client-requests/bookings/{booking_id}/confirm", headers=headers)

    my_booking = client.get("/api/customer/bookings/me", headers=customer_auth_headers).json()
    assert my_booking["instructor"]["average_rating"] is None
    assert my_booking["instructor"]["review_count"] == 0


def _create_review(client, customer_auth_headers, booking_id, rating=5, comment="Loved it!"):
    res = client.post(
        "/api/customer/reviews",
        json={"booking_id": booking_id, "rating": rating, "comment": comment},
        headers=customer_auth_headers,
    )
    assert res.status_code == 201, res.text
    return res.json()["id"]


def test_edit_review_rating_only(client, customer_auth_headers):
    _, booking_id = _make_matched_booking(client, customer_auth_headers, email="edit_rating@example.com")
    review_id = _create_review(client, customer_auth_headers, booking_id, rating=3, comment="Fine.")

    res = client.put(f"/api/customer/reviews/{review_id}", json={"rating": 5}, headers=customer_auth_headers)
    assert res.status_code == 200
    body = res.json()
    assert body["rating"] == 5
    assert body["comment"] == "Fine."


def test_edit_review_comment_only(client, customer_auth_headers):
    _, booking_id = _make_matched_booking(client, customer_auth_headers, email="edit_comment@example.com")
    review_id = _create_review(client, customer_auth_headers, booking_id, rating=3, comment="Fine.")

    res = client.put(f"/api/customer/reviews/{review_id}", json={"comment": "Actually great!"}, headers=customer_auth_headers)
    assert res.status_code == 200
    body = res.json()
    assert body["rating"] == 3
    assert body["comment"] == "Actually great!"


def test_edit_review_rating_and_comment(client, customer_auth_headers):
    _, booking_id = _make_matched_booking(client, customer_auth_headers, email="edit_both@example.com")
    review_id = _create_review(client, customer_auth_headers, booking_id, rating=3, comment="Fine.")

    res = client.put(
        f"/api/customer/reviews/{review_id}", json={"rating": 1, "comment": "Changed my mind."}, headers=customer_auth_headers,
    )
    assert res.status_code == 200
    body = res.json()
    assert body["rating"] == 1
    assert body["comment"] == "Changed my mind."


def test_edit_review_rejects_out_of_range_rating(client, customer_auth_headers):
    _, booking_id = _make_matched_booking(client, customer_auth_headers, email="edit_invalid@example.com")
    review_id = _create_review(client, customer_auth_headers, booking_id)

    res = client.put(f"/api/customer/reviews/{review_id}", json={"rating": 0}, headers=customer_auth_headers)
    assert res.status_code == 422


def test_cannot_edit_another_customers_review(client, customer_auth_headers):
    _, booking_id = _make_matched_booking(client, customer_auth_headers, email="edit_not_yours@example.com")
    review_id = _create_review(client, customer_auth_headers, booking_id)

    other_token = signup_customer(client, email="other_editor@example.com")
    other_headers = {"Authorization": f"Bearer {other_token}"}
    res = client.put(f"/api/customer/reviews/{review_id}", json={"rating": 1}, headers=other_headers)
    assert res.status_code == 404


def test_delete_review(client, customer_auth_headers):
    _, booking_id = _make_matched_booking(client, customer_auth_headers, email="delete_review@example.com")
    review_id = _create_review(client, customer_auth_headers, booking_id)

    res = client.delete(f"/api/customer/reviews/{review_id}", headers=customer_auth_headers)
    assert res.status_code == 204

    mine = client.get("/api/customer/reviews", headers=customer_auth_headers).json()
    assert mine == []


def test_cannot_delete_another_customers_review(client, customer_auth_headers):
    _, booking_id = _make_matched_booking(client, customer_auth_headers, email="delete_not_yours@example.com")
    review_id = _create_review(client, customer_auth_headers, booking_id)

    other_token = signup_customer(client, email="other_deleter@example.com")
    other_headers = {"Authorization": f"Bearer {other_token}"}
    res = client.delete(f"/api/customer/reviews/{review_id}", headers=other_headers)
    assert res.status_code == 404

    # Still there — the delete above must not have gone through.
    mine = client.get("/api/customer/reviews", headers=customer_auth_headers).json()
    assert len(mine) == 1


def test_delete_review_updates_instructors_average_rating(client, customer_auth_headers):
    instructor_headers, booking_id = _make_matched_booking(client, customer_auth_headers, email="delete_updates_avg@example.com")
    review_id = _create_review(client, customer_auth_headers, booking_id, rating=2)

    my_booking = client.get("/api/customer/bookings/me", headers=customer_auth_headers).json()
    assert my_booking["instructor"]["average_rating"] == 2.0
    assert my_booking["instructor"]["review_count"] == 1

    res = client.delete(f"/api/customer/reviews/{review_id}", headers=customer_auth_headers)
    assert res.status_code == 204

    my_booking_after = client.get("/api/customer/bookings/me", headers=customer_auth_headers).json()
    assert my_booking_after["instructor"]["average_rating"] is None
    assert my_booking_after["instructor"]["review_count"] == 0


def test_my_written_reviews_requires_customer_auth(client):
    res = client.get("/api/customer/reviews")
    assert res.status_code == 401


def test_my_written_reviews_lists_only_this_customers_reviews(client, customer_auth_headers):
    _, booking_id = _make_matched_booking(client, customer_auth_headers, email="list_mine@example.com")
    _create_review(client, customer_auth_headers, booking_id)

    mine = client.get("/api/customer/reviews", headers=customer_auth_headers).json()
    assert len(mine) == 1
    assert mine[0]["booking_id"] == booking_id

    other_token = signup_customer(client, email="other_lister@example.com")
    other_headers = {"Authorization": f"Bearer {other_token}"}
    assert client.get("/api/customer/reviews", headers=other_headers).json() == []
