"""6단계 (LLM 기능 ①): 데이터 설명서를 LLM이 읽어 표준 메타데이터로 정리 -> 검사 -> 온톨로지.

사용:
  python scripts/06_llm_metadata.py                      # 쓸 수 있는 LLM 자동 선택 (없으면 비교용 추출기만)
  python scripts/06_llm_metadata.py --provider manual    # Claude 채팅에 붙여넣는 수동 모드
  python scripts/06_llm_metadata.py --provider ollama    # 내 PC의 무료 LLM

결과 (results 폴더):
  metadata_extracted.json  방식별 추출 결과
  metadata_eval.csv        문서·항목별 정답 여부
  metadata_graph.ttl       온톨로지 인스턴스 (형식 검사를 통과한 것만)
  metadata_queries.md      온톨로지 질의 결과
  ../ontology/pdq_extension.ttl  확장된 온톨로지 스키마 (v0.2)
"""
import argparse
import json
from pathlib import Path

import pandas as pd
from _common import ROOT

from pdq import meta_extract as mx
from pdq.llm_client import ManualPending, ask_many, extract_json, model_name, pick_provider
from pdq.ontology import build_schema


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--docs", default=str(ROOT / "examples" / "metadata"))
    ap.add_argument("--results", default="results")
    ap.add_argument("--provider", default=None, help="anthropic|openai|ollama|manual|auto")
    a = ap.parse_args()
    docs_dir, res = Path(a.docs), Path(a.results)
    res.mkdir(parents=True, exist_ok=True)

    docs = {p.stem: p.read_text(encoding="utf-8") for p in sorted(docs_dir.glob("*.txt"))}
    gt_path = docs_dir / "ground_truth.json"
    gt = json.loads(gt_path.read_text(encoding="utf-8")) if gt_path.exists() else {"answers": {}}
    truth = gt["answers"]
    print(f"설명서 {len(docs)}개를 읽었습니다.")

    results = {"baseline": {k: mx.baseline_extract(v) for k, v in docs.items()}}
    method_label = {"baseline": "규칙(키워드·정규식)"}

    provider = pick_provider(a.provider)
    if provider is None:
        print("\n[알림] 쓸 수 있는 LLM이 없어 비교용 규칙 추출기만 실행합니다."
              "\n       --provider manual (Claude 채팅 붙여넣기) 또는 ollama 로 다시 실행해 보세요.")
    else:
        print(f"\nLLM: {provider} ({model_name(provider) if provider != 'manual' else '사람이 붙여넣기'})")
        try:
            raw = ask_many(mx.SYSTEM_PROMPT, {k: mx.user_prompt(v) for k, v in docs.items()},
                           provider=provider, tag="metadata", json_mode=True, max_tokens=400)
        except ManualPending as e:
            print(e)
            return
        results["llm"] = {k: (extract_json(v) if isinstance(v, str) else v) for k, v in raw.items()}
        method_label["llm"] = f"LLM ({provider})"

    # ---- 1) 형식 검사
    print("\n[형식 검사] (코드가 LLM 답을 검사)")
    for method, recs in results.items():
        bad = {k: mx.validate(r) for k, r in recs.items() if mx.validate(r)}
        print(f"  {method_label[method]}: 통과 {len(recs) - len(bad)}/{len(recs)}")
        for k, errs in bad.items():
            print(f"    - {k}: {'; '.join(errs[:2])}")

    # ---- 2) 정답표와 비교
    rows = []
    for method, recs in results.items():
        for doc_id, t in truth.items():
            sc = mx.score(recs.get(doc_id), t)
            for f, ok in sc.items():
                rows.append({"method": method_label[method], "doc": doc_id, "field": f,
                             "pred": (recs.get(doc_id) or {}).get(f), "truth": t.get(f), "correct": ok})
    ev = pd.DataFrame(rows)
    ev.to_csv(res / "metadata_eval.csv", index=False, encoding="utf-8-sig")
    if len(ev):
        print("\n[정확도] 정답표와 비교 (항목 기준)")
        acc = ev.groupby("method")["correct"].mean().mul(100).round(1)
        for m, v in acc.items():
            n_ok = int(ev[ev.method == m].correct.sum())
            print(f"  {m}: {v}%  ({n_ok}/{int((ev.method == m).sum())})")
        print("\n  항목별 정확도(%)")
        print(ev.pivot_table(index="field", columns="method", values="correct", aggfunc="mean")
              .mul(100).round(0).reindex(mx.SCORED).to_string())
        best = "llm" if "llm" in results else "baseline"
        wrong = ev[(ev.method == method_label[best]) & (~ev.correct)]
        if len(wrong):
            print(f"\n  틀린 곳 ({method_label[best]}):")
            for _, r in wrong.iterrows():
                print(f"    {r.doc} {r.field}: 추출 {r.pred} / 정답 {r.truth}")

    # ---- 3) 실제 데이터와 대조 (데모 데이터가 있을 때)
    chosen = "llm" if "llm" in results else "baseline"
    notes = {}
    mpath = res / "metrics.csv"
    if mpath.exists() and gt.get("demo_link"):
        metrics = pd.read_csv(mpath)
        print("\n[실제 데이터와 대조] 설명서 내용 vs 01단계 측정값")
        for doc_id, machine in gt["demo_link"].items():
            rec = results[chosen].get(doc_id) or {}
            n = mx.cross_check(rec, metrics, machine)
            notes[doc_id] = n
            print(f"  {doc_id} ({machine}): " + ("일치" if not n else " / ".join(n)))

    # ---- 4) 온톨로지
    ext = mx.build_extension_schema()
    (ROOT / "ontology").mkdir(exist_ok=True)
    ext.serialize(ROOT / "ontology" / "pdq_extension.ttl", format="turtle")
    inst = mx.records_to_graph(results[chosen], method_label[chosen], notes)
    inst.serialize(res / "metadata_graph.ttl", format="turtle")
    g = build_schema() + ext + inst
    print(f"\n[온톨로지] 확장 스키마 {len(ext)}개 + 인스턴스 {len(inst)}개 트리플 "
          f"(형식 검사 통과한 {method_label[chosen]} 결과만)")
    md = ["# 메타데이터 온톨로지 질의 결과", ""]
    for qid, (desc, q) in mx.EXT_QUERIES.items():
        r = g.query(q)
        df = pd.DataFrame([[v.toPython() if v is not None else None for v in row] for row in r],
                          columns=[str(v) for v in r.vars])
        print(f"\n{qid}: {desc}\n" + (df.to_string(index=False) if len(df) else "  (없음)"))
        md += [f"## {qid}", desc, "", "```sparql", q.strip(), "```", "",
               df.to_markdown(index=False) if len(df) else "(없음)", ""]
    (res / "metadata_queries.md").write_text("\n".join(md), encoding="utf-8")
    (res / "metadata_extracted.json").write_text(
        json.dumps({method_label[k]: v for k, v in results.items()}, ensure_ascii=False, indent=1),
        encoding="utf-8")
    print(f"\n저장: {res}/metadata_extracted.json, metadata_eval.csv, metadata_graph.ttl, "
          f"metadata_queries.md, ontology/pdq_extension.ttl")


if __name__ == "__main__":
    main()
