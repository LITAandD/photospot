"""인물 영역 제외 마스크. True = 배경(분석 대상) 픽셀.

사용자 업로드 사진은 대부분 인물이 크게 나오므로 마스킹이 중요하다.
기본은 마스킹 없음이고, rembg(u2net_human_seg)를 설치하면 인물을 제외한다.
"""
from __future__ import annotations

from typing import Protocol

import numpy as np
from PIL import Image


class BackgroundMasker(Protocol):
    def background_mask(self, img: Image.Image) -> np.ndarray: ...


class NoMask:
    def background_mask(self, img: Image.Image) -> np.ndarray:
        return np.ones((img.height, img.width), dtype=bool)


class RembgHumanMask:
    """pip install rembg onnxruntime — 첫 실행 시 모델을 내려받는다."""

    def __init__(self, model: str = "u2net_human_seg"):
        from rembg import new_session
        self._session = new_session(model)

    def background_mask(self, img: Image.Image) -> np.ndarray:
        from rembg import remove
        person = remove(img.convert("RGB"), session=self._session, only_mask=True)
        return np.asarray(person.convert("L")) < 128


def get_masker(name: str) -> BackgroundMasker:
    return RembgHumanMask() if name == "rembg" else NoMask()
