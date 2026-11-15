"""LLM 기능 ①: 기업마다 제각각인 데이터 설명서 -> 표준 메타데이터 -> 온톨로지.

흐름
  설명서(글) --LLM--> JSON(표준 항목) --코드--> 형식 검사 --코드--> 실제 데이터와 대조 --> 온톨로지에 기록

LLM 은 '글을 읽고 정리'만 한다. 맞는지 틀린지는 코드(형식 검사·대조)와 사람(정답표)이 판단한다.
비교용으로 LLM 없이 키워드·정규식만 쓰는 추출기(baseline)도 둔다.
"""
from __future__ import annotations

import re

from rdflib import RDF, RDFS, OWL, XSD, Graph, Literal, Namespace

from .ontology import DATA, DQV, PDQ, SOSA

DCAT = Namespace("http://www.w3.org/ns/dcat#")

MACHINE_TYPES = ["fan", "pump", "valve", "motor", "gearbox", "bearing", "compressor",
                 "conveyor", "other"]
SENSOR_TYPES = ["microphone", "accelerometer", "current", "temperature", "other"]
FIELDS = ["machine_type", "sensor_type", "sample_rate_hz", "channels", "duration_s",
          "file_count", "location"]
SCORED = FIELDS[:-1]  # location 은 표현이 다양해 채점에서 뺀다

SYSTEM_PROMPT = f"""당신은 공인 시험기관에서 기업이 제출한 물리 데이터(소리·진동·전류·온도) 설명서를 읽고,
메타데이터를 표준 항목으로 정리하는 보조자입니다.
규칙:
1. 설명서에 적힌 내용만 쓰십시오. 적혀 있지 않거나 '미정'이면 null 로 쓰십시오. 추측하지 마십시오.
2. 단위 변환은 하십시오: kHz -> Hz (예: 16kHz -> 16000, 48k -> 48000, 44.1kHz -> 44100),
   분·시간 -> 초, 샘플링 '주기'는 주파수로 (예: 0.1ms -> 10000).
3. machine_type 은 {MACHINE_TYPES} 중 하나 (목록에 없으면 "other").
4. sensor_type 은 {SENSOR_TYPES} 중 하나 (마이크·마이크로폰 -> microphone, 가속도계·진동센서 -> accelerometer,
   CT·홀센서 등 전류 측정 -> current, 열전대 등 -> temperature).
5. '약 200개'처럼 대략의 수는 그 숫자(200)로 쓰십시오.
6. 다음 키만 가진 JSON 객체 하나로만 답하십시오(설명 금지):
   machine_type(문자열), sensor_type(문자열), sample_rate_hz(정수), channels(정수),
   duration_s(숫자, 파일 하나의 길이), file_count(정수), location(문자열)"""


def user_prompt(doc_text: str) -> str:
    return "다음 설명서에서 메타데이터를 뽑으십시오.\n\n<설명서>\n" + doc_text.strip() + "\n</설명서>"


# ------------------------------------------------------------- 비교용: LLM 없는 추출기
_MACHINE_KW = {"fan": ["팬", "fan", "송풍"], "pump": ["펌프", "pump"], "valve": ["밸브", "valve"],
               "motor": ["모터", "motor"], "gearbox": ["기어", "gear"], "bearing": ["베어링", "bearing"],
               "compressor": ["컴프레서", "압축기", "compressor"], "conveyor": ["컨베이어", "conveyor"]}
_SENSOR_KW = {"microphone": ["마이크", "mic"], "accelerometer": ["가속도", "accelerometer", "acc"],
              "current": ["전류", "current", "ct("], "temperature": ["온도", "열전대", "thermo"]}


def baseline_extract(text: str) -> dict:
    """키워드와 정규식만으로 뽑는다. 표현이 조금만 달라도 놓친다(LLM과 비교용)."""
    t = text.lower()
    out = {k: None for k in FIELDS}
    for mt, kws in _MACHINE_KW.items():
        if any(k in t for k in kws):
            out["machine_type"] = mt
            break
    for st, kws in _SENSOR_KW.items():
        if any(k in t for k in kws):
            out["sensor_type"] = st
            break
    m = re.search(r"(\d+(?:\.\d+)?)\s*khz", t)
    if m:
        out["sample_rate_hz"] = int(round(float(m.group(1)) * 1000))
    else:
        m = re.search(r"(\d+)\s*hz", t)
        if m:
            out["sample_rate_hz"] = int(m.group(1))
    m = re.search(r"(\d+)\s*(?:ch|채널)", t)
    out["channels"] = int(m.group(1)) if m else (1 if ("mono" in t or "모노" in t) else None)
    m = re.search(r"(\d+(?:\.\d+)?)\s*(?:초|sec|s\b)", t)
    out["duration_s"] = float(m.group(1)) if m else None
    m = re.search(r"(\d[\d,]*)\s*(?:개|files|wav)", t)
    out["file_count"] = int(m.group(1).replace(",", "")) if m else None
    return out


# ------------------------------------------------------------- 코드 검사
def validate(rec: dict) -> list[str]:
    """LLM 이 낸 JSON 의 형식을 코드로 검사한다. 문제 목록을 돌려준다."""
    errs = []
    if not isinstance(rec, dict):
        return ["JSON 객체가 아님"]
    for k in FIELDS:
        if k not in rec:
            errs.append(f"{k} 항목 없음")
    if rec.get("machine_type") not in MACHINE_TYPES:
        errs.append(f"machine_type 값 '{rec.get('machine_type')}' 은 허용 목록에 없음")
    if rec.get("sensor_type") not in SENSOR_TYPES:
        errs.append(f"sensor_type 값 '{rec.get('sensor_type')}' 은 허용 목록에 없음")
    sr = rec.get("sample_rate_hz")
    if not (isinstance(sr, (int, float)) and 0 < sr <= 1_000_000):
        errs.append(f"sample_rate_hz 값 {sr} 이 범위(1~1,000,000)를 벗어나거나 없음")
    ch = rec.get("channels")
    if ch is not None and not (isinstance(ch, int) and 1 <= ch <= 64):
        errs.append(f"channels 값 {ch} 이상")
    for k in ("duration_s", "file_count"):
        v = rec.get(k)
        if v is not None and not (isinstance(v, (int, float)) and v > 0):
            errs.append(f"{k} 값 {v} 이상")
    return errs


def _same(a, b) -> bool:
    if a is None or b is None:
        return a is None and b is None
    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
        return abs(a - b) <= 0.01 * max(abs(b), 1e-9)
    return str(a).strip().lower() == str(b).strip().lower()


def score(pred: dict, truth: dict) -> dict:
    """항목별 정답 여부 {field: True/False}."""
    return {k: _same((pred or {}).get(k), truth.get(k)) for k in SCORED}


def cross_check(rec: dict, metrics_df, machine: str) -> list[str]:
    """설명서 내용과 실제 측정값(metrics.csv)이 맞는지 코드로 대조한다."""
    sub = metrics_df[metrics_df["machine"] == machine]
    notes = []
    if not len(sub):
        return [f"실제 데이터에 '{machine}' 없음"]
    sr = rec.get("sample_rate_hz")
    if sr:
        diff = sub[sub["sample_rate"] != sr]
        if len(diff):
            notes.append(f"설명서는 {sr}Hz 인데 실제 {len(diff)}개 파일은 다름 "
                         f"({', '.join(sorted({str(int(x)) for x in diff['sample_rate']}))}Hz)")
    fc = rec.get("file_count")
    if fc and fc != len(sub):
        notes.append(f"설명서는 {fc}개 인데 실제 {len(sub)}개")
    du = rec.get("duration_s")
    if du:
        off = sub[(sub["duration_s"] - du).abs() > 0.05 * du]
        if len(off):
            notes.append(f"설명서는 {du}초 인데 실제 {len(off)}개 파일 길이가 다름")
    ch = rec.get("channels")
    if ch and "channels" in sub and (sub["channels"] != ch).any():
        notes.append(f"설명서는 {ch}채널 인데 실제와 다름")
    return notes


# ------------------------------------------------------------- 온톨로지 확장
CLASS_OF_MACHINE = {"fan": "Fan", "pump": "Pump", "valve": "Valve", "motor": "Motor",
                    "gearbox": "Gearbox", "bearing": "Bearing", "compressor": "Compressor",
                    "conveyor": "Conveyor", "other": "OtherMachine"}
ROTATING = {"Fan", "Pump", "Motor", "Gearbox", "Bearing", "Compressor"}
CLASS_OF_SENSOR = {"microphone": "Microphone", "accelerometer": "Accelerometer",
                   "current": "CurrentSensor", "temperature": "TemperatureSensor",
                   "other": "OtherSensor"}
PROPERTY_OF_SENSOR = {"microphone": "sound", "accelerometer": "vibration",
                      "current": "electricCurrent", "temperature": "temperature", "other": None}


def build_extension_schema() -> Graph:
    """온톨로지 v0.2 확장: 기계·센서 종류 계층, 관측 속성, 데이터셋."""
    g = Graph()
    for p, ns in [("sosa", SOSA), ("dqv", DQV), ("pdq", PDQ), ("owl", OWL), ("dcat", DCAT)]:
        g.bind(p, ns)

    def cls(c, parent, ko):
        g.add((PDQ[c], RDF.type, OWL.Class))
        g.add((PDQ[c], RDFS.subClassOf, parent))
        g.add((PDQ[c], RDFS.label, Literal(ko, lang="ko")))

    cls("Dataset", DCAT.Dataset, "데이터셋(기업 제출 단위)")
    cls("RotatingMachine", PDQ.Machine, "회전 기계")
    ko_m = {"Fan": "팬", "Pump": "펌프", "Valve": "밸브", "Motor": "모터", "Gearbox": "기어박스",
            "Bearing": "베어링", "Compressor": "컴프레서", "Conveyor": "컨베이어", "OtherMachine": "기타 기계"}
    for c, ko in ko_m.items():
        cls(c, PDQ.RotatingMachine if c in ROTATING else PDQ.Machine, ko)
    ko_s = {"Accelerometer": "가속도계", "CurrentSensor": "전류 센서",
            "TemperatureSensor": "온도 센서", "OtherSensor": "기타 센서"}
    for c, ko in ko_s.items():
        cls(c, SOSA.Sensor, ko)
    for p, ko in {"vibration": "진동", "electricCurrent": "전류", "temperature": "온도"}.items():
        g.add((PDQ[p], RDF.type, SOSA.ObservableProperty))
        g.add((PDQ[p], RDFS.label, Literal(ko, lang="ko")))
    for p, (dom, rng, ko) in {"aboutMachine": (PDQ.Dataset, PDQ.Machine, "대상 기계"),
                              "usesSensor": (PDQ.Dataset, SOSA.Sensor, "사용 센서")}.items():
        g.add((PDQ[p], RDF.type, OWL.ObjectProperty))
        g.add((PDQ[p], RDFS.domain, dom))
        g.add((PDQ[p], RDFS.range, rng))
        g.add((PDQ[p], RDFS.label, Literal(ko, lang="ko")))
    for p, ko in {"sampleRateHz": "샘플링레이트(Hz)", "channelCount": "채널 수",
                  "clipDurationS": "파일 길이(초)", "fileCount": "파일 수", "location": "수집 장소",
                  "sourceDocument": "원본 설명서", "extractedBy": "추출 방식(LLM/규칙)",
                  "crossCheckNote": "실제 데이터 대조 결과"}.items():
        g.add((PDQ[p], RDF.type, OWL.DatatypeProperty))
        g.add((PDQ[p], RDFS.label, Literal(ko, lang="ko")))
    return g


def records_to_graph(records: dict, extracted_by: str, notes: dict | None = None) -> Graph:
    """추출 결과(문서ID -> 메타데이터)를 인스턴스로 만든다."""
    g = Graph()
    for p, ns in [("sosa", SOSA), ("pdq", PDQ), ("data", DATA)]:
        g.bind(p, ns)
    for doc_id, r in records.items():
        if not isinstance(r, dict) or validate(r):
            continue  # 형식 검사를 통과한 것만 온톨로지에 넣는다
        ds, mc, sn = DATA[f"dataset/{doc_id}"], DATA[f"machine/{doc_id}"], DATA[f"sensor/{doc_id}"]
        g.add((ds, RDF.type, PDQ.Dataset))
        g.add((ds, PDQ.sourceDocument, Literal(f"{doc_id}.txt")))
        g.add((ds, PDQ.extractedBy, Literal(extracted_by)))
        g.add((ds, PDQ.aboutMachine, mc))
        g.add((ds, PDQ.usesSensor, sn))
        g.add((mc, RDF.type, PDQ[CLASS_OF_MACHINE[r["machine_type"]]]))
        g.add((mc, RDFS.label, Literal(f"{doc_id} {r['machine_type']}")))
        g.add((sn, RDF.type, PDQ[CLASS_OF_SENSOR[r["sensor_type"]]]))
        g.add((sn, PDQ.monitors, mc))
        prop = PROPERTY_OF_SENSOR[r["sensor_type"]]
        if prop:
            g.add((sn, SOSA.observes, PDQ[prop]))
        g.add((sn, PDQ.sampleRateHz, Literal(int(r["sample_rate_hz"]), datatype=XSD.integer)))
        if r.get("channels"):
            g.add((sn, PDQ.channelCount, Literal(int(r["channels"]), datatype=XSD.integer)))
        if r.get("duration_s"):
            g.add((ds, PDQ.clipDurationS, Literal(float(r["duration_s"]), datatype=XSD.double)))
        if r.get("file_count"):
            g.add((ds, PDQ.fileCount, Literal(int(r["file_count"]), datatype=XSD.integer)))
        if r.get("location"):
            g.add((ds, PDQ.location, Literal(str(r["location"]))))
        for n in (notes or {}).get(doc_id, []):
            g.add((ds, PDQ.crossCheckNote, Literal(n)))
    return g


EXT_PREFIXES = f"""
PREFIX rdf:  <{RDF}>
PREFIX rdfs: <{RDFS}>
PREFIX sosa: <{SOSA}>
PREFIX pdq:  <{PDQ}>
"""

EXT_QUERIES = {
    "E1_rotating_machines": (
        "회전 기계(팬·펌프·모터 등)에 해당하는 데이터셋은? (클래스 계층을 따라감: subClassOf*)",
        EXT_PREFIXES + """
SELECT ?dataset ?machineClass WHERE {
  ?ds a pdq:Dataset ; pdq:sourceDocument ?dataset ; pdq:aboutMachine ?m .
  ?m a ?c . ?c rdfs:subClassOf* pdq:RotatingMachine ; rdfs:label ?machineClass .
  FILTER(lang(?machineClass) = "ko")
} ORDER BY ?dataset"""),
    "E2_vibration_datasets": (
        "진동을 관측하는 센서를 쓴 데이터셋과 샘플링레이트는?",
        EXT_PREFIXES + """
SELECT ?dataset ?sampleRateHz WHERE {
  ?ds pdq:sourceDocument ?dataset ; pdq:usesSensor ?s .
  ?s sosa:observes pdq:vibration ; pdq:sampleRateHz ?sampleRateHz .
} ORDER BY DESC(?sampleRateHz)"""),
    "E3_low_rate": (
        "샘플링레이트가 10kHz 미만인 데이터셋과 센서 종류는? (저속 신호 확인)",
        EXT_PREFIXES + """
SELECT ?dataset ?sensorClass ?sampleRateHz WHERE {
  ?ds pdq:sourceDocument ?dataset ; pdq:usesSensor ?s .
  ?s pdq:sampleRateHz ?sampleRateHz ; a ?c . ?c rdfs:subClassOf sosa:Sensor ; rdfs:label ?sensorClass .
  FILTER(?sampleRateHz < 10000 && lang(?sensorClass) = "ko")
} ORDER BY ?sampleRateHz"""),
    "E4_mismatch": (
        "설명서와 실제 데이터가 맞지 않는 데이터셋은?",
        EXT_PREFIXES + """
SELECT ?dataset ?note WHERE {
  ?ds pdq:sourceDocument ?dataset ; pdq:crossCheckNote ?note .
} ORDER BY ?dataset"""),
}
