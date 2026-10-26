import sys

import pandas as pd

sys.path.insert(0, "src/phase2")
from cost import DEFAULT_UNIT_COST
from location import evaluate_candidates

ZONES = pd.read_parquet("data/clean/zones.parquet")
DIST = pd.read_parquet("data/clean/distance.parquet")
HAVE = sorted(ZONES.loc[ZONES["has_coord"], "zone_id"].astype(int).tolist())

DISTANCE = {}
for row in DIST.itertuples():
    DISTANCE[(int(row.o_zone), int(row.d_zone))] = row.km


def make_demand(weights):
    # weights: {존번호: 수요(톤)}. 나머지 좌표 있는 존은 수요 0으로 채워 후보지에 모두 들어가게 한다.
    demand = {}
    for zone in HAVE:
        demand[zone] = 0.0
    for zone, tons in weights.items():
        demand[zone] = float(tons)
    return demand


def run_scenarios():
    # 각 시나리오: (이름, 수요, 기대 최적 존, 기대 최소 비용 또는 None). 기대값은 수학으로 구한 것이다.
    results = []

    # S1: 수요가 부산 강서구(37)에만 있다. 최적은 37, 비용 0.
    demand = make_demand({37: 1_000_000})
    table = evaluate_candidates(demand, DIST)
    best = table.iloc[0]
    results.append(("S1 단일 수요지", int(best["center_zone"]) == 37 and best["cost_won"] == 0.0,
                    f"최적 {int(best['center_zone'])}, 비용 {best['cost_won']}"))

    # S2: 서울 종로(1) 60, 부산 중구(26) 25, 대전 동구(66) 15. 1이 과반이라 최적.
    demand = make_demand({1: 60, 26: 25, 66: 15})
    table = evaluate_candidates(demand, DIST)
    results.append(("S2 과반 규칙", int(table.iloc[0]["center_zone"]) == 1,
                    f"최적 {int(table.iloc[0]['center_zone'])} (기대 1)"))

    # S3: 서울 종로(1)와 부산 중구(26)에 같은 수요. 최소 비용 = 수요 x 두 지점 거리 x 단가.
    demand = make_demand({1: 500, 26: 500})
    table = evaluate_candidates(demand, DIST)
    expected = 500 * DISTANCE[(1, 26)] * DEFAULT_UNIT_COST
    got = float(table.iloc[0]["cost_won"])
    results.append(("S3 두 지점 같은 비중", abs(got - expected) / expected < 1e-9,
                    f"최소 비용 {got:,.0f}원, 기대 {expected:,.0f}원"))

    # S4: 수요를 2배로 하면 비용은 2배, 최적은 같다.
    base = make_demand({1: 60, 26: 25, 66: 15, 37: 10})
    doubled = {z: t * 2 for z, t in base.items()}
    t1 = evaluate_candidates(base, DIST)
    t2 = evaluate_candidates(doubled, DIST)
    same_best = int(t1.iloc[0]["center_zone"]) == int(t2.iloc[0]["center_zone"])
    ratio = float(t2.iloc[0]["cost_won"]) / float(t1.iloc[0]["cost_won"])
    results.append(("S4 규모 불변", same_best and abs(ratio - 2.0) < 1e-9, f"비용 비 {ratio:.12f}, 같은 최적 {same_best}"))

    return results


if __name__ == "__main__":
    results = run_scenarios()
    for name, ok, detail in results:
        print(("통과" if ok else "실패"), name, "-", detail)
    print(f"{sum(1 for r in results if r[1])}/{len(results)} 통과")
