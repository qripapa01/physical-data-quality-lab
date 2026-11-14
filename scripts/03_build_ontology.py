"""3단계: 점검 결과를 온톨로지(지식그래프, RDF/Turtle)로 만든다.

사용:  python scripts/03_build_ontology.py --results results
결과:  ontology/pdq_schema.ttl  (클래스·관계·규칙 정의. Protégé로 열어 볼 수 있음)
       results/quality_graph.ttl (스키마 + 파일별 측정값 + 이슈)
"""
import argparse
from pathlib import Path

import pandas as pd
from _common import ROOT

from pdq.ontology import build_data_graph, build_schema


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--results", default="results")
    args = ap.parse_args()
    res = Path(args.results)

    metrics = pd.read_csv(res / "metrics.csv")
    issues = pd.read_csv(res / "issues.csv")

    schema = build_schema()
    (ROOT / "ontology").mkdir(exist_ok=True)
    schema.serialize(ROOT / "ontology" / "pdq_schema.ttl", format="turtle")

    data = build_data_graph(metrics, issues)
    g = schema + data
    for p, ns in schema.namespaces():
        g.bind(p, ns)
    for p, ns in data.namespaces():
        g.bind(p, ns)
    g.serialize(res / "quality_graph.ttl", format="turtle")
    print(f"스키마 트리플 {len(schema)}개 -> ontology/pdq_schema.ttl")
    print(f"전체 트리플 {len(g)}개 (녹음 {len(metrics)}개, 이슈 {len(issues)}개) -> {res}/quality_graph.ttl")


if __name__ == "__main__":
    main()
