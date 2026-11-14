"""스크립트 공통: 저장소 루트를 import 경로에 넣고, 지표 계산을 병렬로 돌린다."""
import os
import sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import pandas as pd  # noqa: E402

from pdq.io_utils import parse_meta  # noqa: E402
from pdq.metrics import compute_metrics  # noqa: E402


def _one(args):
    path, silence_dbfs = args
    row = parse_meta(Path(path))
    try:
        row.update(compute_metrics(path, silence_dbfs))
        row["read_error"] = ""
    except Exception as e:  # 읽을 수 없는 파일도 기록에 남긴다
        row["read_error"] = str(e)
    return row


def metrics_table(paths, silence_dbfs=-70.0, jobs=None) -> pd.DataFrame:
    jobs = jobs or max(1, (os.cpu_count() or 2) - 1)
    tasks = [(str(p), silence_dbfs) for p in paths]
    rows = []
    with ProcessPoolExecutor(max_workers=jobs) as ex:
        for i, r in enumerate(ex.map(_one, tasks, chunksize=16), 1):
            rows.append(r)
            if i % 500 == 0:
                print(f"  {i}/{len(tasks)} 파일 처리")
    df = pd.DataFrame(rows)
    bad = df[df["read_error"] != ""]
    if len(bad):
        print(f"[주의] 읽기 실패 {len(bad)}개 - results/read_errors.csv 참고")
    return df


# 차트 색 (상태 색은 PASS/WARN/FAIL에만 사용)
STATUS_COLORS = {"PASS": "#0ca30c", "WARN": "#fab219", "FAIL": "#d03b3b"}
SERIES_1 = "#2a78d6"
SERIES_2 = "#eb6834"
INK, INK2, SURFACE = "#0b0b0b", "#52514e", "#fcfcfb"


def setup_korean_font():
    """차트 한글 글꼴 설정 (Windows: 맑은 고딕, Mac: 애플고딕, Linux: 나눔/Noto)."""
    import matplotlib
    from matplotlib import font_manager

    have = {f.name for f in font_manager.fontManager.ttflist}
    for name in ["Malgun Gothic", "AppleGothic", "Apple SD Gothic Neo", "NanumGothic",
                 "Noto Sans CJK KR", "Noto Sans KR"]:
        if name in have:
            matplotlib.rcParams["font.family"] = name
            break
    else:
        print("[주의] 한글 글꼴을 찾지 못해 차트 글자가 깨질 수 있습니다 (예: 나눔고딕 설치).")
    matplotlib.rcParams["axes.unicode_minus"] = False
