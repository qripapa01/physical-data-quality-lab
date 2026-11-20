"""API 첫걸음: LLM 에 질문 하나를 보내고 답을 받는다.

API 란? 내 프로그램이 인터넷 너머의 LLM 에게 '요청'을 보내고 '응답'을 받는 정해진 약속(창구)이다.
  요청에 들어가는 것: API 키(출입증), 모델 이름, 지시(system), 질문(user)
  응답에 들어오는 것: LLM 의 답(text)

사용:
  set GEMINI_API_KEY=발급받은키        (Windows 명령 프롬프트, 무료)
  python scripts/llm_hello.py --provider gemini
  python scripts/llm_hello.py --provider gemini --q "클리핑이 뭔지 한 문장으로 설명해줘"
  python scripts/llm_hello.py --provider ollama   (내 PC LLM)
"""
import argparse
import time

from _common import ROOT  # noqa: F401

from pdq.llm_client import ManualPending, ask, model_name, pick_provider


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--provider", default=None)
    ap.add_argument("--q", default="물리 데이터 품질 검사에서 '클리핑'이 무엇인지 초등학생도 알게 두 문장으로 설명해 줘.")
    a = ap.parse_args()
    provider = pick_provider(a.provider)
    if provider is None:
        print("쓸 수 있는 LLM이 없습니다. --provider gemini (키 필요) / ollama / manual 중 하나를 지정하세요.")
        return
    print(f"[요청] 창구: {provider} / 모델: {model_name(provider)}")
    print(f"[요청] 질문: {a.q}")
    t0 = time.time()
    try:
        answer = ask("당신은 친절한 한국어 설명 도우미입니다.", a.q, provider=provider, tag="hello",
                     max_tokens=300)
    except ManualPending as e:
        print(e)
        return
    except Exception as e:
        print(f"[오류] {type(e).__name__}: {e}")
        print("  - 401/403: API 키가 틀렸거나 설정 안 됨  - 429: 무료 사용량 초과(잠시 후 다시)"
              "  - 404: 모델 이름 확인 (set PDQ_LLM_MODEL=모델이름)")
        return
    print(f"[응답] {time.time() - t0:.1f}초 걸림\n{answer.strip()}")


if __name__ == "__main__":
    main()
