"""5단계: LLM이 품질 점검 보고서 초안을 쓰고, 코드가 숫자를 대조한다.

LLM 선택: --provider anthropic|openai|ollama|manual|template|auto (기본 auto)
  auto 는 API 키 -> 내 PC의 Ollama 순서로 찾고, 없으면 템플릿 보고서.

사용:  python scripts/05_llm_report.py --results results
       python scripts/05_llm_report.py --provider manual   (Claude 채팅 붙여넣기)
결과:  results/quality_report.md, results/report_summary.json
"""
import argparse
import json
from datetime import date
from pathlib import Path

import pandas as pd
from _common import ROOT  # noqa: F401

from pdq.llm_client import ManualPending, pick_provider
from pdq.llm_report import build_summary, write_report
from pdq.rules import load_thresholds


def a_provider(args):
    return "template" if args.provider == "template" else args.provider


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--results", default="results")
    ap.add_argument("--config", default=None)
    ap.add_argument("--provider", default=None)
    args = ap.parse_args()
    res = Path(args.results)

    metrics = pd.read_csv(res / "metrics.csv")
    issues = pd.read_csv(res / "issues.csv")
    q = json.loads((res / "ontology_queries.json").read_text(encoding="utf-8"))
    qdf = {k: pd.DataFrame(v) for k, v in q.items()}
    summary = build_summary(metrics, issues, qdf, load_thresholds(args.config))
    (res / "report_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=1),
                                            encoding="utf-8")

    try:
        body, provider, unknown = write_report(summary, pick_provider(a_provider(args)))
    except ManualPending as e:
        print(e)
        return
    check = ("- 보고서의 모든 숫자가 요약 데이터와 일치함" if not unknown else
             "- 요약 데이터에 없는 숫자 (사람이 확인 필요): " + ", ".join(unknown))
    report = "\n".join([
        "# 물리 데이터 품질 점검 보고서 (초안)", "",
        f"- 작성일: {date.today().isoformat()}",
        f"- 작성 방식: {provider} (판정은 규칙 기반 코드, 문장은 {'LLM' if provider != 'template' else '템플릿'})",
        "- 상태: 초안 - 담당 연구원 검토·승인 필요", "", body, "",
        "## 부록. 숫자 자동 대조 결과", check, ""])
    (res / "quality_report.md").write_text(report, encoding="utf-8")
    print(report)
    print(f"\n저장: {res}/quality_report.md")


if __name__ == "__main__":
    main()
