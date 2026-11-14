"""데모용 합성 기기음 데이터 만들기 (DCASE Task 2와 같은 폴더·파일명 구조).

실제 DCASE 데이터가 없어도 전체 실습을 끝까지 돌려 볼 수 있게 한다.
'현장에서 흔한 문제' 몇 개를 일부러 심어 두어(--no-plant로 끌 수 있음) 1단계 점검에서 찾아보게 한다.

사용:  python scripts/00_make_demo_data.py --out data/demo
"""
import argparse
from pathlib import Path

import numpy as np
import soundfile as sf
from scipy.signal import lfilter, resample_poly

SR = 16000
DUR = 3.0


def colored_noise(rng, n, a=0.97):
    return lfilter([1], [1, -a], rng.normal(0, 1, n)) * (1 - a)


def fan(rng, t, domain, anomaly):
    f0 = (50 if domain == "source" else 65) * rng.uniform(0.98, 1.02)
    x = sum((0.8 ** k) * np.sin(2 * np.pi * f0 * k * t + rng.uniform(0, 6.28)) for k in range(1, 9))
    if anomaly:
        x = x + 0.6 * np.sin(2 * np.pi * 1.5 * f0 * t) * (1 + 0.5 * np.sin(2 * np.pi * 3 * t))
    return x + 6 * colored_noise(rng, len(t))


def pump(rng, t, domain, anomaly):
    fc, fm = (300, 5) if domain == "source" else (360, 7)
    x = np.sin(2 * np.pi * fc * rng.uniform(0.99, 1.01) * t) * (1 + 0.5 * np.sin(2 * np.pi * fm * t))
    if anomaly:  # 불규칙한 노킹
        for c in rng.uniform(0, t[-1], 6):
            i = int(c * SR)
            n = min(800, len(t) - i)
            x[i:i + n] += 2.5 * np.exp(-np.arange(n) / 120) * np.sin(2 * np.pi * 1800 * np.arange(n) / SR)
    return x + 0.4 * rng.normal(0, 1, len(t))


def valve(rng, t, domain, anomaly):
    period = 0.25 if domain == "source" else 0.2
    x = 0.15 * rng.normal(0, 1, len(t))
    clicks = np.arange(0.05, t[-1], period)
    if anomaly:
        clicks = np.sort(np.concatenate([clicks + rng.normal(0, 0.03, len(clicks)),
                                         rng.uniform(0, t[-1], 4)]))
    for c in clicks:
        i = int(max(c, 0) * SR)
        n = min(600, len(t) - i)
        if n > 0:
            x[i:i + n] += 3 * np.exp(-np.arange(n) / 80) * np.sin(2 * np.pi * 2500 * np.arange(n) / SR)
    return x


MACHINES = {"fan": fan, "pump": pump, "valve": valve}
# (분할, 도메인, 라벨, 개수) - DCASE처럼 target 학습 데이터는 아주 적게
LAYOUT = [("train", "source", "normal", 40), ("train", "target", "normal", 4),
          ("test", "source", "normal", 10), ("test", "source", "anomaly", 10),
          ("test", "target", "normal", 10), ("test", "target", "anomaly", 10)]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="data/demo")
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--no-plant", action="store_true", help="결함을 심지 않음")
    args = ap.parse_args()
    rng = np.random.default_rng(args.seed)
    t = np.arange(int(SR * DUR)) / SR
    out = Path(args.out)
    n_files = 0
    for mname, fn in MACHINES.items():
        for split, domain, label, count in LAYOUT:
            d = out / mname / split
            d.mkdir(parents=True, exist_ok=True)
            for k in range(1, count + 1):
                x = fn(rng, t, domain, label == "anomaly")
                x = x / np.sqrt(np.mean(x**2)) * 10 ** (rng.uniform(-30, -24) / 20)  # RMS -30~-24 dBFS
                name = f"section_00_{domain}_{split}_{label}_{k:04d}_demo.wav"
                sf.write(d / name, x, SR, subtype="PCM_16")
                n_files += 1

    if not args.no_plant:
        def path(m, split, dom, lab, k):
            return out / m / split / f"section_00_{dom}_{split}_{lab}_{k:04d}_demo.wav"
        # 1) 클리핑: 입력 게인이 너무 높았던 녹음
        p = path("fan", "train", "source", "normal", 3)
        x, _ = sf.read(p)
        sf.write(p, np.clip(x * 40, -1, 1), SR, subtype="PCM_16")
        # 2) 끊김: 수집 장비 버퍼 오류로 300 ms가 0
        p = path("pump", "train", "source", "normal", 5)
        x, _ = sf.read(p)
        x[16000:16000 + 4800] = 0
        sf.write(p, x, SR, subtype="PCM_16")
        # 3) 중복: 같은 파일이 이름만 바뀌어 두 번 들어감
        x, _ = sf.read(path("valve", "test", "target", "normal", 1))
        sf.write(path("valve", "test", "target", "normal", 2), x, SR, subtype="PCM_16")
        # 4) 샘플링레이트: 다른 장비로 8 kHz 녹음
        p = path("fan", "test", "source", "normal", 7)
        x, _ = sf.read(p)
        sf.write(p, resample_poly(x, 1, 2), SR // 2, subtype="PCM_16")
        print("심은 결함 4개: fan 클리핑, pump 끊김, valve 중복, fan 8kHz")
    print(f"{n_files}개 파일 생성 -> {out}")


if __name__ == "__main__":
    main()
