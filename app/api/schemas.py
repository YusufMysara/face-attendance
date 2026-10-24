"""The shape of every API response."""
from datetime import date, datetime

from pydantic import BaseModel, ConfigDict


class EmployeeOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)  # build it straight from a database object

    id: int
    name: str


class FaceResult(BaseModel):
    box: tuple[int, int, int, int]  # x, y, width, height in the uploaded image
    name: str | None  # None = unknown face
    similarity: float | None  # best match score, even for unknown faces (useful when tuning the threshold)
    newly_marked: bool  # True only the first time this person is seen today


class RecognizeOut(BaseModel):
    faces: list[FaceResult]


class PresentOut(BaseModel):
    id: int
    name: str
    first_seen_at: datetime
    confidence: float


class AttendanceOut(BaseModel):
    day: date
    present: list[PresentOut]
    absent: list[EmployeeOut]


class HealthOut(BaseModel):
    status: str
    database: bool
    models: bool
    model: str
    threshold: float  # the current match threshold, so the page can explain scores without hard-coding it
