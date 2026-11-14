"""4단계: 온톨로지에 SPARQL로 질문한다 (Competency Questions).

사용:  python scripts/04_query_ontology.py --results results
결과:  results/ontology_queries.md, results/ontology_queries.json
"""
import argparse
import json
from pathlib import Path

from _common import ROOT  # noqa: F401  (import 경로 설정)
from rdflib import Graph

from pdq.ontology import QUERIES, run_queries


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--results", default="results")
    args = ap.parse_args()
    res = Path(args.results)

    g = Graph()
    g.parse(res / "quality_graph.ttl", format="turtle")
    results = run_queries(g)

    md = ["# 온톨로지 질의 결과\n"]
    for qid, df in results.items():
        desc, q = QUERIES[qid]
        print(f"\n[{qid}] {desc}")
        print(df.to_string(index=False) if len(df) else "  (결과 없음)")
        md += [f"## {qid}: {desc}\n", "```sparql", q.split("\n", 6)[-1].strip(), "```\n",
               df.to_markdown(index=False) if len(df) else "(결과 없음)", "\n"]
    (res / "ontology_queries.md").write_text("\n".join(md), encoding="utf-8")
    (res / "ontology_queries.json").write_text(
        json.dumps({k: json.loads(v.to_json(orient="records", force_ascii=False))
                    for k, v in results.items()}, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"\n저장: {res}/ontology_queries.md, ontology_queries.json")


if __name__ == "__main__":
    main()
