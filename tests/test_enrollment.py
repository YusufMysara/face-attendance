"""Enrolling employees. The face engine is a stand-in; everything else (database, matching) is real."""
import pytest
from helpers import BLANK_IMAGE, embedding, engine_with, near
from sqlalchemy import func, select

from app.ai.face_engine import MODEL_NAME
from app.db.models import Employee, FaceEmbedding
from app.services.enrollment import DuplicateFaceError, EnrollmentError, enroll_employee


def employee_count(session):
    return session.scalar(select(func.count()).select_from(Employee))


def test_enrolling_stores_one_employee_with_one_embedding(session):
    employee = enroll_employee(session, engine_with(embedding(1)), "  Sara  ", BLANK_IMAGE)

    assert employee.name == "Sara"  # surrounding spaces are trimmed
    rows = session.scalars(select(FaceEmbedding)).all()
    assert len(rows) == 1
    assert (rows[0].employee_id, rows[0].model) == (employee.id, MODEL_NAME)


def test_a_blank_name_is_refused_and_nothing_is_saved(session):
    with pytest.raises(EnrollmentError, match="name is required"):
        enroll_employee(session, engine_with(embedding(1)), "   ", BLANK_IMAGE)
    assert employee_count(session) == 0


@pytest.mark.parametrize("vectors", [[], [embedding(1), embedding(2)]], ids=["no face", "two faces"])
def test_a_photo_without_exactly_one_face_is_refused(session, vectors):
    with pytest.raises(EnrollmentError, match="exactly one face"):
        enroll_employee(session, engine_with(*vectors), "Sara", BLANK_IMAGE)
    assert employee_count(session) == 0


def test_the_same_face_cannot_be_enrolled_twice(session):
    # Regression: enrolling the same photo twice used to create two employees.
    enroll_employee(session, engine_with(embedding(1)), "Sara", BLANK_IMAGE)

    with pytest.raises(DuplicateFaceError, match="already enrolled as Sara"):
        enroll_employee(session, engine_with(near(embedding(1))), "Sara again", BLANK_IMAGE)

    assert employee_count(session) == 1  # the refused attempt saved nothing


def test_a_different_face_can_still_enroll(session):
    enroll_employee(session, engine_with(embedding(1)), "Sara", BLANK_IMAGE)
    enroll_employee(session, engine_with(embedding(2)), "Omar", BLANK_IMAGE)
    assert employee_count(session) == 2


def test_the_duplicate_check_uses_the_match_threshold(session, monkeypatch):
    enroll_employee(session, engine_with(embedding(1)), "Sara", BLANK_IMAGE)
    monkeypatch.setenv("MATCH_THRESHOLD", "0.999")  # stricter than the ~0.99 similarity of the near copy

    enroll_employee(session, engine_with(near(embedding(1))), "Sara twin", BLANK_IMAGE)

    assert employee_count(session) == 2
