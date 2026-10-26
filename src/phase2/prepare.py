import glob
import sys

import pandas as pd

sys.path.insert(0, "src/phase1")
sys.path.insert(0, "src/phase2")
from geo import build_distance_table, load_zone_xy
from zones import load_zones

TON_XLSX = glob.glob("data/raw/ton00/*/배포용(기준년도 2024년) 화물물동량OD_2026.08.31.xlsx")[0]
NETWORK_IN = glob.glob("data/raw/network/*/01. 도로네트워크/2024_JUNKUK_도로.in")[0]
ROAD_YEARS = [2024, 2025, 2030, 2035, 2040, 2045, 2050]


def build_zone_table():
    # 존번호, 대존, 시도, 시군구, 이름, 좌표(m), 좌표 유무를 한 표로 합친다.
    zones = load_zones(TON_XLSX, "존체계")
    zones["name"] = zones["sido"] + " " + zones["sigungu"]
    xy = load_zone_xy(NETWORK_IN)
    table = zones.merge(xy, on="zone_id", how="left")
    table["has_coord"] = table["x_m"].notna()
    return table


def build_zone_flows():
    # 연도별로 존마다 (들어오는 양, 나가는 양, 같은 존 안 이동)을 톤으로 모은다. 전체와 컨테이너 둘 다.
    # 기준년도(2024)와 장래년도(2025~)는 서로 다른 파일이라 한 시계열로 잇지 않는다.
    pieces = []
    for year in ROAD_YEARS:
        od = pd.read_parquet(f"data/clean/road_ton_{year}.parquet", columns=["o_zone", "d_zone", "전체", "컨테이너"])
        is_inner = od["o_zone"] == od["d_zone"]
        between = od[~is_inner]
        inner = od[is_inner].set_index("o_zone")

        flows = pd.DataFrame({"zone_id": range(1, 253)}).set_index("zone_id")
        flows["year"] = year
        flows["in_ton"] = between.groupby("d_zone")["전체"].sum()
        flows["out_ton"] = between.groupby("o_zone")["전체"].sum()
        flows["inner_ton"] = inner["전체"]
        flows["in_container_ton"] = between.groupby("d_zone")["컨테이너"].sum()
        flows["out_container_ton"] = between.groupby("o_zone")["컨테이너"].sum()
        pieces.append(flows.fillna(0.0).reset_index())
    return pd.concat(pieces, ignore_index=True)


if __name__ == "__main__":
    zones = build_zone_table()
    zones.to_parquet("data/clean/zones.parquet", index=False)
    print("zones.parquet:", len(zones), "행, 좌표 있음", int(zones["has_coord"].sum()))
    print("이름 중복:", int(zones["name"].duplicated().sum()), "개")

    dist = build_distance_table(zones[zones["has_coord"]][["zone_id", "x_m", "y_m"]])
    dist.to_parquet("data/clean/distance.parquet", index=False)
    print("distance.parquet:", len(dist), "행")

    flows = build_zone_flows()
    flows.to_parquet("data/clean/zone_flows.parquet", index=False)
    print("zone_flows.parquet:", len(flows), "행 (존 252 x 연도", len(ROAD_YEARS), ")")
    print(flows[(flows["year"] == 2024)].nlargest(3, "in_ton")[["zone_id", "in_ton", "out_ton", "inner_ton"]].to_string(index=False))
