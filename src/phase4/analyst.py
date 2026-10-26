import sys

from dotenv import load_dotenv
from langchain_anthropic import ChatAnthropic
from langchain_core.messages import SystemMessage
from langgraph.graph import END, START, MessagesState, StateGraph
from langgraph.prebuilt import ToolNode

sys.path.insert(0, "src/phase3")
from agent_tools import TOOLS_BY_ANALYST

MODEL_NAME = "claude-sonnet-5-5"


def build_base_model():
    # 도구를 붙이지 않은 모델. 분석가마다 도구가 다르므로 도구는 분석가를 만들 때 붙인다.
    load_dotenv()
    return ChatAnthropic(model=MODEL_NAME, max_tokens=4096)


# 분석가별 역할 지시문. 공통 규칙(근거는 도구 결과만, 한계 말하기)과 분석가별 한계 문구를 함께 둔다.
# 한계 문구는 각 도구의 독스트링과 겹치지만, 역할 단위로 한 번 더 못 박아 둔다.
COMMON_RULES = """당신은 물류 데이터 분석가입니다. 맡은 범위의 질문에만 답하고, 숫자는 반드시 도구 결과에서 가져오세요.
도구 결과에 없는 내용은 추측이라고 밝히세요. 지역 이름이 나오면 list_zones로 존 번호를 먼저 찾고, 이름이 여럿에 해당하면 임의로 고르지 말고 후보를 함께 알려 주세요.
자신이 가진 도구로 할 수 없는 분석(도구에 없는 계산, 다른 분석가의 범위)은 해 주겠다고 제안하지 마세요. 그런 분석이 필요하면 '이 도구로는 할 수 없다'고만 말하세요.
답은 요점 위주로 짧게 쓰고, 마지막에 이 결과의 한계를 한두 문장으로 적으세요."""

ROLE_PROMPTS = {
    "concentration": COMMON_RULES + """
당신의 범위는 물동량 집중도입니다. 이것은 병목이 아니라 '물동량이 몰린 곳'입니다. 도로 용량이 반영되지 않았다는 점을 밝히세요.""",
    "location": COMMON_RULES + """
당신의 범위는 물류센터 후보지의 운송비 비교입니다. 직선 거리와 하한 단가로 계산해 절대 금액은 낮게 나오므로 후보끼리의 상대 비교로만 말하세요.
센터 한 곳이 전국 수요를 공급하는 가정의 결과이며 실제 입지 판단이 아니라는 점을 밝히세요.""",
    "mode": COMMON_RULES + """
당신의 범위는 도로·철도·항공 수송수단별 물량 비중입니다(2024년만). 철도 비중이 높다는 것은 물량이 철도로 많이 간다는 뜻이지,
철도역이나 화물 터미널이 가깝다는 뜻이 아닙니다. '철도 연계가 가능하다'고 단정하지 마세요.""",
    "container": COMMON_RULES + """
당신의 범위는 도로 컨테이너 물동량이 몰린 곳입니다. 항만·수출 거점이라고 단정하지 말고 '도로 컨테이너 물동량이 몰린 곳'이라고 말하세요.
같은 존 안에서 도는 물량과 철도 컨테이너는 빠져 있다는 점을 밝히세요.""",
    "road_load": COMMON_RULES + """
당신의 범위는 도로 링크의 화물차 부하 순위입니다(2024년). 화물차 OD를 최단경로 하나에 전부 얹은 값이므로 '화물차가 몰리는 길의 순위'이지 실제로 막히는 곳이 아닙니다.
'병목', '정체', '혼잡'이라고 단정하지 말고 '화물차 부하가 큰 도로'라고 말하세요. 승용차·버스가 빠져 있고 혼잡에 따른 경로 변경이 없다는 점을 밝히세요.
'용량 대비 비율'은 단위와 방법이 확정되지 않은 참고값이니 그 값으로 막힌다·안 막힌다를 말하지 마세요. 가까운 존은 위치를 가늠하는 용도이며 링크가 그 존에 속한다는 뜻이 아닙니다.""",
}


def build_analyst(tools, role_prompt):
    # 분석가 한 명 = '모델 <-> 도구' 루프를 도구 묶음과 역할 지시문만 바꿔 만든 작은 그래프(서브그래프).
    # 아래 call_model, should_use_tools는 함수 안에 정의한 함수다. 바깥 함수의 변수(model, role_prompt)를 그대로 쓸 수 있다.
    model = build_base_model().bind_tools(tools)

    def call_model(state):
        # 역할 지시문(SystemMessage)을 대화 맨 앞에 붙여 모델에 보낸다.
        # 지시문은 상태(messages)에 저장하지 않는다. 호출할 때마다 앞에 붙이기만 하므로 대화 기록은 지시문 없이 쌓인다.
        history = [SystemMessage(content=role_prompt)] + state["messages"]
        response = model.invoke(history)
        return {"messages": [response]}

    def should_use_tools(state):
        # 마지막 응답에 도구 요청이 있으면 도구 실행, 없으면 끝.
        if state["messages"][-1].tool_calls:
            return "use tools"
        return "answer"

    graph = StateGraph(MessagesState)
    graph.add_node("model", call_model)
    graph.add_node("tools", ToolNode(tools))
    graph.add_edge(START, "model")
    graph.add_conditional_edges("model", should_use_tools, {"use tools": "tools", "answer": END})
    graph.add_edge("tools", "model")
    return graph.compile()


def build_all_analysts():
    # 분석가 이름 -> 컴파일된 그래프 딕셔너리.
    analysts = {}
    for name, tools in TOOLS_BY_ANALYST.items():
        analysts[name] = build_analyst(tools, ROLE_PROMPTS[name])
    return analysts


if __name__ == "__main__":
    # 모델 호출 없이 4명을 조립만 해 본다(비용 없음).
    assert set(ROLE_PROMPTS) == set(TOOLS_BY_ANALYST), "도구 묶음과 지시문의 분석가 이름이 어긋남"
    analysts = build_all_analysts()
    for name, analyst in analysts.items():
        print(name, "도구:", [t.name for t in TOOLS_BY_ANALYST[name]], "| 지시문", len(ROLE_PROMPTS[name]), "자")
