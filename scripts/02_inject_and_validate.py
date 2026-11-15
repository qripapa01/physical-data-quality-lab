"""2단계: 결함 주입 시험 - 점검기가 '알고 있는 결함'을 찾아내는지 검출률을 잰다.

PASS 판정을 받은 깨끗한 파일을 골라 8종 결함을 하나씩 넣은 복사본을 만들고,
원본 데이터셋과 함께 다시 점검한다. 결함마다 그 결함을 잡도록 만든 '목표 규칙'에 걸린 비율이 검출률이다.

사용:  python scripts/02_inject_and_validate.py --data data/demo --results results --n 10
결과:  injection_results.csv, figures/injection_detection.png
"""
import argparse
from pathlib import Path

import numpy as np
import pandas as pd
import soundfile as sf
from _common import INK, INK2, SERIES_1, SERIES_2, SURFACE, metrics_table

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

from pdq.inject import DEFECTS  # noqa: E402
from pdq.rules import evaluate, load_thresholds  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", required=True)
    ap.add_argument("--results", default="results", help="1단계 결과 폴더")
    ap.add_argument("--n", type=int, default=10, help="결함·세기 조합마다 만들 파일 수")
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--config", default=None)
    args = ap.parse_args()

    res = Path(args.results)
    cfg = load_thresholds(args.config)
    base = pd.read_csv(res / "metrics.csv")
    rng = np.random.default_rng(args.seed)

    # 깨끗한 학습용 정상 파일 중에서 고른다 (source 도메인 우선)
    pool = base[(base["verdict"] == "PASS") & (base["label"] == "normal")]
    if "source" in set(pool["domain"].dropna()):
        pool = pool[pool["domain"] == "source"]
    if len(pool) == 0:
        raise SystemExit("PASS 판정을 받은 정상 파일이 없습니다.")

    inj_dir = res / "injected"
    records, machines = [], []
    combos = [(name, lv) for name, spec in DEFECTS.items() for lv in spec[3]]
    for name, level in combos:
        fn, expected, desc, _ = DEFECTS[name]
        pick = pool.sample(n=args.n, replace=len(pool) < args.n,
                           random_state=int(rng.integers(1 << 30)))
        for k, (_, row) in enumerate(pick.iterrows()):
            x, sr = sf.read(row["file"], dtype="float64")
            if x.ndim > 1:
                x = x.mean(axis=1)
            y, sr2 = fn(x, sr, rng, level)
            src = Path(row["file"])
            dst = (inj_dir / row["machine"] / src.parent.name /
                   f"{src.stem}__inj_{name}_{level}_{k}.wav")
            dst.parent.mkdir(parents=True, exist_ok=True)
            sf.write(dst, np.clip(y, -1, 1), sr2, subtype="PCM_16")
            records.append({"file": str(dst), "defect": name, "level": level,
                            "expected_rule": expected, "description": desc,
                            "source_file": row["file"]})
            machines.append(row["machine"])
    inj = pd.DataFrame(records)
    print(f"결함 {len(combos)}종x세기, 주입 파일 {len(inj)}개 생성 -> {inj_dir}")

    # 원본 전체 + 주입 파일을 함께 다시 점검 (중복·이상치 점검은 데이터셋 전체가 필요)
    new = metrics_table(inj["file"].tolist(), cfg["silence_dbfs"])
    new = new[new["read_error"] == ""].drop(columns="read_error")
    new["machine"] = new["file"].map(dict(zip(inj["file"], machines)))
    allm = pd.concat([base.drop(columns="verdict"), new], ignore_index=True)
    _, issues = evaluate(allm, cfg)

    hits = issues.groupby("file")["rule_id"].apply(set).to_dict()
    inj["rules_hit"] = inj["file"].map(lambda f: sorted(hits.get(f, set())))
    inj["detected"] = [e in set(r) for e, r in zip(inj["expected_rule"], inj["rules_hit"])]
    inj["detected_any"] = inj["rules_hit"].map(len) > 0  # 목표 규칙이 아니어도 어떤 규칙이든 WARN/FAIL을 냈는가
    inj.to_csv(res / "injection_results.csv", index=False)

    order = {n: i for i, n in enumerate(DEFECTS)}
    table = (inj.groupby(["defect", "level", "description", "expected_rule"])
             .agg(sum=("detected", "sum"), count=("detected", "size"),
                  any_sum=("detected_any", "sum")).reset_index())
    table["detection_rate"] = table["sum"] / table["count"]
    table["any_rule_rate"] = table["any_sum"] / table["count"]
    table["o"] = table["defect"].map(order)
    # 세기 정렬: 목록 순서(약 -> 강) 그대로
    table["lo"] = [DEFECTS[d][3].index(lv) for d, lv in zip(table["defect"], table["level"])]
    table = table.sort_values(["o", "lo"]).drop(columns=["o", "lo"]).reset_index(drop=True)
    print("\n결함별·세기별 검출률 (약 -> 강):")
    for _, r in table.iterrows():
        print(f"  {r['description']:<20} level={r['level']:<6} {r['expected_rule']:<16}"
              f" {int(r['sum'])}/{int(r['count'])}  ({r['detection_rate']:.0%})"
              f"   전체 규칙(any rule): {r['any_rule_rate']:.0%}")
    total = inj["detected"].mean()
    total_any = inj["detected_any"].mean()
    print(f"\n목표 규칙(target rule) 검출률: {total:.1%}, 전체 규칙(any rule) 검출률: {total_any:.1%}  (주입 {len(inj)}건)")
    table.to_csv(res / "injection_summary.csv", index=False)

    labels = [f"{d} @ {lv:g}" if len(DEFECTS[d][3]) > 1 else d
              for d, lv in zip(table["defect"], table["level"])]
    fig, ax = plt.subplots(figsize=(8.5, 0.45 * len(table) + 1.4), facecolor=SURFACE)
    ax.set_facecolor(SURFACE)
    ypos = list(range(len(table)))[::-1]
    yp = np.array(ypos, dtype=float)
    ax.barh(yp + 0.19, table["detection_rate"] * 100, color=SERIES_1, height=0.36,
            label="caught by the target rule")
    ax.barh(yp - 0.19, table["any_rule_rate"] * 100, color=SERIES_2, height=0.36,
            label="caught by any rule (WARN or FAIL)")
    for y, (_, r) in zip(ypos, table.iterrows()):
        ax.text(max(r["detection_rate"], r["any_rule_rate"]) * 100 + 1.5, y,
                f"{int(r['sum'])} / {int(r['any_sum'])} of {int(r['count'])}",
                va="center", fontsize=8.5, color=INK2)
    ax.set_ylim(-0.7, len(table) - 0.3)
    ax.legend(loc="lower left", bbox_to_anchor=(0, 1.0), ncol=2, frameon=False, fontsize=9)
    ax.set_yticks(ypos, labels, fontsize=8.5)
    ax.set_xlim(0, 122)
    ax.set_xticks([0, 20, 40, 60, 80, 100])
    ax.set_xlabel("files flagged (%)  -  each defect listed weak to strong level", color=INK2)
    ax.set_title(f"Defect-injection test: target rule {total:.0%}, any rule {total_any:.0%}",
                 loc="left", color=INK, fontsize=12, pad=26)
    for sp in ["top", "right"]:
        ax.spines[sp].set_visible(False)
    ax.tick_params(colors=INK2)
    fig.tight_layout()
    fig.savefig(res / "figures" / "injection_detection.png", dpi=150)
    plt.close(fig)
    print(f"저장: {res}/injection_results.csv, injection_summary.csv, figures/injection_detection.png")


if __name__ == "__main__":
    main()
