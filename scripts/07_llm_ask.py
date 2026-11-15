"""7단계 (LLM 기능 ②): 말로 한 질문 -> LLM 이 SPARQL 로 번역 -> 온톨로지에서 실행 -> 정답과 비교.

사용:
  python scripts/07_llm_ask.py --provider manual            # 시험 질문 10개 (Claude 채팅 붙여넣기)
  python scripts/07_llm_ask.py --provider ollama --answer   # 문장 답까지
  python scripts/07_llm_ask.py --provider ollama --q "valve 기계에서 WARN 판정 파일은 몇 개야?"

결과: results/ask_eval.csv, results/ask_log.md
"""
import argparse
import json
from pathlib import Path

import pandas as pd
from _common import ROOT
from rdflib import Graph

from pdq.llm_client import ManualPending, ask, ask_many, extract_code, model_name, pick_provider
from pdq.llm_report import check_numbers
from pdq.nl2sparql import ANSWER_PROMPT, SYSTEM_PROMPT, run, same_result
from pdq.ontology import PREFIXES


def load_graph(res: Path) -> Graph:
    g = Graph()
    g.parse(ROOT / "ontology" / "pdq_schema.ttl")
    g.parse(res / "quality_graph.ttl")
    return g


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--results", default="results")
    ap.add_argument("--questions", default=str(ROOT / "examples" / "questions.json"))
    ap.add_argument("--provider", default=None)
    ap.add_argument("--q", default=None, help="질문 하나만 직접 묻기")
    ap.add_argument("--answer", action="store_true", help="결과를 LLM이 문장으로 설명 (+숫자 대조)")
    a = ap.parse_args()
    res = Path(a.results)

    print("온톨로지를 불러오는 중...")
    g = load_graph(res)
    print(f"  트리플 {len(g)}개")

    if a.q:
        qs = [{"id": "USER", "question": a.q, "gold": None}]
    else:
        qs = json.loads(Path(a.questions).read_text(encoding="utf-8"))["questions"]

    provider = pick_provider(a.provider)
    if provider is None:
        print("\n[알림] 쓸 수 있는 LLM이 없습니다. 정답 질의(gold)만 실행해 기대 답을 보여 줍니다."
              "\n       --provider manual 또는 ollama 로 다시 실행하세요.\n")
        for q in qs:
            if q["gold"]:
                rows, err = run(g, PREFIXES + q["gold"])
                print(f"{q['id']} {q['question']}\n   기대 답: {err or rows}")
        return

    print(f"LLM: {provider} ({model_name(provider) if provider != 'manual' else '사람이 붙여넣기'})")
    try:
        raw = ask_many(SYSTEM_PROMPT, {q["id"]: "질문: " + q["question"] for q in qs},
                       provider=provider, tag="ask_sparql", max_tokens=600)
    except ManualPending as e:
        print(e)
        return

    rows_out, log = [], ["# 자연어 질문 -> SPARQL 결과", ""]
    answers_needed = {}
    for q in qs:
        sparql = extract_code(raw.get(q["id"], ""), "sparql")
        pred, err = run(g, sparql)
        gold = run(g, PREFIXES + q["gold"])[0] if q["gold"] else None
        ok = same_result(pred, gold) if gold is not None else None
        mark = "-" if ok is None else ("정답" if ok else "오답")
        print(f"\n{q['id']} [{mark}] {q['question']}")
        print(f"   LLM 결과: {err or pred[:5]}" + (f"\n   정답    : {gold[:5]}" if gold is not None and not ok else ""))
        rows_out.append({"id": q["id"], "question": q["question"], "correct": ok,
                         "error": err, "llm_rows": json.dumps(pred, ensure_ascii=False, default=str)[:300],
                         "gold_rows": json.dumps(gold, ensure_ascii=False, default=str)[:300]})
        log += [f"## {q['id']} [{mark}] {q['question']}", "", "```sparql", sparql, "```", "",
                f"- LLM 결과: {err or pred}", f"- 정답: {gold}", ""]
        if a.answer and pred:
            answers_needed[q["id"]] = (f"질문: {q['question']}\n결과: "
                                       + json.dumps(pred, ensure_ascii=False, default=str))

    ev = pd.DataFrame(rows_out)
    scored = ev[ev["correct"].notna()]
    if len(scored):
        n_ok = int(scored["correct"].sum())
        print(f"\n[정확도] {n_ok}/{len(scored)} = {100 * n_ok / len(scored):.0f}%  "
              f"(실행 오류 {int((scored['error'] != '').sum())}건)")
        log.insert(2, f"정확도: {n_ok}/{len(scored)} ({provider})\n")

    if answers_needed:
        try:
            ans = ask_many(ANSWER_PROMPT, answers_needed, provider=provider, tag="ask_answer",
                           max_tokens=300)
        except ManualPending as e:
            print(e)
            ans = {}
        print("\n[문장 답] (숫자는 결과 표와 자동 대조)")
        for k, text in ans.items():
            unknown = check_numbers(text, {"r": answers_needed[k]})
            flag = "숫자 일치" if not unknown else f"확인 필요 숫자: {unknown}"
            print(f"  {k}: {text.strip()}  ({flag})")
            log += [f"### {k} 문장 답", text.strip(), f"- 숫자 대조: {flag}", ""]

    ev.to_csv(res / "ask_eval.csv", index=False, encoding="utf-8-sig")
    (res / "ask_log.md").write_text("\n".join(log), encoding="utf-8")
    print(f"\n저장: {res}/ask_eval.csv, {res}/ask_log.md")


if __name__ == "__main__":
    main()
