import json
import re
import sys

from langchain_core.messages import HumanMessage, SystemMessage

sys.path.insert(0, "src/phase3")
sys.path.insert(0, "src/phase4")
from agent_tools import TOOLS_BY_ANALYST
from analyst import build_base_model

ANALYST_NAMES = list(TOOLS_BY_ANALYST.keys())

# 분석가 설명: 하는 일, 답할 수 있는 질문의 예, 맡지 않는 것. supervisor가 이 설명만 보고 분석가를 고르므로
# 서로 겹쳐 보이는 경계(전체 물동량 vs 컨테이너, 집중도 vs 센터 비용)를 '맡지 않는 것'에 적어 둔다.
ANALYST_DESCRIPTIONS = {
    "concentration": {
        "role": "전체 도로 물동량이 어느 지역에 몰려 있는지 순위를 내는 분석가. 도로 용량은 반영하지 않아 '병목'이 아니라 '물동량 집중도'를 본다.",
        "examples": "물동량이 가장 많이 몰린 곳은? / 병목 후보 지역은? / 물류가 집중된 지역 상위 10곳",
        "not": "센터 입지나 운송비 비교, 컨테이너만의 순위, 수송수단(철도·항공) 비중은 맡지 않는다.",
    },
    "location": {
        "role": "물류센터를 특정 지역에 두었을 때의 연간 운송비·평균 운송 거리·전국 순위를 계산하고, 후보지끼리 비교하거나 249곳 전체 중 운송비가 낮은 곳을 찾는 분석가. 지역 이름을 존 번호로 바꾸는 일도 한다.",
        "examples": "광양시에 센터를 두면 운송비는? / 청주와 광양 중 센터는 어디가 유리한가? / 센터를 어디에 두면 운송비가 가장 낮은가?",
        "not": "물동량이 몰린 지역 찾기, 컨테이너나 철도 비중 분석은 맡지 않는다. 운송비는 센터 한 곳이 전국 수요를 직선 거리로 공급한다는 가정의 계산이고 도로 용량·토지·임대료는 반영하지 않는다.",
    },
    "mode": {
        "role": "도로·철도·항공 수송수단별 물량과 비중을 분석하는 분석가(2024년만). 특정 지역의 수송수단 구성과, 철도 비중이 높은 지역 순위를 낸다.",
        "examples": "철도 화물 비중이 높은 지역은? / 광양시의 도로·철도 구성은? / 철도로 연계할 만한 지역은?",
        "not": "철도역·화물 터미널 위치는 모른다. 센터 운송비, 전체 물동량 순위, 컨테이너 순위는 맡지 않는다.",
    },
    "container": {
        "role": "도로 컨테이너 물동량이 어느 지역에 몰려 있는지 순위를 내는 분석가. 항만·수출 거점을 찾는 질문의 재료가 된다. 항만 터미널 위치나 처리 능력은 모른다.",
        "examples": "컨테이너가 가장 몰린 곳은? / 수출용 컨테이너 물량이 많은 지역은? / 항만 주변 컨테이너 물동량 상위 지역",
        "not": "컨테이너가 아닌 전체 물동량 순위, 센터 운송비, 철도 비중은 맡지 않는다.",
    },
    "road_load": {
        "role": "도로 링크(구간) 중 화물차 부하가 큰 곳의 순위를 내는 분석가. 화물차 OD를 도로망에 얹은 값이라 어느 도로 구간에 화물차가 몰리는지 본다. 승용차는 빠져 있어 실제 정체 여부는 모른다.",
        "examples": "화물차가 가장 몰리는 도로는? / 고속도로 중 화물 부하가 큰 구간은? / 도로 용량 관점에서 화물이 몰리는 곳은?",
        "not": "지역(존) 단위 물동량 순위, 센터 운송비, 컨테이너·철도 분석은 맡지 않는다. 실제 정체·병목 판정은 하지 못한다.",
    },
}

assert set(ANALYST_DESCRIPTIONS) == set(ANALYST_NAMES), "분석가 설명과 도구 묶음의 이름이 어긋남"


def build_supervisor_prompt():
    # 분석가 설명 딕셔너리로 supervisor 지시문을 만든다. 설명을 고치면 지시문이 같이 바뀐다.
    blocks = []
    for name in ANALYST_NAMES:
        d = ANALYST_DESCRIPTIONS[name]
        blocks.append(f"[{name}]\n역할: {d['role']}\n답할 수 있는 질문 예: {d['examples']}\n맡지 않는 것: {d['not']}")
    analyst_text = "\n\n".join(blocks)

    # 이 모델은 강제 도구 호출(tool_choice의 any/tool)이 400이라서, 구조화된 출력 대신 JSON 텍스트로 답하게 하고 코드가 읽는다.
    return f"""당신은 물류 분석팀의 supervisor입니다. 사용자 질문을 읽고 어떤 분석가에게 맡길지 고릅니다. 직접 답하지 마세요.

분석가 목록:

{analyst_text}

고르는 규칙:
- 질문에 답하려면 필요한 분석가를 모두 고르세요. 질문 하나에 분석가가 여럿 필요할 수 있습니다(예: 병목 후보를 찾고 센터 위치도 묻는 질문).
- 질문과 상관없는 분석가는 넣지 마세요. 어느 분석가도 맡을 수 없는 질문이면 빈 목록을 돌려주세요.
- 질문이 전체 물동량인지 컨테이너인지 분명하지 않으면 '맡지 않는 것'을 보고 가까운 쪽을 고르세요.
답은 JSON 한 줄만 쓰세요. 예: {{"analysts": ["location", "container"]}}"""


SUPERVISOR_PROMPT = build_supervisor_prompt()


def parse_selection(text):
    # 모델 답 텍스트에서 JSON을 찾아 분석가 이름 목록으로 바꾼다. 형식이 어긋나도 프로그램이 죽지 않게 방어한다.
    # 모델이 JSON 앞뒤에 설명을 붙일 수 있어서, 텍스트 안의 첫 {...} 덩어리만 꺼낸다.
    match = re.search(r"\{.*?\}", text, re.DOTALL)
    if match is None:
        return []
    try:
        data = json.loads(match.group(0))
    except json.JSONDecodeError:
        return []

    names = data.get("analysts", [])
    if not isinstance(names, list):
        return []

    # 없는 이름은 버리고, 같은 이름이 두 번 나오면 한 번만 남긴다(순서는 유지).
    selected = []
    for name in names:
        if name in ANALYST_NAMES and name not in selected:
            selected.append(name)
    return selected


# 도구를 붙이지 않은 모델. 모듈이 불러와질 때 한 번만 만든다(네트워크 호출 없음).
MODEL = build_base_model()


def supervisor_node(state):
    # 노드: 상태에서 질문을 읽어 모델에게 분석가 선택을 맡기고, 고른 분석가 이름 목록을 상태에 적는다.
    # 여기서 모델을 1회 호출한다(비용 발생). 상태는 {"question": 문자열, "selected": 목록}으로 가정한다.
    messages = [SystemMessage(content=SUPERVISOR_PROMPT), HumanMessage(content=state["question"])]
    response = MODEL.invoke(messages)

    # 응답 content는 문자열이거나, 블록 목록(예: thinking 블록 + text 블록)일 수 있다. 문자열로 모은다.
    if isinstance(response.content, str):
        text = response.content
    else:
        text = ""
        for block in response.content:
            if isinstance(block, dict) and block.get("type") == "text":
                text += block["text"]

    return {"selected": parse_selection(text)}


if __name__ == "__main__":
    # 모델 없이 지시문과 파싱을 확인한다(비용 없음).
    print(SUPERVISOR_PROMPT)
    print("--- 지시문", len(SUPERVISOR_PROMPT), "자\n")
    # 일부러 어긋난 답도 넣는다.
    cases = [
        '{"analysts": ["location", "container"]}',
        '선택 결과입니다.\n{"analysts": ["mode"]}\n이상입니다.',
        '{"analysts": ["location", "location", "weather"]}',
        '{"analysts": []}',
        '{"analysts": "location"}',
        "JSON 없이 그냥 문장으로 답함",
        '{"analysts": ["location"',
    ]
    for text in cases:
        print(repr(text[:40]), "->", parse_selection(text))
