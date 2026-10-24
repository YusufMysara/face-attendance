"""The real face models (a quick startup check) and the day-boundary setting."""
import numpy as np
import pytest

from app.ai.face_engine import EMBEDDING_SIZE, FaceEngine, cosine_similarity
from app.services.clock import today


def test_the_real_models_load_and_find_no_face_in_a_blank_frame():
    engine = FaceEngine()  # loads YuNet and SFace from models_opencv/
    assert engine.analyze(np.full((480, 640, 3), 128, dtype=np.uint8)) == []


def test_cosine_similarity_of_identical_and_unrelated_vectors():
    vector = np.random.default_rng(0).normal(size=EMBEDDING_SIZE)
    assert cosine_similarity(vector, vector) == pytest.approx(1.0)
    assert cosine_similarity(np.array([1.0, 0.0]), np.array([0.0, 1.0])) == pytest.approx(0.0)


def test_today_follows_the_timezone_setting(monkeypatch):
    monkeypatch.setenv("TIMEZONE", "Pacific/Kiritimati")  # UTC+14
    far_east = today()
    monkeypatch.setenv("TIMEZONE", "Etc/GMT+12")  # UTC-12, which is 26 hours behind
    far_west = today()
    assert far_east > far_west  # 26 hours apart, so the calendar date always differs
