"""Small building blocks shared by the tests."""
import cv2
import numpy as np

from app.ai.face_engine import EMBEDDING_SIZE, Face

BLANK_IMAGE = np.zeros((48, 64, 3), dtype=np.uint8)


def embedding(seed: int) -> np.ndarray:
    """A reproducible fake face. Two different seeds are unrelated people (similarity near 0)."""
    return np.random.default_rng(seed).normal(size=EMBEDDING_SIZE).astype(np.float32)


def near(vector: np.ndarray, seed: int = 999, noise: float = 0.15) -> np.ndarray:
    """The same person on another photo: the same vector plus a little noise (similarity about 0.99)."""
    return vector + np.random.default_rng(seed).normal(scale=noise, size=vector.shape).astype(np.float32)


class FakeEngine:
    """Stands in for FaceEngine: returns one face per embedding the test sets, whatever the image is."""

    def __init__(self):
        self.embeddings: list[np.ndarray] = []

    def analyze(self, image):
        return [Face(bbox=(10, 20, 30, 40), score=0.95, embedding=e) for e in self.embeddings]


def engine_with(*vectors: np.ndarray) -> FakeEngine:
    engine = FakeEngine()
    engine.embeddings = list(vectors)
    return engine


def jpeg_bytes() -> bytes:
    """A real, valid JPEG, so the API's image decoding runs for real."""
    ok, buffer = cv2.imencode(".jpg", BLANK_IMAGE)
    assert ok
    return buffer.tobytes()
