"""Matching, attendance and the database rules, all against a real PostgreSQL with pgvector."""
from datetime import date

import numpy as np
import pytest
from helpers import embedding, near
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from app.ai.face_engine import MODEL_NAME
from app.db.models import Attendance, Employee, FaceEmbedding
from app.services.attendance import attendance_report
from app.services.matching import find_match, mark_present

DAY = date(2026, 1, 5)


def add_employee(session, name, vector, model=MODEL_NAME):
    employee = Employee(name=name, embeddings=[FaceEmbedding(model=model, embedding=vector)])
    session.add(employee)
    session.commit()
    return employee


def count(session, table):
    return session.scalar(select(func.count()).select_from(table))


# ---------- find_match ----------

def test_find_match_returns_none_when_nobody_is_enrolled(session):
    assert find_match(session, embedding(1)) is None


def test_find_match_picks_the_closest_person(session):
    alice = add_employee(session, "Alice", embedding(1))
    add_employee(session, "Bob", embedding(2))

    match = find_match(session, near(embedding(1)))

    assert (match.employee_id, match.name) == (alice.id, "Alice")
    assert match.similarity > 0.95


def test_find_match_reports_low_similarity_for_a_stranger(session):
    add_employee(session, "Alice", embedding(1))
    assert find_match(session, embedding(2)).similarity < 0.3  # unrelated faces score near 0


def test_find_match_ignores_embeddings_made_by_another_model(session):
    alice = add_employee(session, "Alice", embedding(1))
    query = near(embedding(1))
    # Identical to the query, so it would win easily if the model filter were missing.
    add_employee(session, "Impostor", query, model="some_other_model")

    assert find_match(session, query).employee_id == alice.id


# ---------- mark_present ----------

def test_mark_present_is_true_only_for_the_first_sighting_of_the_day(session):
    # Regression: this used to return False on the first call (rowcount is -1 through the ORM).
    employee = add_employee(session, "Alice", embedding(1))

    assert mark_present(session, employee.id, DAY, 0.90) is True
    assert mark_present(session, employee.id, DAY, 0.95) is False

    rows = session.scalars(select(Attendance)).all()
    assert len(rows) == 1
    assert rows[0].confidence == pytest.approx(0.90)  # the first sighting is kept


def test_mark_present_again_on_another_day_is_recorded(session):
    employee = add_employee(session, "Alice", embedding(1))
    assert mark_present(session, employee.id, DAY, 0.9) is True
    assert mark_present(session, employee.id, date(2026, 1, 6), 0.9) is True
    assert count(session, Attendance) == 2


# ---------- the daily report ----------

def test_report_splits_present_and_absent_by_day(session):
    sara = add_employee(session, "Sara", embedding(1))
    add_employee(session, "Omar", embedding(2))
    add_employee(session, "Lina", embedding(3))
    mark_present(session, sara.id, DAY, 0.8)

    present, absent = attendance_report(session, DAY)
    assert [employee.name for employee, _ in present] == ["Sara"]
    assert [employee.name for employee in absent] == ["Lina", "Omar"]  # ordered by name

    present, absent = attendance_report(session, date(2026, 1, 6))  # nobody was seen that day
    assert present == []
    assert len(absent) == 3


# ---------- rules enforced by the database itself ----------

def test_deleting_an_employee_removes_their_embeddings_and_attendance(session):
    employee = add_employee(session, "Alice", embedding(1))
    mark_present(session, employee.id, DAY, 0.9)

    session.delete(employee)
    session.commit()

    assert (count(session, Employee), count(session, FaceEmbedding), count(session, Attendance)) == (0, 0, 0)


def test_database_rejects_a_second_attendance_row_for_the_same_day(session):
    employee = add_employee(session, "Alice", embedding(1))
    session.add_all([Attendance(employee_id=employee.id, day=DAY, confidence=0.9) for _ in range(2)])
    with pytest.raises(IntegrityError):
        session.commit()


def test_database_rejects_a_blank_name(session):
    session.add(Employee(name="   "))
    with pytest.raises(IntegrityError):
        session.commit()


def test_database_rejects_confidence_outside_minus_one_to_one(session):
    employee = add_employee(session, "Alice", embedding(1))
    session.add(Attendance(employee_id=employee.id, day=DAY, confidence=2.0))
    with pytest.raises(IntegrityError):
        session.commit()


def test_database_rejects_a_face_row_without_an_embedding(session):
    # Regression: the column was accidentally nullable in the first generated migration.
    employee = add_employee(session, "Alice", embedding(1))
    session.add(FaceEmbedding(employee_id=employee.id, model=MODEL_NAME, embedding=None))
    with pytest.raises(IntegrityError):
        session.commit()


def test_database_rejects_an_embedding_of_the_wrong_size(session):
    employee = Employee(name="Alice", embeddings=[FaceEmbedding(model=MODEL_NAME, embedding=np.zeros(64, dtype=np.float32))])
    session.add(employee)
    with pytest.raises(SQLAlchemyError):
        session.commit()
