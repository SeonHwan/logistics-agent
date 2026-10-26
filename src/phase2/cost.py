import glob
import sys

import pandas as pd

sys.path.insert(0, "src/phase2")
from geo import build_distance_table, load_zone_xy

# 기본 단가: 2025년 안전운송원가 25톤 777원/km 를 25톤으로 나눈 값.
# 적재율 100%를 가정한 하한 추정이다.
DEFAULT_UNIT_COST = 777 / 25


def compute_od_cost(od, dist, unit_cost=DEFAULT_UNIT_COST, detour=1.0, ton_column="전체"):
    # od: o_zone, d_zone, 톤 열을 가진 표. dist: o_zone, d_zone, km 열을 가진 표.
    # 거리가 있는 쌍만 남겨(inner join) 톤·km와 운송비(원)를 계산해 돌려준다.
    before_rows = len(od)
    before_tons = od[ton_column].sum()

    # 두 표를 (o_zone, d_zone)으로 이어 붙인다.
    # how="inner"는 양쪽에 모두 있는 쌍만 남긴다. 좌표가 없는 존 3개는 dist에 없으므로 여기서 빠진다.
    merged = od[["o_zone", "d_zone", ton_column]].merge(dist, on=["o_zone", "d_zone"], how="inner")

    merged["ton_km"] = merged[ton_column] * merged["km"] * detour
    merged["cost_won"] = merged["ton_km"] * unit_cost

    dropped_rows = before_rows - len(merged)
    dropped_tons = before_tons - merged[ton_column].sum()
    report = {
        "dropped_rows": int(dropped_rows),
        "dropped_tons": float(dropped_tons),
        "dropped_share": float(dropped_tons / before_tons),
        "total_tons": float(merged[ton_column].sum()),
        "total_ton_km": float(merged["ton_km"].sum()),
        "total_cost_won": float(merged["cost_won"].sum()),
    }
    return merged, report


if __name__ == "__main__":
    network = glob.glob("data/raw/network/*/01. 도로네트워크/2024_JUNKUK_도로.in")[0]
    dist = build_distance_table(load_zone_xy(network))
    od = pd.read_parquet("data/clean/road_ton_2024.parquet", columns=["o_zone", "d_zone", "전체"])

    result, report = compute_od_cost(od, dist)
    print("제외된 쌍:", report["dropped_rows"], "개")
    print(f"제외된 물동량: {report['dropped_tons'] / 1e4:,.0f}만톤 (전체의 {100 * report['dropped_share']:.2f}%)")
    print(f"계산에 쓴 물동량: {report['total_tons'] / 1e8:.2f}억톤")
    print(f"총 톤·km: {report['total_ton_km'] / 1e12:.3f}조 톤·km")
    print(f"총 운송비(하한): {report['total_cost_won'] / 1e12:.2f}조 원")

    inner = result[result["o_zone"] == result["d_zone"]]
    print(f"그중 같은 존 안 이동: {inner['전체'].sum() / 1e8:.2f}억톤 (운송비 계산상 0원)")
    print("운송비 상위 3쌍:")
    print(result.nlargest(3, "cost_won")[["o_zone", "d_zone", "전체", "km", "cost_won"]].to_string(index=False))
