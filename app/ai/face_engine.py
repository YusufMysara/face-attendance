"""Face detection + embedding with OpenCV only (YuNet detects, SFace embeds).

This layer knows nothing about HTTP or the database: image in, faces out.
"""
import threading
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np

MODELS_DIR = Path(__file__).resolve().parents[2] / "models_opencv"
DETECTOR_FILE = "face_detection_yunet_2026may.onnx"
RECOGNIZER_FILE = "face_recognition_sface_2021dec.onnx"

# Stored next to every embedding: an embedding only means something for the model that made it.
MODEL_NAME = "sface_2021dec"
EMBEDDING_SIZE = 128


@dataclass
class Face:
    bbox: tuple[int, int, int, int]  # x, y, width, height in pixels
    score: float  # detector confidence, 0..1
    embedding: np.ndarray  # EMBEDDING_SIZE floats


class FaceEngine:
    def __init__(self, models_dir: Path = MODELS_DIR, score_threshold: float = 0.5):
        # (320, 320) is a placeholder: the real size is set for every image in analyze().
        self._detector = cv2.FaceDetectorYN.create(
            str(models_dir / DETECTOR_FILE), "", (320, 320), score_threshold, 0.3, 5000
        )
        self._recognizer = cv2.FaceRecognizerSF.create(str(models_dir / RECOGNIZER_FILE), "")
        # setInputSize changes the detector's state, so concurrent requests must take turns.
        self._lock = threading.Lock()

    def analyze(self, image: np.ndarray) -> list[Face]:
        """Find every face in a BGR image and compute its embedding."""
        height, width = image.shape[:2]
        with self._lock:
            self._detector.setInputSize((width, height))
            _, rows = self._detector.detect(image)  # one row per face: x, y, w, h, 5 landmarks, score
            if rows is None:
                return []
            faces = []
            for row in rows:
                aligned = self._recognizer.alignCrop(image, row)  # rotate/crop so eyes and mouth line up
                embedding = self._recognizer.feature(aligned).flatten()
                x, y, w, h = (int(v) for v in row[:4])
                faces.append(Face(bbox=(x, y, w, h), score=float(row[14]), embedding=embedding))
            return faces


def cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
    """~1.0 = same person, ~0 = unrelated. The embeddings are not unit length, so we normalise."""
    return float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b)))
