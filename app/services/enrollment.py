"""Enrolling an employee: turn one photo into a stored face embedding."""
import numpy as np
from sqlalchemy.orm import Session

from app.ai.face_engine import MODEL_NAME, FaceEngine
from app.config import match_threshold
from app.db.models import Employee, FaceEmbedding
from app.services.matching import find_match


class EnrollmentError(ValueError):
    """The request cannot be enrolled; the message is safe to show to the user."""


class DuplicateFaceError(EnrollmentError):
    """This face already belongs to an enrolled employee."""


def enroll_employee(session: Session, engine: FaceEngine, name: str, image: np.ndarray) -> Employee:
    name = name.strip()
    if not name:
        raise EnrollmentError("name is required")

    # Slow CPU work first, before touching the database, so no transaction stays open meanwhile.
    faces = engine.analyze(image)
    if len(faces) != 1:
        raise EnrollmentError(f"expected exactly one face in the photo, found {len(faces)}")

    # If recognition would already identify this face as someone, a second employee would make
    # attendance ambiguous (and leave one of them "absent" forever), so refuse.
    embedding = faces[0].embedding
    existing = find_match(session, embedding)
    if existing is not None and existing.similarity >= match_threshold():
        raise DuplicateFaceError(f"this face is already enrolled as {existing.name} (match {existing.similarity:.2f})")

    # One commit: the employee and their embedding are saved together, or not at all.
    employee = Employee(name=name, embeddings=[FaceEmbedding(model=MODEL_NAME, embedding=embedding)])
    session.add(employee)
    session.commit()
    return employee
