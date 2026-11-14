"""LLM으로 품질 점검 보고서 초안을 쓰고, 숫자를 원본과 대조한다.

원칙: 숫자 계산과 판정은 코드가 이미 끝냈다. LLM은 요약(JSON)만 받아 글로 정리한다.
- 원본 오디오는 LLM에 보내지 않는다(보안).
- LLM 출력의 숫자를 모두 뽑아 요약 JSON에 있는 숫자인지 코드로 확인한다(환각 방지).
- API 키가 없으면 템플릿 보고서를 만든다(실습이 끝까지 돌도록).
"""
from __future__ import annotations

import json
import os
import re

SYSTEM_PROMPT = """당신은 공인 시험기관에서 AI 학습용 물리 데이터(기기 소리)의 품질 점검 보고서 초안을 쓰는 보조자입니다.
규칙:
1. 아래 JSON에 있는 숫자만 쓰십시오. 계산이 필요한 새 숫자(합계, 비율 등)는 만들지 마십시오.
2. PASS/WARN/FAIL 판정을 바꾸거나 새로 판정하지 마십시오. 판정은 이미 규칙 기반 코드가 했습니다.
3. 원인은 반드시 '추정'이라고 표시하십시오.
4. 다음 목차를 그대로 쓰십시오: ## 1. 점검 개요 / ## 2. 주요 발견 / ## 3. 원인 추정 / ## 4. 조치 권고 / ## 5. 한계와 다음 단계
5. 한국어로, 시험 보고서 문체(~함, ~임)로 간결하게 쓰십시오.
6. outlier_warnings.on_anomaly_labeled_files 가 0보다 크면, 통계적 이상치 경고가 데이터 결함이 아니라 실제 고장음(이상 라벨)일 수 있다는 점을 '한계'에 적으십시오."""


def build_summary(metrics_df, issues_df, query_results: dict, cfg: dict) -> dict:
    """LLM에 넘길 요약. 여기 있는 숫자만 보고서에 쓸 수 있다."""
    verdict_counts = metrics_df["verdict"].value_counts().to_dict()
    by_rule = (issues_df.groupby(["rule_id", "rule_name", "severity"]).size()
               .reset_index(name="count").to_dict("records")) if len(issues_df) else []
    examples = []
    if len(issues_df):
        ex = issues_df.sort_values("severity").drop_duplicates("rule_id").head(10)
        for _, r in ex.iterrows():
            examples.append({"file": os.path.basename(r["file"]), "machine": r["machine"],
                             "rule": r["rule_name"], "severity": r["severity"],
                             "message": r["message"]})

    def _records(df, n=15):
        return json.loads(df.head(n).to_json(orient="records", force_ascii=False))

    # 통계적 이상치 경고 중 '이상(anomaly)' 라벨 파일에 걸린 것: 데이터 결함이 아니라 진짜 고장음일 수 있음
    lab = dict(zip(metrics_df["file"], metrics_df["label"]))
    out_iss = issues_df[issues_df["rule_id"] == "R11_OUTLIER"] if len(issues_df) else issues_df
    on_anom = int(sum(lab.get(f) == "anomaly" for f in out_iss["file"])) if len(out_iss) else 0

    return {
        "outlier_warnings": {"total": int(len(out_iss)), "on_anomaly_labeled_files": on_anom},
        "dataset": {
            "total_files": int(len(metrics_df)),
            "machines": sorted(metrics_df["machine"].unique().tolist()),
            "sample_rates_hz": sorted(int(s) for s in metrics_df["sample_rate"].unique()),
            "verdict_counts": {k: int(v) for k, v in verdict_counts.items()},
        },
        "thresholds": cfg,
        "issues_by_rule": by_rule,
        "issue_examples": examples,
        "ontology_query_results": {
            "verdict_by_machine": _records(query_results["Q1_verdict_by_machine"], 30),
            "issues_by_dimension": _records(query_results["Q2_issues_by_dimension"], 30),
        },
    }


def _call_anthropic(prompt: str) -> str:
    import anthropic

    client = anthropic.Anthropic()
    model = os.environ.get("PDQ_LLM_MODEL", "claude-sonnet-5-5")
    msg = client.messages.create(model=model, max_tokens=2000, system=SYSTEM_PROMPT,
                                 messages=[{"role": "user", "content": prompt}])
    return "".join(b.text for b in msg.content if getattr(b, "type", "") == "text")


def _call_openai(prompt: str) -> str:
    from openai import OpenAI

    client = OpenAI()
    model = os.environ.get("PDQ_LLM_MODEL", "gpt-4o-mini")
    r = client.chat.completions.create(model=model, messages=[
        {"role": "system", "content": SYSTEM_PROMPT}, {"role": "user", "content": prompt}])
    return r.choices[0].message.content


def pick_provider() -> str:
    p = os.environ.get("PDQ_LLM_PROVIDER", "auto").lower()
    if p != "auto":
        return p
    if os.environ.get("ANTHROPIC_API_KEY"):
        return "anthropic"
    if os.environ.get("OPENAI_API_KEY"):
        return "openai"
    return "template"


def template_report(s: dict) -> str:
    """LLM 없이 만드는 보고서(같은 목차)."""
    d = s["dataset"]
    vc = d["verdict_counts"]
    lines = ["## 1. 점검 개요",
             f"- 대상: {d['total_files']}개 파일, 기기 {len(d['machines'])}종 ({', '.join(d['machines'])})",
             f"- 샘플링레이트: {', '.join(str(x) for x in d['sample_rates_hz'])} Hz",
             f"- 판정: PASS {vc.get('PASS', 0)}, WARN {vc.get('WARN', 0)}, FAIL {vc.get('FAIL', 0)}",
             "", "## 2. 주요 발견"]
    for r in s["issues_by_rule"]:
        lines.append(f"- {r['rule_name']} ({r['severity']}): {r['count']}건")
    if not s["issues_by_rule"]:
        lines.append("- 규칙 위반 없음")
    lines += ["", "## 3. 원인 추정"]
    for e in s["issue_examples"]:
        lines.append(f"- {e['file']} ({e['machine']}): {e['rule']} - {e['message']} (원인은 수집 장비·저장 과정 확인 필요)")
    lines += ["", "## 4. 조치 권고",
              "- FAIL 파일은 학습 데이터에서 제외하고 원천 기관에 재수집을 요청함",
              "- WARN 파일은 담당 연구원이 청취·파형 확인 후 사용 여부를 결정함",
              "", "## 5. 한계와 다음 단계",
              "- 기준값은 예시값이며 센서·용도별로 전문가 검토가 필요함",
              "- 추정 SNR은 비교용 지표로 절대값이 아님",
              f"- 통계적 이상치 경고 {s['outlier_warnings']['total']}건 중 "
              f"{s['outlier_warnings']['on_anomaly_labeled_files']}건은 '이상(anomaly)' 라벨 파일임. "
              "데이터 결함이 아니라 실제 고장음일 수 있으므로 제외하지 말고 사람이 구분해야 함"]
    return "\n".join(lines)


NUM_RE = re.compile(r"(?<![A-Za-z_])-?\d[\d,]*(?:\.\d+)?%?")


def _collect_numbers(obj, out: set):
    if isinstance(obj, bool):
        return
    if isinstance(obj, (int, float)):
        out.add(float(obj))
    elif isinstance(obj, str):
        for t in NUM_RE.findall(obj):
            try:
                out.add(float(t.rstrip("%").replace(",", "")))
            except ValueError:
                pass
    elif isinstance(obj, dict):
        for k, v in obj.items():
            _collect_numbers(k, out)
            _collect_numbers(v, out)
    elif isinstance(obj, (list, tuple)):
        for v in obj:
            _collect_numbers(v, out)


def check_numbers(report: str, summary: dict) -> list[str]:
    """보고서의 숫자 중 요약 JSON에 없는 것을 돌려준다(= 확인 필요)."""
    allowed: set[float] = set()
    _collect_numbers(summary, allowed)
    allowed |= {a * 100 for a in list(allowed)}  # 0.25 -> 25% 허용
    unknown = []
    for line in report.splitlines():
        if line.lstrip().startswith("#"):
            continue  # 목차 번호는 제외
        line = re.sub(r"^\s*\d+\.\s", "", line)  # 번호 목록 표시 제외
        line = re.sub(r"R\d+_[A-Z_]+", "", line)  # 규칙 코드 제외
        for tok in NUM_RE.findall(line):
            raw = tok.rstrip("%").replace(",", "")
            try:
                val = float(raw)
            except ValueError:
                continue
            dec = len(raw.split(".")[1]) if "." in raw else 0
            tol = 0.5 * 10 ** (-dec) + 1e-9
            if not any(abs(val - a) <= tol for a in allowed):
                unknown.append(tok)
    return sorted(set(unknown))


def write_report(summary: dict) -> tuple[str, str, list[str]]:
    provider = pick_provider()
    prompt = ("다음은 규칙 기반 품질 점검과 온톨로지 질의 결과(JSON)입니다. "
              "이 내용만으로 품질 점검 보고서 초안을 작성하십시오.\n\n"
              + json.dumps(summary, ensure_ascii=False, indent=1))
    if provider == "anthropic":
        body = _call_anthropic(prompt)
    elif provider == "openai":
        body = _call_openai(prompt)
    else:
        body = template_report(summary)
    return body, provider, check_numbers(body, summary)
