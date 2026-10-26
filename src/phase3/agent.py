import sys

from dotenv import load_dotenv
from langchain_anthropic import ChatAnthropic
from langgraph.graph import END, START, MessagesState, StateGraph
from langgraph.prebuilt import ToolNode

sys.path.insert(0, "src/phase3")
from agent_tools import ALL_TOOLS

MODEL_NAME = "claude-sonnet-5-5"


def build_model():
    # .env 파일의 ANTHROPIC_API_KEY를 환경 변수로 읽어 들인다. ChatAnthropic이 이 변수를 알아서 쓴다.
    load_dotenv()

    # thinking이 켜져 있어서 max_tokens가 작으면 생각만 하다가 텍스트가 빈 응답이 나올 수 있다. 넉넉히 둔다.
    model = ChatAnthropic(model=MODEL_NAME, max_tokens=4096)

    # bind_tools: 모델에게 "이 도구들을 쓸 수 있다"는 설명서(이름, 독스트링, 입력 형식)를 붙인 새 모델 객체를 돌려준다.
    # 도구를 실행해 주는 것은 아니다. 모델은 "이 도구를 이 인자로 불러 달라"는 요청만 응답에 담는다.
    # tool_choice는 지정하지 않는다(auto). 이 모델은 강제 호출이 400 오류가 난다.
    return model.bind_tools(ALL_TOOLS)


# 모듈이 불러와질 때 한 번만 만든다(네트워크 호출 없음). 노드 함수가 호출될 때마다 새로 만들지 않기 위해서다.
MODEL = build_model()


def call_model(state):
    # 노드: 상태(MessagesState)를 받는다. state["messages"]는 지금까지의 대화 목록이다
    # (사용자 질문, 모델 응답, 도구 결과가 순서대로 쌓인 목록).
    history = state["messages"]

    # 대화 전체를 모델에 보내고 응답 메시지 하나(AIMessage)를 받는다. 여기서 비용이 든다.
    # 응답에는 최종 답 텍스트가 있거나, 도구를 불러 달라는 요청(tool_calls)이 있다.
    response = MODEL.invoke(history)

    # MessagesState의 messages는 돌려준 값으로 덮어쓰지 않는다.
    # 이 필드는 '덮어쓰기'가 아니라 '목록 뒤에 붙이기'로 합쳐지도록 정의되어 있다(add_messages).
    # 그래서 새 응답 하나만 리스트에 담아 돌려주면, 기존 대화 뒤에 붙는다.
    return {"messages": [response]}


def should_use_tools(state):
    # 조건부 엣지: 방금 모델이 낸 응답(대화의 마지막 메시지)을 보고 다음에 갈 곳의 '라벨'을 돌려준다.
    last = state["messages"][-1]

    # 모델이 도구를 불러 달라고 요청했으면 tool_calls에 요청 목록이 들어 있다. 요청이 없으면 빈 목록이다.
    # 빈 목록은 if 조건에서 False로 취급된다.
    if last.tool_calls:
        return "use tools"
    return "answer"


def build_graph():
    # MessagesState: 'messages' 필드 하나(대화 목록, 붙이기 방식)를 가진 LangGraph 기본 상태.
    graph = StateGraph(MessagesState)

    graph.add_node("model", call_model)
    # ToolNode: 마지막 모델 응답의 tool_calls를 읽어 해당 도구를 실행하고, 결과를 ToolMessage로 messages에 붙여 준다.
    graph.add_node("tools", ToolNode(ALL_TOOLS))

    graph.add_edge(START, "model")
    # model 노드가 끝나면 should_use_tools가 돌려준 라벨에 따라 도구 실행 또는 종료로 갈라진다.
    graph.add_conditional_edges("model", should_use_tools, {"use tools": "tools", "answer": END})
    # 도구 결과를 받은 모델이 다시 판단해야 하므로 tools에서 model로 되돌아간다. 이 되돌림이 루프다.
    graph.add_edge("tools", "model")
    return graph.compile()


if __name__ == "__main__":
    # 모델 호출 없이 그래프 모양만 그린다(비용 없음).
    from draw import save_png

    app = build_graph()
    save_png(app, "data/agent_graph.png", "tool-calling agent")
