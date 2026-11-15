"""LLM 기능 ②: 사람이 말로 한 질문 -> LLM 이 SPARQL 로 번역 -> 온톨로지에서 실행 -> (선택) 문장 답.

핵심: 답(숫자)은 LLM 이 아니라 온톨로지가 낸다. LLM 은 '질문을 질의문으로 번역'만 한다.
검증: 질문마다 사람이 만든 정답 질의(gold)를 두고, LLM 질의의 실행 결과가 같은지 코드로 비교한다.
"""
from __future__ import annotations

import re
from collections import Counter

from rdflib import Graph

from .ontology import PREFIXES

SCHEMA_CARD = PREFIXES + """
# ---- 온톨로지 구조 (이 이름들만 쓰십시오) ----
# 클래스
#   pdq:AudioRecording  녹음 파일 1개 (sosa:Observation 의 하위 클래스)
#   pdq:Machine         기계 (rdfs:label 값: "fan", "pump", "valve" - 언어 태그 없음)
#   pdq:Microphone      마이크 센서
#   pdq:QualityIssue    품질 문제 기록 1건
#   pdq:QualityRule     품질 규칙 (rdfs:label 예: "클리핑"@ko, "끊김/정지 구간"@ko)
#   dqv:QualityMeasurement 측정값 1개,  dqv:Metric 지표,  dqv:Dimension 품질 차원
# 녹음 파일(?obs)의 속성
#   ?obs sosa:hasFeatureOfInterest ?machine     (녹음한 기계)
#   ?obs sosa:madeBySensor ?sensor
#   ?obs pdq:filePath "data/demo/fan/train/section_00_source_train_normal_0003_demo.wav"
#        (경로 구분자는 / 또는 \\ 일 수 있으니 CONTAINS 로 찾으십시오)
#   ?obs pdq:verdict  "PASS" | "WARN" | "FAIL"
#   ?obs pdq:label    "normal" | "anomaly"      (정상음/이상음 라벨)
#   ?obs pdq:domain   "source" | "target"
#   ?obs pdq:split    "train" | "test"
#   ?obs pdq:hasIssue ?issue
# 문제 기록(?issue)의 속성
#   ?issue pdq:violatesRule ?rule ;  pdq:severity "WARN" | "FAIL" ;  pdq:message "0.6157 > 0.01"
# 규칙(?rule)의 속성
#   ?rule rdfs:label ?name ;  pdq:checksMetric ?metric
#   규칙 IRI: pdq:R01_NAN pdq:R02_SAMPLE_RATE pdq:R03_CHANNELS pdq:R04_DURATION pdq:R05_CLIPPING
#            pdq:R06_DC_OFFSET pdq:R07_DROPOUT pdq:R08_SILENCE pdq:R09_METADATA pdq:R10_DUPLICATE pdq:R11_OUTLIER
# 지표(?metric)와 품질 차원
#   ?metric dqv:inDimension ?dim .  품질 차원 IRI: pdq:Accuracy(정확성) pdq:Completeness(완전성)
#                                    pdq:Consistency(일관성) pdq:Uniqueness(유일성)
#   ?dim rdfs:label 은 "정확성"@ko 와 "Accuracy"@en 두 개가 있음
#   지표 IRI: pdq:sample_rate pdq:duration_s pdq:clip_ratio pdq:dc_offset pdq:longest_flat_ms
#            pdq:silence_ratio pdq:rms_dbfs pdq:snr_est_db pdq:spectral_flatness
# 측정값(?mm)
#   ?mm dqv:computedOn ?obs ; dqv:isMeasurementOf pdq:clip_ratio ; dqv:value 0.0002 (실수)
"""

SYSTEM_PROMPT = """당신은 물리 데이터 품질 온톨로지에 대한 질문을 SPARQL 1.1 SELECT 질의로 번역하는 보조자입니다.
규칙:
1. 아래 '온톨로지 구조'에 있는 PREFIX, 클래스, 속성 이름만 쓰십시오. 없는 이름을 지어내지 마십시오.
2. PREFIX 선언을 질의 맨 위에 모두 포함하십시오.
3. SELECT 질의만 쓰십시오 (INSERT, DELETE 등 데이터 변경 금지).
4. 질문이 묻는 값만 SELECT 하십시오. 개수를 물으면 COUNT 하나만, 목록을 물으면 그 목록만.
5. 답은 ```sparql 코드블록 하나로만 쓰십시오. 설명은 쓰지 마십시오.

[온톨로지 구조]
""" + SCHEMA_CARD + """
[예시]
질문: valve 기계의 녹음 파일은 몇 개인가?
```sparql
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
PREFIX sosa: <http://www.w3.org/ns/sosa/>
PREFIX pdq:  <https://github.com/qripapa01/physical-data-quality-lab/ontology#>
SELECT (COUNT(?obs) AS ?n) WHERE {
  ?obs a pdq:AudioRecording ; sosa:hasFeatureOfInterest ?m .
  ?m rdfs:label "valve" .
}
```"""

ANSWER_PROMPT = """당신은 품질 담당자에게 결과를 설명하는 보조자입니다.
질문과 질의 실행 결과(JSON 표)를 보고 한국어 1~2문장으로 답하십시오.
결과 표에 있는 숫자와 이름만 쓰고, 새로운 숫자(합계·비율 등)는 만들지 마십시오."""

FORBIDDEN = re.compile(r"\b(INSERT|DELETE|LOAD|CLEAR|DROP|CREATE|ADD|MOVE|COPY|SERVICE)\b", re.I)


def is_safe(q: str) -> tuple[bool, str]:
    if FORBIDDEN.search(q):
        return False, "데이터 변경·외부 접속 구문이 있어 실행하지 않음"
    if not re.search(r"\b(SELECT|ASK)\b", q, re.I):
        return False, "SELECT 질의가 아님"
    return True, ""


def _norm(v):
    if v is None:
        return "None"
    try:
        f = float(v)
        return f"{f:.6g}"
    except (TypeError, ValueError):
        return str(v).replace("\\", "/")


def run(g: Graph, q: str):
    """질의를 실행해 (행 목록, 오류)를 돌려준다."""
    ok, why = is_safe(q)
    if not ok:
        return None, why
    try:
        res = g.query(q)
        return [[None if v is None else v.toPython() for v in row] for row in res], ""
    except Exception as e:  # 문법 오류, 없는 접두어 등
        return None, f"실행 오류: {str(e).splitlines()[0][:120]}"


def same_result(pred_rows, gold_rows) -> bool:
    """두 결과가 같은지. 열 순서·이름은 무시하고, LLM 쪽에 설명용 열이 더 있어도 허용."""
    if pred_rows is None:
        return False

    def dedup(rows):  # 같은 행이 여러 번 나와도 한 번으로 본다
        seen, out = set(), []
        for r in rows:
            key = tuple(sorted(_norm(v) for v in r))
            if key not in seen:
                seen.add(key)
                out.append(r)
        return out

    pred_rows, gold_rows = dedup(pred_rows), dedup(gold_rows)
    if len(pred_rows) != len(gold_rows):
        return False
    p = [Counter(_norm(v) for v in r) for r in pred_rows]
    gset = [Counter(_norm(v) for v in r) for r in gold_rows]
    if sorted(map(sorted, map(Counter.elements, p))) == sorted(map(sorted, map(Counter.elements, gset))):
        return True
    used = [False] * len(p)  # 느슨한 비교: gold 행의 값이 모두 들어 있는 LLM 행이 하나씩 있으면 정답
    for gr in gset:
        for i, pr in enumerate(p):
            if not used[i] and not (gr - pr):
                used[i] = True
                break
        else:
            return False
    return True
