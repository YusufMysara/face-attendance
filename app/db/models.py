"""The three tables. Rules live in the database (constraints), not only in application code."""
from datetime import date, datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import REAL, CheckConstraint, Date, DateTime, ForeignKey, Identity, Index, Integer, MetaData, Text, UniqueConstraint, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

from app.ai.face_engine import EMBEDDING_SIZE

# Fixed constraint/index names, so migrations are predictable and easy to read.
NAMING_CONVENTION = {
    "ix": "ix_%(table_name)s_%(column_0_name)s",
    "uq": "uq_%(table_name)s_%(constraint_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)


class Employee(Base):
    __tablename__ = "employees"
    __table_args__ = (CheckConstraint("length(btrim(name)) > 0", name="name_not_blank"),)

    id: Mapped[int] = mapped_column(Integer, Identity(always=True), primary_key=True)
    name: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    # passive_deletes: let the database's ON DELETE CASCADE do the work instead of loading rows first.
    embeddings: Mapped[list["FaceEmbedding"]] = relationship(back_populates="employee", cascade="all, delete-orphan", passive_deletes=True)


class FaceEmbedding(Base):
    __tablename__ = "face_embeddings"

    id: Mapped[int] = mapped_column(Integer, Identity(always=True), primary_key=True)
    employee_id: Mapped[int] = mapped_column(ForeignKey("employees.id", ondelete="CASCADE"), index=True)
    model: Mapped[str] = mapped_column(Text)  # which model made this embedding; only comparable within one model
    embedding = mapped_column(Vector(EMBEDDING_SIZE), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    employee: Mapped[Employee] = relationship(back_populates="embeddings")


class Attendance(Base):
    __tablename__ = "attendance"
    __table_args__ = (
        UniqueConstraint("employee_id", "day", name="employee_day"),  # one row per person per day
        CheckConstraint("confidence BETWEEN -1 AND 1", name="confidence_range"),
        Index("ix_attendance_day", "day"),
    )

    id: Mapped[int] = mapped_column(Integer, Identity(always=True), primary_key=True)
    employee_id: Mapped[int] = mapped_column(ForeignKey("employees.id", ondelete="CASCADE"))
    day: Mapped[date] = mapped_column(Date)  # the local date, computed in the app from the configured timezone
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    confidence: Mapped[float] = mapped_column(REAL)
