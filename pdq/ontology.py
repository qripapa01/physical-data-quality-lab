"""품질 점검 결과를 온톨로지(지식그래프)로 만들고 SPARQL로 질의한다.

국제 표준 어휘를 빌려 쓴다.
- SOSA (W3C): 센서(Sensor), 관측(Observation), 관측대상(FeatureOfInterest)
- DQV  (W3C): 품질 측정(QualityMeasurement), 지표(Metric), 품질 차원(Dimension)
그 위에 이 실습용 어휘(pdq:)를 조금 더한다: 기계, 마이크, 녹음, 품질 규칙, 품질 이슈.

트리플 예:
    obs:fan_0001  sosa:hasFeatureOfInterest  machine:fan
    obs:fan_0001  sosa:madeBySensor          sensor:fan_mic
    mm:fan_0001_clip  dqv:computedOn  obs:fan_0001 ;  dqv:isMeasurementOf pdq:clip_ratio ; dqv:value 0.0002
"""
from __future__ import annotations

import hashlib
import re
from pathlib import Path

import pandas as pd
from rdflib import RDF, RDFS, OWL, XSD, Graph, Literal, Namespace

from .rules import DIMENSION_KO, RULES

SOSA = Namespace("http://www.w3.org/ns/sosa/")
DQV = Namespace("http://www.w3.org/ns/dqv#")
PDQ = Namespace("https://github.com/qripapa01/physical-data-quality-lab/ontology#")
DATA = Namespace("https://github.com/qripapa01/physical-data-quality-lab/data/")

# 그래프에 넣을 지표와 품질 차원
METRICS = {
    "sample_rate": ("샘플링레이트(Hz)", "Consistency"),
    "duration_s": ("길이(초)", "Completeness"),
    "clip_ratio": ("클리핑 비율", "Accuracy"),
    "dc_offset": ("DC 오프셋", "Accuracy"),
    "longest_flat_ms": ("최장 정지 구간(ms)", "Completeness"),
    "silence_ratio": ("무음 비율", "Completeness"),
    "rms_dbfs": ("RMS 레벨(dBFS)", "Accuracy"),
    "snr_est_db": ("추정 SNR(dB)", "Accuracy"),
    "spectral_flatness": ("스펙트럼 평탄도", "Accuracy"),
}
# 규칙이 보는 지표 중 그래프 측정값이 아닌 것(메타데이터 등)
EXTRA_METRICS = {
    "nan_count": ("NaN/Inf 개수", "Accuracy"),
    "channels": ("채널 수", "Consistency"),
    "meta_ok": ("메타데이터 완전 여부", "Completeness"),
    "md5": ("파일 해시", "Uniqueness"),
    "robust_z": ("묶음 대비 robust z", "Accuracy"),
}


def _slug(text: str) -> str:
    s = re.sub(r"[^A-Za-z0-9]+", "_", text).strip("_")
    return f"{s[-60:]}_{hashlib.md5(text.encode()).hexdigest()[:6]}"


def build_schema() -> Graph:
    """클래스, 관계, 품질 차원, 지표, 규칙을 정의한 스키마(TBox)."""
    g = Graph()
    for p, ns in [("sosa", SOSA), ("dqv", DQV), ("pdq", PDQ), ("owl", OWL)]:
        g.bind(p, ns)

    classes = {
        PDQ.Machine: (SOSA.FeatureOfInterest, "기계(관측 대상)"),
        PDQ.Microphone: (SOSA.Sensor, "마이크(센서)"),
        PDQ.AudioRecording: (SOSA.Observation, "녹음 파일(관측)"),
        PDQ.QualityRule: (None, "품질 판정 규칙"),
        PDQ.QualityIssue: (None, "품질 이슈(규칙 위반 기록)"),
    }
    for c, (parent, label) in classes.items():
        g.add((c, RDF.type, OWL.Class))
        g.add((c, RDFS.label, Literal(label, lang="ko")))
        if parent is not None:
            g.add((c, RDFS.subClassOf, parent))

    obj_props = {
        PDQ.hasIssue: (PDQ.AudioRecording, PDQ.QualityIssue, "이슈를 가짐"),
        PDQ.violatesRule: (PDQ.QualityIssue, PDQ.QualityRule, "위반한 규칙"),
        PDQ.checksMetric: (PDQ.QualityRule, DQV.Metric, "보는 지표"),
    }
    for p, (dom, rng, label) in obj_props.items():
        g.add((p, RDF.type, OWL.ObjectProperty))
        g.add((p, RDFS.domain, dom))
        g.add((p, RDFS.range, rng))
        g.add((p, RDFS.label, Literal(label, lang="ko")))
    for p, label in [(PDQ["domain"], "도메인(source/target)"), (PDQ["split"], "분할(train/test)"),
                     (PDQ["label"], "정상/이상 라벨"), (PDQ.filePath, "파일 경로"),
                     (PDQ.verdict, "품질 판정"), (PDQ.severity, "심각도"),
                     (PDQ.message, "설명")]:
        g.add((p, RDF.type, OWL.DatatypeProperty))
        g.add((p, RDFS.label, Literal(label, lang="ko")))

    for dim, ko in DIMENSION_KO.items():
        d = PDQ[dim]
        g.add((d, RDF.type, DQV.Dimension))
        g.add((d, RDFS.label, Literal(ko, lang="ko")))
        g.add((d, RDFS.label, Literal(dim, lang="en")))

    for name, (label, dim) in {**METRICS, **EXTRA_METRICS}.items():
        m = PDQ[name]
        g.add((m, RDF.type, DQV.Metric))
        g.add((m, RDFS.label, Literal(label, lang="ko")))
        g.add((m, DQV.inDimension, PDQ[dim]))

    for rid, (name, metric, _dim) in RULES.items():
        r = PDQ[rid]
        g.add((r, RDF.type, PDQ.QualityRule))
        g.add((r, RDFS.label, Literal(name, lang="ko")))
        g.add((r, PDQ.checksMetric, PDQ[metric]))
    return g


def build_data_graph(metrics_df: pd.DataFrame, issues_df: pd.DataFrame) -> Graph:
    """파일별 지표와 이슈를 인스턴스(ABox)로 만든다."""
    g = Graph()
    for p, ns in [("sosa", SOSA), ("dqv", DQV), ("pdq", PDQ), ("data", DATA)]:
        g.bind(p, ns)

    obs_uri = {}
    for machine in metrics_df["machine"].unique():
        m = DATA[f"machine/{_slug(machine)}"]
        s = DATA[f"sensor/{_slug(machine)}_mic"]
        g.add((m, RDF.type, PDQ.Machine))
        g.add((m, RDFS.label, Literal(machine)))
        g.add((s, RDF.type, PDQ.Microphone))
        g.add((s, RDFS.label, Literal(f"{machine} 마이크")))
        g.add((s, SOSA.observes, m))

    for _, row in metrics_df.iterrows():
        o = DATA[f"obs/{_slug(row['file'])}"]
        obs_uri[row["file"]] = o
        mslug = _slug(row["machine"])
        g.add((o, RDF.type, PDQ.AudioRecording))
        g.add((o, SOSA.hasFeatureOfInterest, DATA[f"machine/{mslug}"]))
        g.add((o, SOSA.madeBySensor, DATA[f"sensor/{mslug}_mic"]))
        g.add((o, PDQ.filePath, Literal(row["file"])))
        g.add((o, PDQ.verdict, Literal(row["verdict"])))
        for col in ("domain", "split", "label"):
            if isinstance(row[col], str):
                g.add((o, PDQ[col], Literal(row[col])))
        for name in METRICS:
            mm = DATA[f"mm/{_slug(row['file'])}_{name}"]
            g.add((mm, RDF.type, DQV.QualityMeasurement))
            g.add((mm, DQV.computedOn, o))
            g.add((mm, DQV.isMeasurementOf, PDQ[name]))
            g.add((mm, DQV.value, Literal(float(row[name]), datatype=XSD.double)))

    for k, row in issues_df.reset_index(drop=True).iterrows():
        o = obs_uri[row["file"]]
        it = DATA[f"issue/{_slug(row['file'])}_{row['rule_id']}_{k}"]
        g.add((it, RDF.type, PDQ.QualityIssue))
        g.add((it, PDQ.violatesRule, PDQ[row["rule_id"]]))
        g.add((it, PDQ.severity, Literal(row["severity"])))
        g.add((it, PDQ.message, Literal(str(row["message"]))))
        g.add((o, PDQ.hasIssue, it))
    return g


PREFIXES = f"""
PREFIX rdfs: <{RDFS}>
PREFIX sosa: <{SOSA}>
PREFIX dqv:  <{DQV}>
PREFIX pdq:  <{PDQ}>
"""

# 온톨로지에 던지는 질문들 (Competency Questions)
QUERIES = {
    "Q1_verdict_by_machine": (
        "기기·도메인별로 파일 수와 FAIL/WARN 수는?",
        PREFIXES + """
SELECT ?machine ?domain (COUNT(?obs) AS ?files)
       (SUM(IF(?v = "FAIL", 1, 0)) AS ?fail) (SUM(IF(?v = "WARN", 1, 0)) AS ?warn)
WHERE {
  ?obs a pdq:AudioRecording ; sosa:hasFeatureOfInterest ?m ; pdq:verdict ?v .
  ?m rdfs:label ?machine .
  OPTIONAL { ?obs pdq:domain ?d }
  BIND(COALESCE(?d, "unknown") AS ?domain)
}
GROUP BY ?machine ?domain ORDER BY ?machine ?domain
"""),
    "Q2_issues_by_dimension": (
        "품질 차원(완전성/정확성/일관성/유일성)과 규칙별 이슈 수는? (규칙→지표→차원 관계를 따라감)",
        PREFIXES + """
SELECT ?dimension ?rule (COUNT(?issue) AS ?issues)
WHERE {
  ?obs pdq:hasIssue ?issue .
  ?issue pdq:violatesRule ?r .
  ?r rdfs:label ?rule ; pdq:checksMetric ?metric .
  ?metric dqv:inDimension ?dim .
  ?dim rdfs:label ?dimension .
  FILTER(lang(?dimension) = "ko")
}
GROUP BY ?dimension ?rule ORDER BY DESC(?issues)
"""),
    "Q3_clipping_over_threshold": (
        "클리핑 비율이 기준(0.001)을 넘는 녹음과 그 기계는?",
        PREFIXES + """
SELECT ?file ?machine ?clip_ratio
WHERE {
  ?mm dqv:isMeasurementOf pdq:clip_ratio ; dqv:computedOn ?obs ; dqv:value ?clip_ratio .
  FILTER(?clip_ratio > 0.001)
  ?obs pdq:filePath ?file ; sosa:hasFeatureOfInterest ?m .
  ?m rdfs:label ?machine .
}
ORDER BY DESC(?clip_ratio) LIMIT 20
"""),
    "Q4_fail_trace": (
        "FAIL 판정을 받은 파일과 그 근거(규칙, 측정 설명)는? (추적성)",
        PREFIXES + """
SELECT ?file ?machine ?rule ?message
WHERE {
  ?obs pdq:hasIssue ?issue ; pdq:filePath ?file ; sosa:hasFeatureOfInterest ?m .
  ?m rdfs:label ?machine .
  ?issue pdq:severity "FAIL" ; pdq:violatesRule ?r ; pdq:message ?message .
  ?r rdfs:label ?rule .
}
ORDER BY ?machine ?file LIMIT 30
"""),
}


def run_queries(g: Graph) -> dict[str, pd.DataFrame]:
    out = {}
    for qid, (_desc, q) in QUERIES.items():
        res = g.query(q)
        cols = [str(v) for v in res.vars]
        rows = [[None if v is None else v.toPython() for v in r] for r in res]
        out[qid] = pd.DataFrame(rows, columns=cols)
    return out
