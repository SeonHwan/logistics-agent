import json
import sys
from datetime import datetime

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.types import Command

sys.path.insert(0, "src/phase4")
from graph import build_team_graph
from observe import flush, make_config

# 사용법 (프로젝트 루트에서, 한 번만 실행한다):
#   uv run python src/phase5/run_approval.py "질문"
# 분석가가 끝나면 결과를 보여 주고 터미널에서 승인을 묻는다. yes를 입력하면 취합까지 이어서 진행한다.


def print_pending(snapshot):
    # 멈춘 지점의 정보를 보여 준다. snapshot.interrupts는 approve 노드의 interrupt()가 바깥에 낸 값이다.
    for item in snapshot.interrupts:
        payload = item.value
        print("질문:", payload["question"])
        for result in payload["results"]:
            print(f"\n--- {result['analyst']} 분석가 결과 ---")
            print(result["text"])
        print("\n" + payload["message"])


def main():
    if len(sys.argv) > 1:
        question = sys.argv[1]
    else:
        question = "병목이 많은 곳을 알려 주고 센터는 어디에 두면 좋을까요?"

    # InMemorySaver: 체크포인트를 메모리에 둔다. 이 프로세스가 살아 있는 동안만 유지되며, 승인을 이 실행 안에서 받으므로 충분하다.
    # interrupt()는 상태를 저장해 둘 체크포인터가 있어야 쓸 수 있다.
    app = build_team_graph(checkpointer=InMemorySaver(), approval=True, verify=True)

    # thread_id는 체크포인트의 저장 키다. 실행 한 번에 하나뿐이라 고정값으로 둔다.
    config = make_config()
    config["configurable"] = {"thread_id": "run"}

    # 1) 승인 노드에서 멈출 때까지 실행한다.
    initial_state = {
        "question": question, "selected": [], "results": [], "answer": "", "approved": False,
        "verdicts": [], "history": [], "retries": 0, "feedback": "", "passed": False,
    }
    final_state = app.invoke(initial_state, config)

    # 2) 멈췄는지 본다. next가 비어 있으면 승인 노드를 거치지 않고 끝난 것이다(분석가를 못 골라 decline으로 간 경우).
    snapshot = app.get_state(config)
    if snapshot.next:
        print_pending(snapshot)
        reply = input("\n승인하시겠습니까? yes를 입력하면 승인, 그 밖은 거절: ").strip()

        # 3) 사람의 응답을 넘겨 이어 간다. approve 노드가 처음부터 다시 실행되고, interrupt()가 reply를 돌려준다.
        final_state = app.invoke(Command(resume=reply), config)

    flush()

    # 검증 결과: 승인 거절이나 decline 경로에서는 검증을 거치지 않아 passed가 False로 남는다.
    print("\n검증 통과:", final_state["passed"], "/ 되돌린 횟수:", final_state["retries"])
    for record in final_state["history"]:
        for verdict in record["verdicts"]:
            print(f"\n[라운드 {record['round']}] {verdict['verifier']}: ok={verdict['ok']}")
            print("  사유:", verdict["reason"])
            for issue in verdict["issues"]:
                print("  지적:", issue)
    if final_state["feedback"]:
        print("\n마지막 지적 사항:\n" + final_state["feedback"])

    print("\n=== 최종 답 ===")
    print(final_state["answer"])

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_path = f"data/phase5_{stamp}.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(final_state, f, ensure_ascii=False, indent=1)
    print("\n저장:", out_path)


main()
