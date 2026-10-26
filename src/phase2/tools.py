import sys

import pandas as pd

sys.path.insert(0, "src/phase2")
from cost import DEFAULT_UNIT_COST
from location import evaluate_candidates

# 에이전트가 부를 계산 도구 모음. 모델은 계산하지 않고 이 함수들을 호출해 숫자를 받는다.
# 모든 함수는 숫자와 함께 "무엇을 가정했는지"를 같이 돌려준다.

ZONES = pd.read_parquet("data/clean/zones.parquet")
DIST = pd.read_parquet("data/clean/distance.parquet")
FLOWS = pd.read_parquet("data/clean/zone_flows.parquet")
ROAD_YEARS = sorted(FLOWS["year"].unique().tolist())


def _zone_totals(path, ton_column):
    # OD 표(출발, 도착, 톤)에서 존마다 나가는 양·들어오는 양을 구한다. 같은 존 안 이동은 제외한다(zone_flows와 같은 정의).
    od = pd.read_parquet(path, columns=["o_zone", "d_zone", ton_column])
    od = od[od["o_zone"] != od["d_zone"]]
    out_ton = od.groupby("o_zone")[ton_column].sum()
    in_ton = od.groupby("d_zone")[ton_column].sum()
    return (out_ton.add(in_ton, fill_value=0)).rename("ton")


# 수송수단별 (출발 + 도착) 물량. 기준년도 2024 파일만 쓴다. 장래년도 파일은 기준년도와 이어지지 않는다.
MODE_TOTALS = pd.concat({
    "도로": _zone_totals("data/clean/road_ton_2024.parquet", "전체"),
    "철도": _zone_totals("data/clean/rail_2024.parquet", "전체"),
    "항공": _zone_totals("data/clean/air_2024.parquet", "항공화물(톤/년)"),
}, axis=1).fillna(0)

ASSUMPTIONS = {
    "도로 물동량": "KTDB 2025 화물OD(톤/년, 도로 전체). 기준년도 2024와 장래년도(2025~2050)는 서로 다른 파일이라 한 시계열로 잇지 않음",
    "거리": "존 중심 좌표 간 직선 거리(우회 계수 기본 1.0). 실제 도로 거리보다 짧음",
    "단가": "2025 안전운송원가 25톤 777원/km ÷ 25톤 = 약 31.08원/톤·km (적재율 100% 가정의 하한 추정)",
    "제외": "좌표 없는 존 3개(울릉군, 제주시, 서귀포시) 제외",
}


def _name_of(zone_id):
    return ZONES.loc[ZONES["zone_id"] == zone_id, "name"].iloc[0]


def list_zones(keyword):
    # 이름에 keyword가 들어간 존을 찾아 [{zone_id, name, has_coord}] 목록으로 돌려준다.
    found = ZONES[ZONES["name"].str.contains(keyword, regex=False)]
    result = []
    for row in found.itertuples():
        result.append({"zone_id": int(row.zone_id), "name": row.name, "has_coord": bool(row.has_coord)})
    return result


def zone_concentration(year=2024, top_n=10):
    # 병목의 약한 정의: 존의 (들어오는 양 + 나가는 양)이 존 평균의 몇 배인가.
    # 도로 용량이 없어서 '용량 대비 혼잡'은 아니다. 물동량이 몰린 정도만 본다.
    if year not in ROAD_YEARS:
        raise ValueError(f"연도는 {ROAD_YEARS} 중 하나여야 합니다: {year}")
    f = FLOWS[FLOWS["year"] == year].copy()
    f["through_ton"] = f["in_ton"] + f["out_ton"]
    mean_value = f["through_ton"].mean()
    f["ratio"] = f["through_ton"] / mean_value

    top = f.nlargest(top_n, "through_ton")
    rows = []
    for row in top.itertuples():
        rows.append({
            "zone_id": int(row.zone_id), "name": _name_of(row.zone_id),
            "in_만톤": round(row.in_ton / 1e4), "out_만톤": round(row.out_ton / 1e4),
            "평균 대비 배수": round(row.ratio, 1),
        })
    return {"year": year, "top": rows, "평균(만톤)": round(mean_value / 1e4),
            "정의": "병목이 아니라 물동량 집중도(도로 용량 미반영)", "가정": ASSUMPTIONS}


def center_cost(center_zone, year=2024, unit_cost=DEFAULT_UNIT_COST, detour=1.0):
    # 센터 한 곳을 center_zone에 두고 전국 수요(도착 기준)를 공급할 때의 운송비.
    f = FLOWS[FLOWS["year"] == year].set_index("zone_id")
    have = set(ZONES.loc[ZONES["has_coord"], "zone_id"])
    if center_zone not in have:
        raise ValueError(f"존 {center_zone}은 좌표가 없어 계산할 수 없습니다")
    demand = {}
    for z in have:
        demand[int(z)] = float(f.loc[z, "in_ton"] + f.loc[z, "inner_ton"])
    table = evaluate_candidates(demand, DIST, unit_cost=unit_cost, detour=detour)
    row = table[table["center_zone"] == center_zone].iloc[0]
    rank = int(table.index[table["center_zone"] == center_zone][0]) + 1
    # numpy 숫자를 파이썬 기본 숫자로 바꾼다(float()). 에이전트에 JSON으로 넘길 때 직렬화 오류를 막는다.
    return {"center": _name_of(center_zone), "year": year, "운송비_조원": round(float(row.cost_won) / 1e12, 3),
            "평균 운송거리_km": round(float(row.avg_km), 1), "249곳 중 순위": rank, "가정": ASSUMPTIONS}


def best_centers(year=2024, top_n=5, unit_cost=DEFAULT_UNIT_COST, detour=1.0):
    # 후보 249곳 전체에 대해 center_cost와 같은 계산을 하고, 운송비가 낮은 순으로 top_n곳을 돌려준다.
    # evaluate_candidates가 원래 후보 전체의 표를 만들므로(center_cost는 거기서 한 줄만 꺼낸다) 한 번 호출하면 된다.
    f = FLOWS[FLOWS["year"] == year].set_index("zone_id")
    have = set(ZONES.loc[ZONES["has_coord"], "zone_id"])
    demand = {}
    for z in have:
        demand[int(z)] = float(f.loc[z, "in_ton"] + f.loc[z, "inner_ton"])
    table = evaluate_candidates(demand, DIST, unit_cost=unit_cost, detour=detour)

    top = table.head(top_n)
    rows = []
    for rank, row in enumerate(top.itertuples(), start=1):
        rows.append({
            "순위": rank, "zone_id": int(row.center_zone), "name": _name_of(row.center_zone),
            "운송비_조원": round(float(row.cost_won) / 1e12, 3), "평균 운송거리_km": round(float(row.avg_km), 1),
        })
    worst = table.iloc[-1]
    return {"year": year, "top": rows, "후보 수": len(table),
            "가장 높은 후보": {"name": _name_of(int(worst.center_zone)), "운송비_조원": round(float(worst.cost_won) / 1e12, 3)},
            "주의": "센터 한 곳이 전국 수요를 직선 거리로 공급하는 모델에서는 지리적 중앙이 유리한 것이 거의 당연한 결과임. 실제 입지 판단이 아님",
            "가정": ASSUMPTIONS}


def container_hubs(year=2024, top_n=10):
    # 도로 컨테이너 물동량이 몰린 존의 순위. zone_concentration과 같은 방식이고 컨테이너 열만 쓴다.
    # 철도의 컨테이너 열은 따로 집계된 별도 자료라 여기에 포함하지 않는다.
    if year not in ROAD_YEARS:
        raise ValueError(f"연도는 {ROAD_YEARS} 중 하나여야 합니다: {year}")
    f = FLOWS[FLOWS["year"] == year].copy()
    f["container_ton"] = f["in_container_ton"] + f["out_container_ton"]
    mean_value = f["container_ton"].mean()
    f["ratio"] = f["container_ton"] / mean_value

    top = f.nlargest(top_n, "container_ton")
    rows = []
    for row in top.itertuples():
        rows.append({
            "zone_id": int(row.zone_id), "name": _name_of(row.zone_id),
            "in_만톤": round(row.in_container_ton / 1e4), "out_만톤": round(row.out_container_ton / 1e4),
            "평균 대비 배수": round(row.ratio, 1),
        })
    return {"year": year, "top": rows, "평균(만톤)": round(mean_value / 1e4),
            "정의": "도로 컨테이너 물동량 집중도(같은 존 안 이동은 제외). 항만·철도 컨테이너 터미널 위치나 처리 능력은 반영하지 않음",
            "가정": ASSUMPTIONS}


def mode_share(zone_id=None, top_n=10):
    # zone_id가 있으면 그 존의 수송수단별 물량과 비중, 없으면 철도 비중이 높은 존 순위를 돌려준다. 2024년만.
    # 비중 = 수송수단 물량 / (도로 + 철도 + 항공). 세 수송수단의 톤수를 단순 합산한 값이다.
    note = {"정의": "수송수단별 물량 비중(2024, 같은 존 안 이동 제외). 철도역·화물 터미널 위치와 연계 가능성은 반영하지 않음",
            "주의": "철도·항공 자료는 기준년도(2024)만 사용. 장래년도 자료와 이어서 증가율을 계산하지 않음"}
    totals = MODE_TOTALS.copy()
    totals["합계"] = totals["도로"] + totals["철도"] + totals["항공"]

    if zone_id is not None:
        if zone_id not in totals.index:
            raise ValueError(f"존 {zone_id}를 찾을 수 없습니다")
        row = totals.loc[zone_id]
        return {"zone_id": int(zone_id), "name": _name_of(zone_id),
                "도로_만톤": round(row["도로"] / 1e4), "철도_만톤": round(row["철도"] / 1e4),
                "항공_만톤": round(row["항공"] / 1e4, 2),
                "철도 비중(%)": round(100 * row["철도"] / row["합계"], 2),
                "항공 비중(%)": round(100 * row["항공"] / row["합계"], 3), **note}

    totals["철도 비중"] = totals["철도"] / totals["합계"]
    # 물량이 거의 없는 존은 비중이 튀므로, 도로+철도+항공 합계가 중앙값 이상인 존만 순위에 넣는다.
    eligible = totals[totals["합계"] >= totals["합계"].median()]
    top = eligible.nlargest(top_n, "철도 비중")
    rows = []
    for zone, row in top.iterrows():
        rows.append({"zone_id": int(zone), "name": _name_of(zone), "철도_만톤": round(float(row["철도"]) / 1e4),
                     "도로_만톤": round(row["도로"] / 1e4), "철도 비중(%)": round(float(100 * row["철도 비중"]), 1)})
    return {"top": rows, "순위 대상": "합계 물량이 존 중앙값 이상인 존만(물량이 작은 존의 비중 왜곡 방지)",
            "전국 철도 비중(%)": round(100 * totals["철도"].sum() / totals["합계"].sum(), 2), **note}


LINK_LOAD = pd.read_parquet("data/clean/link_load_2024_located.parquet")
ROAD_TYPE_NAMES = {101: "고속국도", 102: "도시고속화도로", 103: "일반국도", 104: "특별·광역시도", 105: "국가지원지방도",
                   106: "지방도", 107: "시군도", 108: "연결램프"}

ROAD_LOAD_NOTE = {
    "정의": "2024 화물차 OD(대/일, 차종별 환산계수 적용)를 도로망의 최단경로 하나에 전량 배정했을 때 링크별 화물차 부하(승용차환산대수/일)",
    "한계": "화물차만 반영하고 승용차·버스는 빠져 있음. 혼잡에 따라 경로를 바꾸지 않는 전량 배정이라 일부 링크에 쏠림. 용량 단위(차로당 시간당)와 첨두율(0.078)은 추정. 따라서 부하는 '화물차가 몰리는 길의 순위'이고 실제 혼잡·정체 여부가 아님",
    "차종 환산계수": "소형 1.0, 중형 1.5, 대형 2.5 (근거 없음, 임시값)",
    "위치": "'가까운 존'은 링크 시점 노드에서 직선거리가 가장 가까운 존 중심이며 링크가 그 존에 속한다는 뜻이 아님",
    "제외": "울릉군·제주시·서귀포시(섬, 도로망에 연결 안 됨) 관련 OD는 배정하지 못함(전체 PCU의 1.25%)",
}


def road_load(top_n=10, road_type=None):
    # 화물차 부하(PCU/일)가 큰 도로 링크의 순위. 순위 기준은 부하이고, 용량 대비 비율은 참고로만 붙인다.
    # road_type이 있으면 그 도로 등급(101 고속국도 ... 108 연결램프)만 본다.
    f = LINK_LOAD
    if road_type is not None:
        if road_type not in ROAD_TYPE_NAMES:
            raise ValueError(f"도로 등급은 {sorted(ROAD_TYPE_NAMES)} 중 하나여야 합니다: {road_type}")
        f = f[f["type"] == road_type]

    top = f.nlargest(top_n, "load_pcu_day")
    rows = []
    for row in top.itertuples():
        rows.append({
            "link": f"{int(row.i)}->{int(row.j)}", "도로등급": ROAD_TYPE_NAMES[int(row.type)], "차로수": int(row.lanes),
            "가까운 존": _name_of(row.near_zone), "존까지 거리(km)": round(row.near_km, 1),
            "화물차 부하(PCU/일)": round(row.load_pcu_day), "용량 대비 비율(참고, 방법 미확정)": round(row.ratio, 2),
        })
    return {"road_type": road_type, "top": rows, **ROAD_LOAD_NOTE}


def road_load_by_zone(top_n=10):
    # 존 단위로 묶어 본다: 존마다 '가까운 존'이 그 존인 링크 중 부하 상위 링크의 부하 합과 최댓값.
    # 같은 길이 여러 링크로 쪼개져 있어 링크 단위 순위는 한 길이 여러 번 나올 수 있는데, 존 단위로 보면 그 중복이 줄어든다.
    g = LINK_LOAD.groupby("near_zone").agg(최대_부하=("load_pcu_day", "max"), 부하_합=("load_pcu_day", "sum"), 링크수=("i", "count"))
    top = g.nlargest(top_n, "최대_부하")
    rows = []
    for zone, row in top.iterrows():
        rows.append({"zone_id": int(zone), "name": _name_of(zone), "최대 링크 부하(PCU/일)": round(row["최대_부하"]), "링크 수": int(row["링크수"])})
    return {"top": rows, "기준": "존 근처 링크 중 부하가 가장 큰 링크의 부하로 순위. 링크 부하 합은 같은 차량이 여러 링크에서 중복 집계되어 쓰지 않음", **ROAD_LOAD_NOTE}


if __name__ == "__main__":
    print(list_zones("광양"))
    c = zone_concentration(2024, top_n=3)
    print(c["top"])
    import json
    print(json.dumps(center_cost(141), ensure_ascii=False)[:200])
    print(json.dumps(zone_concentration(2024, top_n=2), ensure_ascii=False)[:200])
