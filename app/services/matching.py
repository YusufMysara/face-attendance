"""Finding who a face belongs to, and recording attendance."""
from dataclasses import dataclass
from datetime import date

import numpy as np
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.ai.face_engine import MODEL_NAME
from app.db.models import Attendance, Employee, FaceEmbedding


@dataclass
class Match:
    employee_id: int
    name: str
    similarity: float  # cosine similarity: ~1.0 = same person, ~0 = unrelated


def find_match(session: Session, embedding: np.ndarray) -> Match | None:
    """The stored face closest to this one, or None if nobody is enrolled.
    The caller decides whether the similarity is high enough to count as a match."""
    distance = FaceEmbedding.embedding.cosine_distance(embedding)  # pgvector's <=> operator
    row = session.execute(
        select(FaceEmbedding.employee_id, Employee.name, (1 - distance).label("similarity"))
        .join(Employee)
        .where(FaceEmbedding.model == MODEL_NAME)  # embeddings from different models are not comparable
        .order_by(distance)
        .limit(1)
    ).first()
    return Match(row.employee_id, row.name, float(row.similarity)) if row else None


def mark_present(session: Session, employee_id: int, day: date, confidence: float) -> bool:
    """Record the first sighting of the day. True if recorded now, False if already present.
    Safe to call many times, even concurrently: the database keeps one row per person per day."""
    # RETURNING gives back the new row's id, or nothing when the row already existed. (Not rowcount:
    # through the ORM session it is always -1, "unknown".)
    new_id = session.execute(
        insert(Attendance)
        .values(employee_id=employee_id, day=day, confidence=confidence)
        .on_conflict_do_nothing(index_elements=["employee_id", "day"])
        .returning(Attendance.id)
    ).scalar_one_or_none()
    session.commit()
    return new_id is not None
