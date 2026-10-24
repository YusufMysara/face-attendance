"""HTTP endpoints. Thin on purpose: read the request, call a service, shape the response."""
import logging
import time
from datetime import date
from typing import Annotated

import cv2
import numpy as np
from fastapi import APIRouter, Depends, Form, HTTPException, Request, Response, UploadFile
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.ai.face_engine import MODEL_NAME, FaceEngine
from app.api.schemas import AttendanceOut, EmployeeOut, FaceResult, HealthOut, PresentOut, RecognizeOut
from app.config import match_threshold
from app.db.models import Employee
from app.db.session import get_session
from app.services.attendance import attendance_report
from app.services.clock import today
from app.services.enrollment import DuplicateFaceError, EnrollmentError, enroll_employee
from app.services.matching import find_match, mark_present

logger = logging.getLogger("attendance")
router = APIRouter()

MAX_UPLOAD_BYTES = 5 * 1024 * 1024


def get_engine(request: Request) -> FaceEngine:
    return request.app.state.engine


DbSession = Annotated[Session, Depends(get_session)]
Engine = Annotated[FaceEngine, Depends(get_engine)]


def read_image(upload: UploadFile) -> np.ndarray:
    data = upload.file.read(MAX_UPLOAD_BYTES + 1)
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(413, "image too large (max 5 MB)")
    image = cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_COLOR)
    if image is None:
        raise HTTPException(422, "the file is not a valid image")
    return image


@router.get("/health", response_model=HealthOut)
def health(request: Request, response: Response, session: DbSession):
    try:
        session.execute(text("SELECT 1"))
        database = True
    except Exception:
        logger.exception("health check: database unreachable")
        database = False
    models = getattr(request.app.state, "engine", None) is not None
    if not (database and models):
        response.status_code = 503
    return HealthOut(status="ok" if database and models else "unavailable", database=database, models=models, model=MODEL_NAME)


@router.post("/employees", status_code=201, response_model=EmployeeOut)
def create_employee(name: Annotated[str, Form(max_length=100)], photo: UploadFile, session: DbSession, engine: Engine):
    try:
        return enroll_employee(session, engine, name, read_image(photo))
    except DuplicateFaceError as error:
        raise HTTPException(409, str(error)) from error
    except EnrollmentError as error:
        raise HTTPException(422, str(error)) from error


@router.get("/employees", response_model=list[EmployeeOut])
def list_employees(session: DbSession):
    return session.scalars(select(Employee).order_by(Employee.name)).all()


@router.delete("/employees/{employee_id}", status_code=204)
def delete_employee(employee_id: int, session: DbSession):
    employee = session.get(Employee, employee_id)
    if employee is None:
        raise HTTPException(404, "employee not found")
    session.delete(employee)  # the database cascades to their embeddings and attendance
    session.commit()


@router.post("/recognize", response_model=RecognizeOut)
def recognize(frame: UploadFile, session: DbSession, engine: Engine):
    image = read_image(frame)
    started = time.perf_counter()
    faces = engine.analyze(image)
    analyze_ms = (time.perf_counter() - started) * 1000

    threshold, day = match_threshold(), today()
    results = []
    for face in faces:
        match = find_match(session, face.embedding)
        known = match is not None and match.similarity >= threshold
        results.append(
            FaceResult(
                box=face.bbox,
                name=match.name if known else None,
                similarity=round(match.similarity, 3) if match else None,
                newly_marked=mark_present(session, match.employee_id, day, match.similarity) if known else False,
            )
        )
    logger.info("recognize: %d face(s), analyze %.0f ms, total %.0f ms", len(faces), analyze_ms, (time.perf_counter() - started) * 1000)
    return RecognizeOut(faces=results)


@router.get("/attendance", response_model=AttendanceOut)
def attendance(session: DbSession, day: date | None = None):
    day = day or today()
    present, absent = attendance_report(session, day)
    return AttendanceOut(
        day=day,
        present=[PresentOut(id=e.id, name=e.name, first_seen_at=a.first_seen_at, confidence=a.confidence) for e, a in present],
        absent=absent,
    )
