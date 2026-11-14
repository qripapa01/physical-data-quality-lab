"""품질 판정 규칙. 지표(숫자)를 기준값과 비교해 PASS / WARN / FAIL을 정한다.

LLM이 아니라 이 규칙이 판정한다. 그래야 결과가 매번 같고, 기준을 문서로 설명할 수 있다.
각 규칙은 어떤 지표를 보는지, 어떤 품질 차원(완전성/정확성/일관성/유일성)에 속하는지 함께 적어 둔다.
이 정보는 온톨로지에도 그대로 들어간다.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

# 규칙 목록: id -> (이름, 보는 지표, 품질 차원)
RULES = {
    "R01_NAN": ("숫자가 아닌 값(NaN/Inf)", "nan_count", "Accuracy"),
    "R02_SAMPLE_RATE": ("샘플링레이트 불일치", "sample_rate", "Consistency"),
    "R03_CHANNELS": ("채널 수 불일치", "channels", "Consistency"),
    "R04_DURATION": ("길이 이상(잘림/초과)", "duration_s", "Completeness"),
    "R05_CLIPPING": ("클리핑", "clip_ratio", "Accuracy"),
    "R06_DC_OFFSET": ("DC 오프셋", "dc_offset", "Accuracy"),
    "R07_DROPOUT": ("끊김/정지 구간", "longest_flat_ms", "Completeness"),
    "R08_SILENCE": ("무음 과다", "silence_ratio", "Completeness"),
    "R09_METADATA": ("파일명 메타데이터 누락", "meta_ok", "Completeness"),
    "R10_DUPLICATE": ("내용이 같은 중복 파일", "md5", "Uniqueness"),
    "R11_OUTLIER": ("같은 기기·도메인 대비 통계적 이상치", "robust_z", "Accuracy"),
}

DIMENSION_KO = {
    "Completeness": "완전성",
    "Accuracy": "정확성",
    "Consistency": "일관성",
    "Uniqueness": "유일성",
}

SEVERITY_ORDER = {"PASS": 0, "WARN": 1, "FAIL": 2}


def load_thresholds(path: str | Path | None = None) -> dict:
    if path is None:
        path = Path(__file__).resolve().parent.parent / "config" / "thresholds.json"
    with open(path, encoding="utf-8") as f:
        cfg = json.load(f)
    return {k: v for k, v in cfg.items() if not k.startswith("_")}


def _issue(row, rule_id, severity, value, threshold, message):
    return {
        "file": row["file"],
        "machine": row["machine"],
        "domain": row["domain"],
        "rule_id": rule_id,
        "rule_name": RULES[rule_id][0],
        "metric": RULES[rule_id][1],
        "dimension": RULES[rule_id][2],
        "severity": severity,
        "value": value,
        "threshold": threshold,
        "message": message,
    }


def _two_level(row, rule_id, value, warn, fail, unit=""):
    """값이 warn/fail 기준을 넘으면 이슈를 하나 돌려준다."""
    if value > fail:
        return _issue(row, rule_id, "FAIL", value, fail, f"{value:.4g}{unit} > {fail}{unit}")
    if value > warn:
        return _issue(row, rule_id, "WARN", value, warn, f"{value:.4g}{unit} > {warn}{unit}")
    return None


def robust_z(values: pd.Series) -> pd.Series:
    """중앙값과 MAD로 계산한 z 점수. 이상치 몇 개에 흔들리지 않는다."""
    med = values.median()
    mad = (values - med).abs().median()
    if mad == 0 or np.isnan(mad):
        return pd.Series(0.0, index=values.index)
    return 0.6745 * (values - med) / mad


def evaluate(df: pd.DataFrame, cfg: dict) -> tuple[pd.DataFrame, pd.DataFrame]:
    """지표 표(df)를 받아 (파일별 판정 표, 이슈 목록 표)를 돌려준다."""
    issues = []
    sr_expected = cfg.get("expected_sample_rate") or int(df["sample_rate"].mode().iloc[0])
    ch_expected = cfg.get("expected_channels") or int(df["channels"].mode().iloc[0])
    # 길이 기준: 기기별 중앙값
    dur_median = df.groupby("machine")["duration_s"].transform("median")

    for i, row in df.iterrows():
        if row["nan_count"] > 0:
            issues.append(_issue(row, "R01_NAN", "FAIL", row["nan_count"], 0, "NaN/Inf 값 존재"))
        if row["sample_rate"] != sr_expected:
            issues.append(_issue(row, "R02_SAMPLE_RATE", "FAIL", row["sample_rate"], sr_expected,
                                 f"{row['sample_rate']} Hz != {sr_expected} Hz"))
        if row["channels"] != ch_expected:
            issues.append(_issue(row, "R03_CHANNELS", "WARN", row["channels"], ch_expected,
                                 f"{row['channels']}ch != {ch_expected}ch"))
        dev = abs(row["duration_s"] - dur_median[i]) / max(dur_median[i], 1e-9)
        it = _two_level(row, "R04_DURATION", dev, cfg["duration_dev_warn"], cfg["duration_dev_fail"])
        if it:
            it["message"] = f"길이 {row['duration_s']}s, 기기 중앙값 대비 {dev:.1%} 차이"
            issues.append(it)
        for rid, col, w, f, unit in [
            ("R05_CLIPPING", "clip_ratio", cfg["clip_ratio_warn"], cfg["clip_ratio_fail"], ""),
            ("R07_DROPOUT", "longest_flat_ms", cfg["flat_ms_warn"], cfg["flat_ms_fail"], "ms"),
            ("R08_SILENCE", "silence_ratio", cfg["silence_ratio_warn"], cfg["silence_ratio_fail"], ""),
        ]:
            it = _two_level(row, rid, float(row[col]), w, f, unit)
            if it:
                issues.append(it)
        it = _two_level(row, "R06_DC_OFFSET", abs(row["dc_offset"]), cfg["dc_offset_warn"], cfg["dc_offset_fail"])
        if it:
            issues.append(it)
        if not row["meta_ok"]:
            issues.append(_issue(row, "R09_METADATA", "WARN", False, True, "파일명에서 도메인/라벨을 읽을 수 없음"))

    # 데이터셋 단위 점검 1: 중복 (첫 파일은 원본으로 보고 두 번째부터 FAIL)
    dup = df[df.duplicated("md5", keep="first")]
    for _, row in dup.iterrows():
        first = df[df["md5"] == row["md5"]].iloc[0]["file"]
        issues.append(_issue(row, "R10_DUPLICATE", "FAIL", row["md5"][:8], "unique",
                             f"{Path(first).name} 와 내용 동일"))

    # 데이터셋 단위 점검 2: 같은 기기·도메인 묶음에서 통계적으로 튀는 파일
    z_cols = ["rms_dbfs", "spectral_flatness", "snr_est_db"]
    for _, g in df.groupby(["machine", "domain"], dropna=False):
        if len(g) < cfg["outlier_min_group"]:
            continue
        for col in z_cols:
            z = robust_z(g[col])
            for i in z.index[z.abs() > cfg["outlier_z_warn"]]:
                row = df.loc[i]
                issues.append(_issue(row, "R11_OUTLIER", "WARN", round(float(z[i]), 2),
                                     cfg["outlier_z_warn"], f"{col} robust z = {z[i]:.1f}"))

    issues_df = pd.DataFrame(issues, columns=[
        "file", "machine", "domain", "rule_id", "rule_name", "metric", "dimension",
        "severity", "value", "threshold", "message"])

    verdict = df[["file"]].copy()
    verdict["verdict"] = "PASS"
    if len(issues_df):
        worst = (issues_df.assign(s=issues_df["severity"].map(SEVERITY_ORDER))
                 .groupby("file")["s"].max())
        inv = {v: k for k, v in SEVERITY_ORDER.items()}
        verdict["verdict"] = verdict["file"].map(worst).map(inv).fillna("PASS")
    out = df.merge(verdict, on="file")
    return out, issues_df
