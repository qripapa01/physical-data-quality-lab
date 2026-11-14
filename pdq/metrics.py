"""파일 하나의 품질 지표 계산.

모든 지표는 사람이 귀로 들어 판단하던 것을 숫자로 바꾼 것이다.
- 클리핑: 소리가 너무 커서 최대값에 잘린 샘플 비율
- DC 오프셋: 파형 평균이 0에서 벗어난 정도
- 정지 구간: 같은 값이 계속 이어진 가장 긴 구간(ms) -> 결측/끊김/센서 멈춤
- 무음 비율: 거의 소리가 없는 프레임 비율
- 추정 SNR: 프레임 에너지 상위 10% / 하위 10% 비율 (정확한 SNR이 아닌 비교용 지표)
- 스펙트럼 평탄도: 0에 가까우면 음색(톤)이 뚜렷, 1에 가까우면 백색잡음 같은 소리
"""
from __future__ import annotations

import hashlib
from pathlib import Path

import numpy as np
import soundfile as sf

EPS = 1e-12


def _db(x: float) -> float:
    return float(10.0 * np.log10(max(x, EPS)))


def _frames(x: np.ndarray, frame: int, hop: int) -> np.ndarray:
    if len(x) < frame:
        x = np.pad(x, (0, frame - len(x)))
    n = 1 + (len(x) - frame) // hop
    idx = np.arange(frame)[None, :] + hop * np.arange(n)[:, None]
    return x[idx]


def longest_flat_run(x: np.ndarray) -> int:
    """연속으로 같은 값이 이어진 가장 긴 샘플 수."""
    if len(x) < 2:
        return len(x)
    same = np.diff(x) == 0
    if not same.any():
        return 1
    # True 구간 길이 구하기
    padded = np.concatenate(([False], same, [False]))
    edges = np.flatnonzero(padded[1:] != padded[:-1])
    runs = edges[1::2] - edges[::2]
    return int(runs.max()) + 1


def file_md5(path: Path) -> str:
    h = hashlib.md5()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def compute_metrics(path: str | Path, silence_dbfs: float = -70.0) -> dict:
    """WAV 파일 하나의 품질 지표를 dict로 돌려준다."""
    path = Path(path)
    info = sf.info(str(path))
    x2d, sr = sf.read(str(path), always_2d=True, dtype="float64")
    x = x2d.mean(axis=1)  # 여러 채널이면 평균해서 본다

    nan_count = int(np.count_nonzero(~np.isfinite(x)))
    x = np.nan_to_num(x)

    frame = int(0.032 * sr)  # 32 ms 프레임
    hop = frame // 2
    fr = _frames(x, frame, hop)
    frame_pow = (fr**2).mean(axis=1)
    frame_db = 10.0 * np.log10(frame_pow + EPS)

    # 스펙트럼 평탄도: 기하평균 / 산술평균 (프레임별 평균)
    win = np.hanning(frame)
    spec = np.abs(np.fft.rfft(fr * win, axis=1)) ** 2 + EPS
    flatness = np.exp(np.log(spec).mean(axis=1)) / spec.mean(axis=1)
    loud = frame_db > silence_dbfs
    flat_mean = float(flatness[loud].mean()) if loud.any() else 1.0

    p90, p10 = np.percentile(frame_pow, [90, 10])

    return {
        "sample_rate": int(sr),
        "channels": int(info.channels),
        "subtype": info.subtype,
        "duration_s": round(len(x) / sr, 4),
        "nan_count": nan_count,
        "peak_dbfs": round(_db(float(np.max(np.abs(x)) ** 2)), 2),
        "rms_dbfs": round(_db(float((x**2).mean())), 2),
        "clip_ratio": float(np.mean(np.abs(x) >= 0.999)),
        "dc_offset": float(x.mean()),
        "longest_flat_ms": round(1000.0 * longest_flat_run(x) / sr, 2),
        "silence_ratio": float(np.mean(frame_db < silence_dbfs)),
        "snr_est_db": round(_db(p90) - _db(p10), 2),
        "spectral_flatness": round(flat_mean, 4),
        "md5": file_md5(path),
    }
