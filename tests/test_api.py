"""The HTTP API, end to end through FastAPI, the real database and real image decoding.
Only the face engine is a stand-in (it returns the embeddings each test sets)."""
import pytest
from fastapi.testclient import TestClient
from helpers import FakeEngine, embedding, jpeg_bytes, near

from app.api.routes import MAX_UPLOAD_BYTES, get_engine
from app.main import app


@pytest.fixture
def engine():
    return FakeEngine()


@pytest.fixture
def client(engine):
    app.dependency_overrides[get_engine] = lambda: engine
    app.state.engine = engine  # used by /health
    yield TestClient(app)  # not used as a context manager, so the real models are not loaded
    app.dependency_overrides.clear()


def enroll(client, engine, name, vector):
    engine.embeddings = [] if vector is None else [vector]
    return client.post("/employees", data={"name": name}, files={"photo": ("photo.jpg", jpeg_bytes(), "image/jpeg")})


def recognize(client, engine, *vectors):
    engine.embeddings = list(vectors)
    return client.post("/recognize", files={"frame": ("frame.jpg", jpeg_bytes(), "image/jpeg")})


def test_health_reports_database_and_models(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "database": True, "models": True, "model": "sface_2021dec"}


# ---------- employees ----------

def test_enroll_list_and_delete_an_employee(client, engine):
    created = enroll(client, engine, "Sara", embedding(1))
    assert created.status_code == 201
    employee_id = created.json()["id"]

    assert client.get("/employees").json() == [{"id": employee_id, "name": "Sara"}]
    assert client.delete(f"/employees/{employee_id}").status_code == 204
    assert client.get("/employees").json() == []


def test_deleting_an_unknown_employee_is_404(client):
    assert client.delete("/employees/999").status_code == 404


def test_enrolling_the_same_face_twice_is_409(client, engine):
    # Regression for the duplicate-enrollment bug.
    assert enroll(client, engine, "Sara", embedding(1)).status_code == 201

    response = enroll(client, engine, "Sara again", near(embedding(1)))

    assert response.status_code == 409
    assert "already enrolled as Sara" in response.json()["detail"]
    assert len(client.get("/employees").json()) == 1


def test_enrolling_a_photo_without_a_face_is_422(client, engine):
    response = enroll(client, engine, "Sara", None)
    assert response.status_code == 422
    assert "exactly one face" in response.json()["detail"]


def test_a_file_that_is_not_an_image_is_422(client):
    response = client.post("/employees", data={"name": "Sara"}, files={"photo": ("x.txt", b"not an image", "text/plain")})
    assert response.status_code == 422
    assert response.json()["detail"] == "the file is not a valid image"


def test_an_oversized_upload_is_413(client):
    response = client.post("/recognize", files={"frame": ("big.bin", b"\0" * (MAX_UPLOAD_BYTES + 1), "image/jpeg")})
    assert response.status_code == 413


# ---------- recognition and attendance ----------

def test_recognizing_an_unknown_face_marks_nobody(client, engine):
    response = recognize(client, engine, embedding(5))

    [face] = response.json()["faces"]
    assert face["name"] is None
    assert face["newly_marked"] is False
    assert client.get("/attendance").json()["present"] == []


def test_recognizing_an_enrolled_face_marks_attendance_once(client, engine):
    enroll(client, engine, "Sara", embedding(1))

    first = recognize(client, engine, near(embedding(1))).json()["faces"][0]
    second = recognize(client, engine, near(embedding(1), seed=7)).json()["faces"][0]

    assert (first["name"], first["newly_marked"]) == ("Sara", True)
    assert (second["name"], second["newly_marked"]) == ("Sara", False)
    assert first["box"] == [10, 20, 30, 40]
    report = client.get("/attendance").json()
    assert [person["name"] for person in report["present"]] == ["Sara"]
    assert report["absent"] == []


def test_every_face_in_a_frame_gets_its_own_result(client, engine):
    enroll(client, engine, "Sara", embedding(1))

    faces = recognize(client, engine, near(embedding(1)), embedding(9)).json()["faces"]

    assert [face["name"] for face in faces] == ["Sara", None]


def test_the_match_threshold_is_configurable(client, engine, monkeypatch):
    enroll(client, engine, "Sara", embedding(1))
    monkeypatch.setenv("MATCH_THRESHOLD", "0.999")  # stricter than the ~0.99 similarity of the near copy

    [face] = recognize(client, engine, near(embedding(1))).json()["faces"]

    assert face["name"] is None
    assert face["similarity"] > 0.9  # still reported, which helps when tuning the threshold


def test_attendance_for_a_day_nobody_came_lists_everyone_absent(client, engine):
    enroll(client, engine, "Sara", embedding(1))
    recognize(client, engine, near(embedding(1)))

    report = client.get("/attendance", params={"day": "2000-01-01"}).json()

    assert report["present"] == []
    assert [person["name"] for person in report["absent"]] == ["Sara"]


def test_attendance_rejects_a_malformed_day(client):
    assert client.get("/attendance", params={"day": "banana"}).status_code == 422
