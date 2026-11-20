"""LLM 연결을 한곳에 모은 모듈.

어떤 LLM을 쓸지(provider)는 환경변수 PDQ_LLM_PROVIDER 또는 스크립트의 --provider 로 정한다.

  anthropic : Claude API (유료, ANTHROPIC_API_KEY 필요)
  openai    : OpenAI API (유료, OPENAI_API_KEY 필요)
  gemini    : Google Gemini API (무료 등급 있음, GEMINI_API_KEY 필요, https://aistudio.google.com 에서 발급)
  ollama    : 내 PC에서 돌리는 무료 LLM (https://ollama.com 설치, 데이터가 밖으로 나가지 않음)
  manual    : 수동. 질문(prompt)을 파일로 저장 -> 사람이 Claude 채팅 등에 붙여넣기
              -> 답을 파일로 저장 -> 다시 실행하면 그 답을 읽음 (무료, 설치 불필요)
  auto      : 위 순서대로 쓸 수 있는 것을 고름. 아무것도 없으면 None

모델 이름은 PDQ_LLM_MODEL 로 바꿀 수 있다.
"""
from __future__ import annotations

import json
import os
import re
import urllib.request
from pathlib import Path

DEFAULT_MODEL = {
    "anthropic": "claude-sonnet-5-5",
    "openai": "gpt-4o-mini",
    "gemini": "gemini-2.5-flash",
    "ollama": "qwen2.5:7b",
}
GEMINI_URL = os.environ.get("GEMINI_BASE_URL",
                            "https://generativelanguage.googleapis.com/v1beta").rstrip("/")
OLLAMA_URL = os.environ.get("OLLAMA_HOST", "http://localhost:11434").rstrip("/")
MANUAL_DIR = Path(os.environ.get("PDQ_MANUAL_DIR", "llm_io"))


class ManualPending(Exception):
    """수동 모드에서 아직 답 파일이 없을 때."""


def _ollama_alive() -> bool:
    try:
        with urllib.request.urlopen(OLLAMA_URL + "/api/tags", timeout=1.5) as r:
            return r.status == 200
    except Exception:
        return False


def pick_provider(requested: str | None = None) -> str | None:
    p = (requested or os.environ.get("PDQ_LLM_PROVIDER") or "auto").lower()
    if p != "auto":
        return p
    if os.environ.get("ANTHROPIC_API_KEY"):
        return "anthropic"
    if os.environ.get("OPENAI_API_KEY"):
        return "openai"
    if os.environ.get("GEMINI_API_KEY"):
        return "gemini"
    if _ollama_alive():
        return "ollama"
    return None


def model_name(provider: str) -> str:
    return os.environ.get("PDQ_LLM_MODEL") or DEFAULT_MODEL.get(provider, "-")


# ---------------------------------------------------------------- 각 LLM 호출
def _anthropic(system: str, user: str, max_tokens: int) -> str:
    import anthropic

    client = anthropic.Anthropic()
    msg = client.messages.create(model=model_name("anthropic"), max_tokens=max_tokens,
                                 system=system, temperature=0,
                                 messages=[{"role": "user", "content": user}])
    return "".join(b.text for b in msg.content if getattr(b, "type", "") == "text")


def _openai(system: str, user: str, max_tokens: int) -> str:
    from openai import OpenAI

    r = OpenAI().chat.completions.create(
        model=model_name("openai"), temperature=0, max_tokens=max_tokens,
        messages=[{"role": "system", "content": system}, {"role": "user", "content": user}])
    return r.choices[0].message.content


def _gemini(system: str, user: str, json_mode: bool) -> str:
    """Google Gemini REST API. 추가 설치 없이 표준 라이브러리로 호출한다."""
    key = os.environ["GEMINI_API_KEY"]
    body = {"system_instruction": {"parts": [{"text": system}]},
            "contents": [{"role": "user", "parts": [{"text": user}]}],
            "generationConfig": {"temperature": 0}}
    if json_mode:
        body["generationConfig"]["responseMimeType"] = "application/json"
    url = f"{GEMINI_URL}/models/{model_name('gemini')}:generateContent"
    req = urllib.request.Request(url, data=json.dumps(body).encode("utf-8"),
                                 headers={"Content-Type": "application/json", "x-goog-api-key": key})
    with urllib.request.urlopen(req, timeout=300) as r:
        data = json.loads(r.read().decode("utf-8"))
    parts = data["candidates"][0]["content"].get("parts", [])
    return "".join(p.get("text", "") for p in parts)


def _ollama(system: str, user: str, max_tokens: int, json_mode: bool) -> str:
    body = {"model": model_name("ollama"), "stream": False,
            "messages": [{"role": "system", "content": system},
                         {"role": "user", "content": user}],
            "options": {"temperature": 0, "num_predict": max_tokens}}
    if json_mode:
        body["format"] = "json"
    req = urllib.request.Request(OLLAMA_URL + "/api/chat", data=json.dumps(body).encode("utf-8"),
                                 headers={"Content-Type": "application/json"})
    # 프록시를 거치지 않고 내 PC(localhost)로 바로 보낸다
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    with opener.open(req, timeout=600) as r:
        return json.loads(r.read().decode("utf-8"))["message"]["content"]


def _manual(system: str, user: str, tag: str) -> str:
    MANUAL_DIR.mkdir(parents=True, exist_ok=True)
    prompt_f = MANUAL_DIR / f"{tag}_prompt.txt"
    resp_f = MANUAL_DIR / f"{tag}_response.txt"
    prompt_f.write_text(f"[지시]\n{system}\n\n[요청]\n{user}\n", encoding="utf-8")
    if resp_f.exists() and resp_f.read_text(encoding="utf-8").strip():
        return resp_f.read_text(encoding="utf-8")
    raise ManualPending(
        f"\n[수동 모드] 아래 순서로 하세요.\n"
        f"  1) 메모장으로 {prompt_f} 를 열어 전체 복사 (Ctrl+A, Ctrl+C)\n"
        f"  2) Claude 채팅(claude.ai)에 붙여넣고 답을 받기\n"
        f"  3) 답 전체를 복사해서 {resp_f} 로 저장 (메모장 새 파일 -> UTF-8로 저장)\n"
        f"  4) 같은 명령을 다시 실행\n")


def ask(system: str, user: str, *, provider: str, tag: str = "task",
        json_mode: bool = False, max_tokens: int = 2000) -> str:
    """LLM에 한 번 묻고 답 문자열을 돌려준다."""
    if provider == "anthropic":
        return _anthropic(system, user, max_tokens)
    if provider == "openai":
        return _openai(system, user, max_tokens)
    if provider == "gemini":
        return _gemini(system, user, json_mode)
    if provider == "ollama":
        return _ollama(system, user, max_tokens, json_mode)
    if provider == "manual":
        return _manual(system, user, tag)
    raise ValueError(f"알 수 없는 provider: {provider}")


def ask_many(system: str, items: dict[str, str], *, provider: str, tag: str,
             json_mode: bool = False, max_tokens: int = 1500) -> dict[str, str]:
    """여러 건을 묻는다. 자동 모드는 한 건씩, 수동 모드는 한 번에 묶어서 묻는다(붙여넣기 1회)."""
    if provider != "manual":
        out = {}
        for i, (k, u) in enumerate(items.items(), 1):
            print(f"  LLM 질의 {i}/{len(items)}: {k}", flush=True)
            out[k] = ask(system, u, provider=provider, tag=f"{tag}_{k}",
                         json_mode=json_mode, max_tokens=max_tokens)
        return out
    bundle = ("아래 여러 건을 각각 처리하고, 결과를 하나의 JSON 객체로만 답하십시오. "
              "키는 각 건의 ID, 값은 그 건의 답(문자열 또는 JSON 객체)입니다. JSON 외의 말은 쓰지 마십시오.\n\n")
    for k, u in items.items():
        bundle += f"===== ID: {k} =====\n{u}\n\n"
    raw = ask(system, bundle, provider="manual", tag=tag)
    data = extract_json(raw)
    if not isinstance(data, dict):
        raise ValueError("수동 모드 답에서 JSON 객체를 찾지 못했습니다.")
    return {k: (v if isinstance(v, str) else json.dumps(v, ensure_ascii=False))
            for k, v in data.items()}


# ---------------------------------------------------------------- 답 정리 도구
def extract_json(text: str):
    """LLM 답에서 JSON을 꺼낸다. ```json 코드블록이나 앞뒤 설명이 붙어 있어도 된다."""
    cands = [text.strip()]
    m = re.match(r"\s*```(?:json)?\s*(.*)```\s*$", text, re.S)  # 답 전체가 코드블록인 경우
    if m:
        cands.append(m.group(1))
    cands += re.findall(r"```json\s*(.*?)```", text, re.S)
    for c in list(cands):
        for opener, closer in (("{", "}"), ("[", "]")):
            s, e = c.find(opener), c.rfind(closer)
            if s != -1 and e > s:
                cands.append(c[s:e + 1])
    for c in cands:
        try:
            return json.loads(c)
        except (json.JSONDecodeError, TypeError):
            continue
    return None


def extract_code(text: str, lang: str = "sparql") -> str:
    """```sparql ... ``` 코드블록 안의 내용을 꺼낸다. 없으면 전체."""
    m = re.search(rf"```(?:{lang})?\s*(.*?)```", text, re.S | re.I)
    return (m.group(1) if m else text).strip()
