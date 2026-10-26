import math
import sys

import pandas as pd

sys.path.insert(0, "src/phase1")
from centroids import read_centroids


def load_zone_xy(network_path):
    # 도로망 파일의 존 중심점(a*)을 읽어 (zone_id, x_m, y_m) 표로 돌려준다.
    # read_centroids는 {존번호: (x, y, 행정코드)} 딕셔너리를 돌려준다.
    centroids = read_centroids(network_path)

    zone_ids = []
    xs = []
    ys = []
    # 딕셔너리를 한 줄씩 꺼낸다. items()는 (키, 값) 짝을 돌려준다.
    for zone_id, (x, y, code) in centroids.items():
        zone_ids.append(zone_id)
        xs.append(x)
        ys.append(y)

    table = pd.DataFrame({"zone_id": zone_ids, "x_m": xs, "y_m": ys})
    table = table.sort_values("zone_id").reset_index(drop=True)
    return table


def build_distance_table(zone_xy):
    # 모든 (출발 존, 도착 존) 쌍의 직선 거리(km)를 (o_zone, d_zone, km) 표로 돌려준다.
    # 존이 249개이면 249 x 249 = 62,001줄이다. 자기 자신과의 거리는 0이다.
    ids = zone_xy["zone_id"].tolist()
    xs = zone_xy["x_m"].tolist()
    ys = zone_xy["y_m"].tolist()

    o_list = []
    d_list = []
    km_list = []
    for i in range(len(ids)):
        for j in range(len(ids)):
            dx = xs[i] - xs[j]
            dy = ys[i] - ys[j]
            # 피타고라스: 두 점 사이 거리. 좌표가 미터라서 1000으로 나눠 km로 바꾼다.
            distance_km = math.sqrt(dx * dx + dy * dy) / 1000
            o_list.append(ids[i])
            d_list.append(ids[j])
            km_list.append(distance_km)

    return pd.DataFrame({"o_zone": o_list, "d_zone": d_list, "km": km_list})


if __name__ == "__main__":
    import glob

    path = glob.glob("data/raw/network/*/01. 도로네트워크/2024_JUNKUK_도로.in")[0]
    xy = load_zone_xy(path)
    dist = build_distance_table(xy)
    print("쌍 수:", len(dist), "(기대: 249 x 249 = 62001)")

    # 검산: 자기 자신은 0, 방향을 바꿔도 같아야 한다, 앞에서 잰 서울-부산 값(330.9)과 같아야 한다.
    self_pairs = dist[dist["o_zone"] == dist["d_zone"]]
    print("자기 자신 거리 최대:", self_pairs["km"].max())
    lookup = dist.set_index(["o_zone", "d_zone"])["km"]
    print("서울(1)->부산(26):", round(lookup[(1, 26)], 1), " 부산->서울:", round(lookup[(26, 1)], 1))
    print("가장 먼 쌍:", dist.loc[dist["km"].idxmax()].to_dict())
