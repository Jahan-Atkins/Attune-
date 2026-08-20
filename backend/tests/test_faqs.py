"""
FAQs have no create endpoint (they're read-only content in the app),
so these tests insert rows directly through SQLAlchemy — the same
SessionLocal the app itself uses, since conftest.py pointed it at the
test database before anything was imported.
"""
from app.database import SessionLocal
from app import models


def _create_faq(question, category):
    db = SessionLocal()
    faq = models.FAQ(question=question, category=category)
    db.add(faq)
    db.commit()
    db.refresh(faq)
    db.close()
    return faq


def test_faqs_require_auth(client):
    res = client.get("/api/faqs")
    assert res.status_code == 401


def test_list_and_filter_faqs(client, auth_headers):
    _create_faq("How do refunds work?", "payments")
    _create_faq("How do I update my calendar?", "app use")

    all_res = client.get("/api/faqs", headers=auth_headers)
    assert len(all_res.json()) == 2

    payments_res = client.get("/api/faqs?category=payments", headers=auth_headers)
    assert len(payments_res.json()) == 1
    assert payments_res.json()[0]["category"] == "payments"
