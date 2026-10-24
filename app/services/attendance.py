"""The daily report: who is present, and who is absent."""
from datetime import date

from sqlalchemy import and_, select
from sqlalchemy.orm import Session

from app.db.models import Attendance, Employee


def attendance_report(session: Session, day: date) -> tuple[list[tuple[Employee, Attendance]], list[Employee]]:
    """(present, absent). Absent is computed, not stored: an employee with no attendance row that day."""
    rows = session.execute(
        select(Employee, Attendance)
        .outerjoin(Attendance, and_(Attendance.employee_id == Employee.id, Attendance.day == day))
        .order_by(Employee.name)
    ).all()
    present = [(employee, record) for employee, record in rows if record is not None]
    absent = [employee for employee, record in rows if record is None]
    return present, absent
