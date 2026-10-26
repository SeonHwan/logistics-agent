import sys

from langchain_core.tools import tool

sys.path.insert(0, "src/phase2")
import tools as calc


@tool
def list_zones(keyword: str) -> list:
    """존(시·군·구) 이름에 keyword가 들어간 존을 찾아 존 번호를 알려 줍니다.
    다른 도구는 이름이 아니라 존 번호를 받으므로, 지역 이름이 나오면 먼저 이 도구로 번호를 찾으세요.
    keyword는 '광양', '청주'처럼 짧게 쓰세요. 결과의 has_coord가 false인 존(울릉군, 제주시, 서귀포시)은 거리 계산을 할 수 없습니다."""
    return calc.list_zones(keyword)


@tool
def zone_concentration(year: int = 2024, top_n: int = 10) -> dict:
    """물동량이 많이 몰린 존의 순위를 알려 줍니다. 존마다 (들어오는 양 + 나가는 양)을 존 평균과 비교한 배수를 돌려줍니다.
    이것은 도로 용량 대비 혼잡이 아니라 물동량 집중도입니다. 병목이라고 단정하지 말고 '물동량이 몰린 곳'이라고 말하세요.
    year는 2024, 2025, 2030, 2035, 2040, 2045, 2050 중 하나입니다. 2024(기준년도)와 2025 이후(장래년도)는 서로 다른 자료라 증가율을 계산하지 마세요."""
    return calc.zone_concentration(year=year, top_n=top_n)


@tool
def center_cost(center_zone: int, year: int = 2024) -> dict:
    """물류센터 한 곳을 center_zone(존 번호)에 두고 전국 수요를 공급할 때의 연간 총 운송비(조 원)와 평균 운송 거리(km)를 계산합니다.
    249개 후보 존 중 몇 위인지도 알려 줍니다. 비용이 낮을수록 순위가 높습니다.
    직선 거리와 하한 단가로 계산해서 절대 금액은 낮게 나옵니다. 후보끼리의 상대 비교에만 쓰세요.
    존 번호를 모르면 먼저 list_zones로 찾으세요."""
    return calc.center_cost(center_zone, year=year)


@tool
def best_centers(year: int = 2024, top_n: int = 5) -> dict:
    """물류센터 후보 249곳 전체를 계산해, 연간 총 운송비가 가장 낮은 존을 top_n곳 순위로 알려 줍니다.
    '어디에 두는 게 가장 좋은가'처럼 후보 이름이 정해지지 않은 질문에 쓰세요. 가장 높은 후보의 운송비도 함께 돌려줍니다.
    센터 한 곳이 전국 수요를 직선 거리로 공급하는 가정이라 지리적 중앙이 유리한 것이 거의 당연한 결과입니다. 실제 입지 판단이 아니라고 밝히세요.
    직선 거리와 하한 단가로 계산해 절대 금액은 낮게 나오니 후보끼리의 상대 비교에만 쓰세요. 도로 용량·토지·임대료는 반영하지 않습니다.
    year는 2024, 2025, 2030, 2035, 2040, 2045, 2050 중 하나이며, 2024와 2025 이후는 서로 다른 자료라 증가율을 계산하지 마세요."""
    return calc.best_centers(year=year, top_n=top_n)


@tool
def container_hubs(year: int = 2024, top_n: int = 10) -> dict:
    """도로 컨테이너 물동량이 많이 몰린 존의 순위를 알려 줍니다. 존마다 (들어오는 컨테이너 + 나가는 컨테이너)를 존 평균과 비교한 배수입니다.
    같은 존 안에서 도는 물량은 빠져 있고, 항만·철도 컨테이너 터미널의 위치나 처리 능력은 반영하지 않습니다.
    '항만이다' 또는 '수출 거점이다'라고 단정하지 말고 '도로 컨테이너 물동량이 몰린 곳'이라고 말하세요.
    year는 2024, 2025, 2030, 2035, 2040, 2045, 2050 중 하나이며, 2024와 2025 이후는 서로 다른 자료라 증가율을 계산하지 마세요."""
    return calc.container_hubs(year=year, top_n=top_n)


@tool
def mode_share(zone_id: int = None, top_n: int = 10) -> dict:
    """도로·철도·항공 수송수단별 물량과 비중을 알려 줍니다. 2024년 자료만 있습니다.
    zone_id(존 번호)를 주면 그 존의 수송수단별 물량(만톤)과 철도·항공 비중을 돌려주고,
    zone_id를 생략하면 철도 비중이 높은 존 순위(top_n개)를 돌려줍니다.
    철도 비중이 높다는 것은 물량이 철도로 많이 간다는 뜻일 뿐, 철도역이나 화물 터미널이 가깝다는 뜻이 아닙니다. '철도 연계가 가능하다'고 단정하지 마세요.
    존 번호를 모르면 먼저 list_zones로 찾으세요."""
    return calc.mode_share(zone_id=zone_id, top_n=top_n)


@tool
def road_load(top_n: int = 10, road_type: int = None) -> dict:
    """도로 링크 중 화물차 부하(승용차환산대수/일)가 큰 곳의 순위를 알려 줍니다. 2024년 화물차 OD를 도로망의 최단경로 하나에 전부 얹어 계산한 값입니다.
    각 링크의 도로등급, 차로수, 가장 가까운 존 이름, 부하를 돌려줍니다. road_type을 주면 그 등급만 봅니다(101 고속국도, 102 도시고속화도로, 103 일반국도, 104 특별·광역시도, 105 국가지원지방도, 106 지방도, 107 시군도, 108 연결램프).
    화물차만 반영하고 승용차·버스는 빠져 있으며 혼잡에 따라 경로를 바꾸지 않으므로, 이것은 '화물차가 몰리는 길의 순위'일 뿐 실제로 막히는 곳이 아닙니다. '병목'이라고 단정하지 마세요.
    '용량 대비 비율'은 용량 단위와 첨두율이 추정이라 참고로만 보고, 비율 값을 근거로 막힌다·안 막힌다고 말하지 마세요. 가까운 존은 위치를 가늠하는 용도이고 링크가 그 존에 속한다는 뜻이 아닙니다."""
    return calc.road_load(top_n=top_n, road_type=road_type)


@tool
def road_load_by_zone(top_n: int = 10) -> dict:
    """존 단위로 묶어, 존 근처 도로 링크 중 화물차 부하가 가장 큰 링크의 부하로 존 순위를 알려 줍니다. 같은 길이 링크 여러 개로 쪼개져 있어 링크 순위에 같은 길이 여러 번 나올 때 쓰면 좋습니다.
    road_load와 같은 한계를 가집니다: 화물차만 반영, 전량 배정, 실제 혼잡·정체가 아니라 화물차가 몰리는 길의 순위입니다. '병목'이라고 단정하지 마세요."""
    return calc.road_load_by_zone(top_n=top_n)


ALL_TOOLS = [list_zones, zone_concentration, center_cost, best_centers, container_hubs, mode_share, road_load, road_load_by_zone]

# 분석가마다 필요한 도구만 준다. 도구가 적을수록 모델이 고르기 쉽고, 각 분석가의 역할이 분명해진다.
TOOLS_BY_ANALYST = {
    "concentration": [zone_concentration, list_zones],
    "location": [list_zones, center_cost, best_centers],
    "mode": [list_zones, mode_share],
    "container": [list_zones, container_hubs],
    "road_load": [list_zones, road_load, road_load_by_zone],
}


if __name__ == "__main__":
    # 모델에게 보이는 도구 설명서(이름, 설명 첫 줄, 입력 형식)를 확인하고, 모델 없이 도구를 직접 한 번씩 부른다.
    for t in ALL_TOOLS:
        print(f"[{t.name}] 입력 형식: {t.args}")
        print("   설명 첫 줄:", t.description.splitlines()[0])
    print()
    print(list_zones.invoke({"keyword": "광양"}))
    print(center_cost.invoke({"center_zone": 187}))
    print(container_hubs.invoke({"top_n": 2})["top"])
    print(mode_share.invoke({"zone_id": 187})["철도 비중(%)"])
    for name, tools in TOOLS_BY_ANALYST.items():
        print(name, [t.name for t in tools])
