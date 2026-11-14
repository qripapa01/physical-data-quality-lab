"""결함 주입: 깨끗한 파일에 '알고 있는' 결함을 일부러 넣는다.

점검기가 이 결함을 찾아내는지 보면 점검기 자체의 성능(검출률)을 시험할 수 있다.
음성인식에서 깨끗한 음성에 잡음을 섞어 성능을 시험하던 것과 같은 방법이다.
결함마다 세기(level)를 약/중/강으로 바꿔 넣어, 어느 세기부터 놓치는지(검출 한계)도 본다.
각 결함에는 '이 결함이면 이 규칙에 걸려야 한다'는 기대 규칙을 함께 적는다.
"""
from __future__ import annotations

import numpy as np
from scipy.signal import resample_poly


def clipping(x, sr, rng, level):
    """level = 피크를 몇 배로 키운 뒤 잘라내는지 (1.05 = 피크 근처만 살짝 잘림)."""
    gain = level / max(np.max(np.abs(x)), 1e-9)
    return np.clip(x * gain, -1.0, 1.0), sr


def dropout(x, sr, rng, level):
    """level = 0으로 끊긴 구간 길이(ms)."""
    y = x.copy()
    n = int(level / 1000 * sr)
    start = rng.integers(0, max(len(y) - n, 1))
    y[start:start + n] = 0.0
    return y, sr


def dc_offset(x, sr, rng, level):
    return x + level, sr


def white_noise(x, sr, rng, level):
    """level = SNR(dB). 값이 작을수록 잡음이 큼."""
    p = np.mean(x**2) / 10 ** (level / 10)
    return x + rng.normal(0, np.sqrt(p), len(x)), sr


def silence(x, sr, rng, level):
    """level = 감쇠량(dB). 마이크가 빠졌거나 게인이 0에 가까운 상황."""
    return x * 10 ** (level / 20), sr


def wrong_rate(x, sr, rng, level):
    return resample_poly(x, 1, 2), sr // 2


def truncate(x, sr, rng, level):
    """level = 남는 길이 비율."""
    return x[: int(len(x) * level)], sr


def duplicate(x, sr, rng, level):
    return x, sr


# 이름 -> (함수, 기대 규칙, 설명, 세기 목록[약 -> 강])
DEFECTS = {
    "clipping": (clipping, "R05_CLIPPING", "클리핑: 피크 배율", [1.05, 1.5, 3.0]),
    "dropout": (dropout, "R07_DROPOUT", "끊김 길이(ms)", [10, 50, 200]),
    "dc_offset": (dc_offset, "R06_DC_OFFSET", "DC 오프셋", [0.005, 0.02, 0.08]),
    "white_noise": (white_noise, "R11_OUTLIER", "백색잡음 SNR(dB)", [20, 10, 0]),
    "silence": (silence, "R08_SILENCE", "레벨 감쇠(dB)", [-20, -40, -80]),
    "truncate": (truncate, "R04_DURATION", "남은 길이 비율", [0.97, 0.9, 0.5]),
    "wrong_rate": (wrong_rate, "R02_SAMPLE_RATE", "샘플링레이트 절반", [1]),
    "duplicate": (duplicate, "R10_DUPLICATE", "중복 파일", [1]),
}
