"""WAV 파일 찾기와 DCASE 파일명 해석.

DCASE Task 2 파일명 예시:
    ToyCar/train/section_00_source_train_normal_0001_car_A1_spd_28V_mic_1_noise_1.wav
여기서 기기 종류(ToyCar), 섹션(00), 도메인(source/target), 분할(train/test),
라벨(normal/anomaly)을 뽑아낸다. 형식이 다른 파일도 읽을 수 있게 실패하면 None을 넣는다.
"""
from __future__ import annotations

import re
from pathlib import Path

NAME_RE = re.compile(
    r"section_(?P<section>\d+)_(?P<domain>source|target)_(?P<split>train|test)_"
    r"(?P<label>normal|anomaly)_(?P<index>\d+)"
)


def find_wavs(root: str | Path) -> list[Path]:
    """root 아래의 모든 .wav 파일을 정렬해서 돌려준다."""
    return sorted(p for p in Path(root).rglob("*.wav") if p.is_file())


def parse_meta(path: Path) -> dict:
    """파일 경로에서 메타데이터(기기, 도메인, 라벨 등)를 뽑는다."""
    parts = path.parts
    # .../<machine>/<train|test>/<file>.wav 구조면 machine = 두 단계 위 폴더
    if len(parts) >= 3 and parts[-2] in ("train", "test"):
        machine = parts[-3]
    else:
        machine = path.parent.name
    m = NAME_RE.search(path.stem)
    meta = {
        "file": str(path),
        "machine": machine,
        "section": None,
        "domain": None,
        "split": None,
        "label": None,
        "meta_ok": bool(m),
    }
    if m:
        meta.update(
            section=m["section"], domain=m["domain"], split=m["split"], label=m["label"]
        )
    return meta
