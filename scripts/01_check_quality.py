"""1단계: 모든 WAV 파일의 품질 지표를 계산하고 규칙으로 PASS/WARN/FAIL 판정.

사용:  python scripts/01_check_quality.py --data data/demo --out results
       python scripts/01_check_quality.py --data ~/dcase2026/dev_data/raw --out results_dcase
결과:  metrics.csv(파일별 지표+판정), issues.csv(규칙 위반 목록), figures/verdict_by_machine.png
"""
import argparse
import time
from pathlib import Path

from _common import INK, INK2, STATUS_COLORS, SURFACE, metrics_table

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

from pdq.io_utils import find_wavs  # noqa: E402
from pdq.rules import evaluate, load_thresholds  # noqa: E402


def plot_verdicts(df, path):
    tab = (df.groupby(["machine", "verdict"]).size().unstack(fill_value=0)
           .reindex(columns=["PASS", "WARN", "FAIL"], fill_value=0))
    share = tab.div(tab.sum(axis=1), axis=0) * 100
    fig, ax = plt.subplots(figsize=(8, 0.6 * len(tab) + 1.4), facecolor=SURFACE)
    ax.set_facecolor(SURFACE)
    left = 0
    for v in ["PASS", "WARN", "FAIL"]:
        ax.barh(share.index, share[v], left=left, color=STATUS_COLORS[v], label=v,
                edgecolor=SURFACE, linewidth=2, height=0.6)
        left = left + share[v]
    for i, m in enumerate(tab.index):
        bad = tab.loc[m, "WARN"] + tab.loc[m, "FAIL"]
        ax.text(101, i, f"{bad} of {tab.loc[m].sum()} flagged", va="center", fontsize=9, color=INK2)
    ax.set_xlim(0, 125)
    ax.set_xticks([0, 20, 40, 60, 80, 100])
    ax.set_xlabel("share of files (%)", color=INK2)
    ax.set_title("Quality verdict by machine type", loc="left", color=INK, fontsize=12)
    ax.legend(ncol=3, loc="upper left", bbox_to_anchor=(0, -0.25), frameon=False)
    for s in ["top", "right"]:
        ax.spines[s].set_visible(False)
    ax.tick_params(colors=INK2)
    fig.tight_layout()
    fig.savefig(path, dpi=150)
    plt.close(fig)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", required=True, help="WAV 파일이 있는 폴더 (하위 폴더 포함)")
    ap.add_argument("--out", default="results")
    ap.add_argument("--config", default=None, help="기준값 JSON (기본: config/thresholds.json)")
    ap.add_argument("--jobs", type=int, default=None)
    args = ap.parse_args()

    out = Path(args.out)
    (out / "figures").mkdir(parents=True, exist_ok=True)
    cfg = load_thresholds(args.config)

    paths = find_wavs(args.data)
    if not paths:
        raise SystemExit(f"WAV 파일이 없습니다: {args.data}")
    print(f"{len(paths)}개 파일 점검 시작")
    t0 = time.time()
    df = metrics_table(paths, cfg["silence_dbfs"], args.jobs)
    bad = df[df["read_error"] != ""]
    if len(bad):
        bad.to_csv(out / "read_errors.csv", index=False)
    df = df[df["read_error"] == ""].drop(columns="read_error").reset_index(drop=True)

    df, issues = evaluate(df, cfg)
    df.to_csv(out / "metrics.csv", index=False)
    issues.to_csv(out / "issues.csv", index=False)
    plot_verdicts(df, out / "figures" / "verdict_by_machine.png")

    print(f"\n완료 ({time.time() - t0:.1f}초)")
    print("판정:", df["verdict"].value_counts().to_dict())
    if len(issues):
        print("\n규칙별 이슈 수:")
        print(issues.groupby(["rule_id", "severity"]).size().to_string())
    print(f"\n저장: {out}/metrics.csv, issues.csv, figures/verdict_by_machine.png")


if __name__ == "__main__":
    main()
