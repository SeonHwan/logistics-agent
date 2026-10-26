import glob
import sys

import pandas as pd

sys.path.insert(0, "src/phase1")
sys.path.insert(0, "src/phase2")
from cost import DEFAULT_UNIT_COST
from geo import build_distance_table, load_zone_xy
from zones import load_zones


def evaluate_candidates(demand, dist, unit_cost=DEFAULT_UNIT_COST, detour=1.0):
    # demand: {존번호: 수요(톤)}. dist: o_zone, d_zone, km 열을 가진 표.
    # 후보지(센터를 둘 존)마다, 센터에서 모든 존으로 수요를 보내는 총 운송비(원)를 구해 표로 돌려준다.

    # 거리 표를 {(출발, 도착): km} 딕셔너리로 바꿔 두면 아래에서 바로 찾을 수 있다.
    distance = {}
    for row in dist.itertuples():
        distance[(row.o_zone, row.d_zone)] = row.km

    candidates = sorted(demand.keys())
    result_zone = []
    result_cost = []
    result_avg_km = []

    for center in candidates:
        total_cost = 0.0
        total_ton_km = 0.0
        total_tons = 0.0
        for zone in candidates:
            tons = demand[zone]
            km = distance[(center, zone)] * detour
            total_ton_km += tons * km
            total_tons += tons
        total_cost = total_ton_km * unit_cost

        result_zone.append(center)
        result_cost.append(total_cost)
        # 평균 운송 거리 = 톤·km 합 / 톤 합. 센터에서 수요가 평균 몇 km 떨어져 있는지다.
        result_avg_km.append(total_ton_km / total_tons)

    table = pd.DataFrame({"center_zone": result_zone, "cost_won": result_cost, "avg_km": result_avg_km})
    return table.sort_values("cost_won").reset_index(drop=True)


if __name__ == "__main__":
    network = glob.glob("data/raw/network/*/01. 도로네트워크/2024_JUNKUK_도로.in")[0]
    dist = build_distance_table(load_zone_xy(network))
    zone_ids = set(dist["o_zone"])

    od = pd.read_parquet("data/clean/road_ton_2024.parquet", columns=["o_zone", "d_zone", "전체"])
    # 존으로 들어오는 양(도착 기준 합, 같은 존 안 이동 포함). 좌표가 있는 존만 남긴다.
    inflow = od.groupby("d_zone")["전체"].sum()
    demand = {}
    for zone, tons in inflow.items():
        if zone in zone_ids:
            demand[int(zone)] = float(tons)
    print(f"수요 존 {len(demand)}개, 수요 합 {sum(demand.values()) / 1e8:.2f}억톤")

    ton_dir = "data/raw/ton00/2025-OD-FRE-TON-00 전국지역간 품목별 도로물동량 OD(2024년 기준)/"
    zones = load_zones(ton_dir + "배포용(기준년도 2024년) 화물물동량OD_2026.08.31.xlsx", "존체계")
    names = {}
    for row in zones.itertuples():
        names[row.zone_id] = f"{row.sido} {row.sigungu}"

    table = evaluate_candidates(demand, dist)
    table["name"] = table["center_zone"].map(names)
    table["cost_조원"] = (table["cost_won"] / 1e12).round(3)
    table["avg_km"] = table["avg_km"].round(1)
    print("\n총 운송비가 낮은 후보 5곳")
    print(table.head(5)[["center_zone", "name", "cost_조원", "avg_km"]].to_string(index=False))
    print("\n가장 높은 후보 3곳")
    print(table.tail(3)[["center_zone", "name", "cost_조원", "avg_km"]].to_string(index=False))
