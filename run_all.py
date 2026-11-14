"""전체 파이프라인 실행 (Windows/Mac/Linux 공통).

데모:      python run_all.py
실제 데이터: python run_all.py --data <DCASE dev_data 폴더> --out results_dcase
"""
import argparse
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def run(*args):
    print("\n$ python", " ".join(args), flush=True)
    subprocess.run([sys.executable, *args], cwd=ROOT, check=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default="data/demo")
    ap.add_argument("--out", default="results")
    a = ap.parse_args()
    if a.data == "data/demo" and not (ROOT / "data" / "demo").exists():
        run("scripts/00_make_demo_data.py", "--out", "data/demo")
    shutil.rmtree(ROOT / a.out / "injected", ignore_errors=True)
    run("scripts/01_check_quality.py", "--data", a.data, "--out", a.out)
    run("scripts/02_inject_and_validate.py", "--data", a.data, "--results", a.out)
    run("scripts/03_build_ontology.py", "--results", a.out)
    run("scripts/04_query_ontology.py", "--results", a.out)
    run("scripts/05_llm_report.py", "--results", a.out)


if __name__ == "__main__":
    main()
