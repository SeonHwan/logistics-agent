import json
import re
import sys

from dotenv import load_dotenv
from langchain_anthropic import ChatAnthropic
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI
from langgraph.types import Overwrite, Send

sys.path.insert(0, "src/phase3")
sys.path.insert(0, "src/phase4")
from agent_tools import TOOLS_BY_ANALYST
from texts import text_of

# 검증자 두 명: 이름 -> 모델 ID. 모델 계열이 달라야 한쪽이 놓친 것을 다른 쪽이 볼 수 있을 것이라는 기대에서 골랐다
# (이 기대가 실제로 맞는지는 측정하지 않았다).
VERIFIER_MODELS = {
    "opus": "claude-opus-5-5",
    "terra": "gpt-5.6-terra",
}

# 취합을 다시 쓰게 되돌리는 최대 횟수. 검증 호출이 한 번에 2회이므로 상한을 작게 둔다.
MAX_RETRIES = 1

VERIFY_PROMPT = """당신은 물류 분석팀의 검증 담당입니다. 취합된 최종 답이 분석가 결과와 분석가의 도구 범위에 맞는지 검사합니다.
다음을 확인하세요.
1. 최종 답의 숫자가 분석가 결과에 있는 것인가(없는 숫자를 만들거나 바꿔 옮기지 않았는가).
2. 분석가 결과나 최종 답이 분석가의 도구로 할 수 없는 분석(도구 목록에 없는 계산, 도로 용량 기반 병목 판정 등)을 해 주겠다고 제안하지 않았는가.
3. 도구 결과에 없는 내용을 추측이 아닌 사실처럼 쓰지 않았는가.
문제가 없으면 ok를 true로, 있으면 false로 하고 issues에 문제를 한 줄씩 적으세요. 문제가 있다고 판단한 이유를 답에서 인용하세요.
reason에는 통과든 실패든 그렇게 판단한 근거를 한두 문장으로 적으세요(위 세 항목 중 무엇을 어떻게 확인했는지 포함).
반드시 이 JSON 하나만 출력하세요: {"ok": true 또는 false, "reason": "...", "issues": ["...", "..."]}"""


def build_verifier(name):
    # 검증자 이름에 맞는 모델을 만든다(만드는 것만으로는 호출이 일어나지 않는다).
    # 키는 환경 변수 ANTHROPIC_API_KEY, OPENAI_API_KEY에서 읽는다.
    load_dotenv()

    if name == "opus":
        return ChatAnthropic(model=VERIFIER_MODELS["opus"], max_tokens=4096)

    # terra는 OpenAI Responses API 형식으로 호출한다.
    return ChatOpenAI(
        model=VERIFIER_MODELS["terra"],
        use_responses_api=True,
        max_tokens=4096,
    )


def build_verifiers():
    verifiers = {}
    for name in VERIFIER_MODELS:
        verifiers[name] = build_verifier(name)
    return verifiers


def tools_text():
    # 분석가별 도구 이름 목록을 검증자에게 줄 글로 만든다. 검증자는 "이 분석가가 할 수 없는 일"을 판단하는 근거로 쓴다.
    lines = []
    for analyst, tools in TOOLS_BY_ANALYST.items():
        names = []
        for tool in tools:
            names.append(tool.name)
        lines.append(f"- {analyst}: " + ", ".join(names))
    return "\n".join(lines)


def parse_verdict(text):
    # 검증자 답에서 {"ok":..., "issues":[...]}를 꺼낸다. 못 읽으면 통과로 보지 않고 실패(ok=False)로 돌려준다.
    # 제대로 읽지 못한 판정을 통과로 치면 검증이 구멍이 되기 때문이다.
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if match is None:
        return {"ok": False, "reason": "", "issues": ["검증자 답에서 JSON을 찾지 못했습니다."]}
    try:
        data = json.loads(match.group(0))
    except json.JSONDecodeError:
        return {"ok": False, "reason": "", "issues": ["검증자 답의 JSON을 읽지 못했습니다."]}

    ok = data.get("ok")
    issues = data.get("issues", [])
    if not isinstance(ok, bool) or not isinstance(issues, list):
        return {"ok": False, "reason": "", "issues": ["검증자 답의 형식이 약속과 다릅니다."]}
    if not ok and not issues:
        issues = ["검증자가 실패로 판정했으나 사유를 적지 않았습니다."]
    # reason은 판정에 영향을 주지 않는다(통과·실패는 ok로만 정한다). 근거를 사람이 읽기 위한 글이다.
    return {"ok": ok, "reason": str(data.get("reason", "")), "issues": [str(item) for item in issues]}


def route_to_verifiers(state):
    # 취합 뒤 갈림길: 검증자마다 Send 하나를 만들어 병렬로 실행한다(분석가 병렬과 같은 방식).
    sends = []
    for name in VERIFIER_MODELS:
        sends.append(Send("verify_one", {"verifier": name, "question": state["question"],
                                         "results": state["results"], "answer": state["answer"]}))
    return sends


def build_verify_one(verifiers):
    def verify_one(state, config):
        # Send로 들어온 입력 한 건을 해당 검증자 모델로 판정한다. 모델 호출 1회.
        name = state["verifier"]
        blocks = []
        for item in state["results"]:
            blocks.append(f"[{item['analyst']} 분석가 결과]\n{item['text']}")
        body = (
            "질문: " + state["question"]
            + "\n\n분석가별 도구:\n" + tools_text()
            + "\n\n" + "\n\n".join(blocks)
            + "\n\n[최종 답]\n" + state["answer"]
        )
        messages = [SystemMessage(content=VERIFY_PROMPT), HumanMessage(content=body)]
        response = verifiers[name].invoke(messages, config)

        raw = text_of(response.content)
        verdict = parse_verdict(raw)
        verdict["verifier"] = name
        verdict["raw"] = raw  # 파싱 전 원문. 파싱이 판정을 어떻게 읽었는지 대조하려고 남긴다.
        return {"verdicts": [verdict]}

    return verify_one


def judge(state):
    # 검증자 판정을 합치는 노드. 한쪽이라도 ok=False이면 실패로 본다(합치는 규칙: 하나라도 지적하면 실패).
    # 실패하면 지적 사항을 모아 feedback에 적고 retries를 1 올린다. 통과하면 feedback을 비운다.
    problems = []
    for verdict in state["verdicts"]:
        if not verdict["ok"]:
            for issue in verdict["issues"]:
                problems.append(f"[{verdict['verifier']}] {issue}")

    # verdicts는 병렬 결과를 이어 붙이는 필드라, 되돌려 다시 검증하면 이전 판정이 남아 계속 실패로 보인다.
    # 읽은 뒤에는 Overwrite로 비워 다음 라운드가 새 판정만 갖게 한다. 비우기 전에 history에 라운드별로 보관한다
    # (history는 이어 붙이기 필드라 비워지지 않는다).
    round_record = {"round": state["retries"], "verdicts": state["verdicts"]}
    if not problems:
        return {"feedback": "", "passed": True, "verdicts": Overwrite(value=[]), "history": [round_record]}
    return {"feedback": "\n".join(problems), "passed": False, "retries": state["retries"] + 1,
            "verdicts": Overwrite(value=[]), "history": [round_record]}


def route_after_judge(state):
    # 통과했거나 되돌릴 횟수를 다 썼으면 끝낸다. 아니면 취합으로 되돌린다.
    if state["passed"] or state["retries"] > MAX_RETRIES:
        return "end"
    return "synthesize"
