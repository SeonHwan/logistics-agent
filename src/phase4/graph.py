import operator
import sys
from typing import Annotated, TypedDict

from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.graph import END, START, StateGraph
from langgraph.types import Send

sys.path.insert(0, "src/phase4")
import supervisor
from analyst import build_all_analysts, build_base_model
from texts import text_of


class TeamState(TypedDict):
    # 팀 전체가 함께 읽고 쓰는 상태.
    question: str
    selected: list
    # results: 분석가 여러 명이 동시에 결과를 적는다. 그냥 덮어쓰면 마지막 한 명 것만 남으므로,
    # 'operator.add'(리스트 + 리스트 = 이어 붙이기)로 합치도록 표시한다.
    results: Annotated[list, operator.add]
    answer: str
    # 사람 승인 결과. 승인 단계를 쓰지 않는 실행에서는 채워지지 않는다.
    approved: bool
    # 검증: verdicts는 검증자 둘이 동시에 적으므로 이어 붙이기, retries는 취합을 되돌린 횟수,
    # feedback은 되돌릴 때 취합에 줄 지적 사항, passed는 마지막 검증 통과 여부.
    verdicts: Annotated[list, operator.add]
    history: Annotated[list, operator.add]  # 라운드별 판정 기록. judge가 verdicts를 비우기 전에 옮겨 둔다.
    retries: int
    feedback: str
    passed: bool


SYNTH_PROMPT = """당신은 물류 분석팀의 취합 담당입니다. 사용자 질문과 분석가들의 결과를 받아 하나의 답으로 정리합니다.
- 숫자는 분석가 결과에 있는 것만 쓰고, 새로 계산하거나 추측으로 채우지 마세요.
- 분석가가 밝힌 한계(병목이 아니라 집중도, 낮게 나온 절대 금액, 철도 연계 단정 불가 등)는 빼지 말고 답에 남기세요.
- 분석가 결과끼리 맞지 않거나 질문에 답하지 못한 부분이 있으면 숨기지 말고 그대로 말하세요.
- 답은 질문에 대한 결론을 먼저, 근거를 그다음에 쓰세요."""


def route_after_supervisor(state):
    # supervisor가 고른 분석가마다 Send 하나를 만든다. Send("노드 이름", 그 노드에 줄 입력)이다.
    # Send를 여러 개 돌려주면 LangGraph가 그 노드를 입력만 바꿔 동시에 여러 번 실행한다(병렬 분기).
    # 고른 분석가가 없으면 Send 대신 노드 이름을 돌려주어 거절 노드로 보낸다.
    if not state["selected"]:
        return "decline"

    sends = []
    for name in state["selected"]:
        sends.append(Send("analyst_run", {"question": state["question"], "analyst": name}))
    return sends


def decline_node(state):
    # 어느 분석가도 맡을 수 없는 질문이면 모델을 부르지 않고 안내만 한다.
    return {"answer": "이 질문은 현재 분석가(물동량 집중도, 센터 운송비, 수송수단 비중, 컨테이너 집중도)가 다루는 범위가 아닙니다."}


def route_after_approve(state):
    # 승인했으면 취합으로, 아니면 바로 끝낸다(approve 노드가 거절 안내를 answer에 적어 두었다).
    if state["approved"]:
        return "synthesize"
    return "end"


def build_team_graph(analysts=None, synth_model=None, checkpointer=None, approval=False, verify=False, verifiers=None):
    # analysts, synth_model을 바깥에서 넣을 수 있게 열어 둔다. 안 넣으면 분석가 4명과 취합 모델을 만든다
    # (만드는 것만으로는 모델 호출이 일어나지 않는다).
    # approval=True면 분석가 뒤·취합 앞에 사람 승인 노드를 끼운다. 멈췄다 이어가려면 checkpointer가 필요하다.
    if analysts is None:
        analysts = build_all_analysts()
    if synth_model is None:
        synth_model = build_base_model()

    def analyst_run(state, config):
        # Send로 들어온 입력({"question", "analyst"})으로 해당 분석가 서브그래프를 실행한다.
        # config를 서브그래프에 그대로 넘겨야 Langfuse 기록이 한 trace 아래에 묶인다.
        name = state["analyst"]
        sub_result = analysts[name].invoke({"messages": [HumanMessage(content=state["question"])]}, config)
        last_message = sub_result["messages"][-1]
        return {"results": [{"analyst": name, "text": text_of(last_message.content)}]}

    def synthesize(state, config):
        # 분석가 결과를 이름과 함께 한 덩어리 글로 만들어 취합 모델에게 준다.
        # config를 모델 호출에 넘겨야 Langfuse에서 분석가 호출들과 같은 trace에 묶인다.
        blocks = []
        for item in state["results"]:
            blocks.append(f"[{item['analyst']} 분석가 결과]\n{item['text']}")
        body = "질문: " + state["question"] + "\n\n" + "\n\n".join(blocks)

        # 검증에서 되돌아온 경우: 이전 답과 지적 사항을 함께 줘서 고쳐 쓰게 한다. 처음에는 feedback이 비어 있다.
        if state.get("feedback"):
            body += "\n\n[이전 답]\n" + state["answer"]
            body += "\n\n[검증자 지적 사항 - 숫자는 분석가 결과에 있는 것만 쓰고, 지적된 부분을 고쳐 다시 쓰세요]\n" + state["feedback"]

        messages = [
            SystemMessage(content=SYNTH_PROMPT),
            HumanMessage(content=body),
        ]
        response = synth_model.invoke(messages, config)
        return {"answer": text_of(response.content)}

    graph = StateGraph(TeamState)
    graph.add_node("supervisor", supervisor.supervisor_node)
    graph.add_node("analyst_run", analyst_run)
    graph.add_node("decline", decline_node)
    graph.add_node("synthesize", synthesize)

    graph.add_edge(START, "supervisor")
    # 갈림길 도착지를 목록으로 알려 줘야 다이어그램에 선이 그려진다(Send는 실행 때 정해져서 그림에 안 나온다).
    graph.add_conditional_edges("supervisor", route_after_supervisor, ["analyst_run", "decline"])
    if approval:
        sys.path.insert(0, "src/phase5")
        from approve import approve_node

        graph.add_node("approve", approve_node)
        graph.add_edge("analyst_run", "approve")
        graph.add_conditional_edges("approve", route_after_approve, {"synthesize": "synthesize", "end": END})
    else:
        graph.add_edge("analyst_run", "synthesize")
    graph.add_edge("decline", END)
    if verify:
        # 검증: 취합 뒤 검증자 둘이 병렬로 판정(Send) -> judge가 합침 -> 통과면 끝, 실패면 취합으로 되돌림.
        sys.path.insert(0, "src/phase5")
        import verify as verify_module

        if verifiers is None:
            verifiers = verify_module.build_verifiers()
        graph.add_node("verify_one", verify_module.build_verify_one(verifiers))
        graph.add_node("judge", verify_module.judge)
        graph.add_conditional_edges("synthesize", verify_module.route_to_verifiers, ["verify_one"])
        graph.add_edge("verify_one", "judge")
        graph.add_conditional_edges("judge", verify_module.route_after_judge, {"synthesize": "synthesize", "end": END})
    else:
        graph.add_edge("synthesize", END)
    return graph.compile(checkpointer=checkpointer)


if __name__ == "__main__":
    import json
    from datetime import datetime

    from observe import flush, make_config

    # 질문은 실행할 때 뒤에 붙여 줄 수 있다: uv run python src/phase4/graph.py "질문"
    # 안 붙이면 아래 기본 질문을 쓴다. sys.argv[0]은 파일 이름이고 [1]부터가 넘겨 준 값이다.
    if len(sys.argv) > 1:
        question = sys.argv[1]
    else:
        question = "병목이 많은 곳을 알려 주고 센터는 어디에 두면 좋을까요?"

    app = build_team_graph()

    # 실행 한 번에 config를 한 번만 만든다. 그래야 supervisor, 분석가들, 취합 호출이 Langfuse에서 한 trace로 묶인다.
    config = make_config()

    initial_state = {"question": question, "selected": [], "results": [], "answer": ""}
    final_state = app.invoke(initial_state, config)

    # 짧게 끝나는 스크립트는 기록을 서버로 보내기 전에 끝날 수 있어 비워 준다.
    flush()

    print("질문:", final_state["question"])
    print("supervisor가 고른 분석가:", final_state["selected"])
    for item in final_state["results"]:
        print(f"\n--- {item['analyst']} 분석가 결과 ---")
        print(item["text"])
    print("\n=== 최종 답 ===")
    print(final_state["answer"])

    # 결과를 data/에 저장한다. 실행마다 파일 이름이 달라지도록 시각을 붙인다.
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_path = f"data/phase4_team_{stamp}.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(final_state, f, ensure_ascii=False, indent=1)
    print("\n저장:", out_path)
