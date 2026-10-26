from langgraph.types import interrupt


def approve_node(state):
    # 분석가 결과를 사람에게 보여 주고 승인을 기다리는 노드.
    # interrupt(값)을 부르면 그래프가 여기서 멈추고, 지금까지의 상태가 체크포인트에 저장된다.
    # 바깥에는 '값'이 전달된다(아래 payload). 나중에 Command(resume=응답)으로 이어 가면
    # 이 노드가 처음부터 다시 실행되고, 이번에는 interrupt()가 멈추지 않고 그 '응답'을 돌려준다.
    # (그래서 interrupt 앞에는 다시 실행해도 문제 없는 코드만 둔다. 지금은 읽기만 한다.)
    payload = {
        "question": state["question"],
        "results": state["results"],
        "message": "분석가 결과를 확인하고 승인하면 취합을 진행합니다.",
    }
    reply = interrupt(payload)

    # reply는 사람이 넘긴 값이다. "yes"면 승인, 그 밖이면 거절로 본다.
    if reply == "yes":
        return {"approved": True}

    return {
        "approved": False,
        "answer": "사람이 분석가 결과를 승인하지 않아 취합하지 않았습니다.",
    }
