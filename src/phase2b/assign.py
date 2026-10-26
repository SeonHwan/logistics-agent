import glob
import sys

import numpy as np
import pandas as pd
from scipy.sparse import csr_matrix
from scipy.sparse.csgraph import dijkstra

# OD(화물차 대/일)를 도로망의 최단경로에 얹어 링크별 부하를 구한다.
# - 전량 배정: 모든 OD를 최단경로 하나에 얹는다. 혼잡에 따라 경로를 바꾸지 않는다.
# - 최단경로 기준은 이동 시간(길이 / 초기속도)이다. 방향 링크를 방향 그대로 쓴다.
# - 화물차 OD만 얹으므로 승용차·버스 교통량이 빠져 있다. 결과는 혼잡도가 아니라 '화물차가 용량을 얼마나 쓰는가'다.
# 사용법: uv run python src/phase2b/assign.py [연도]

NETWORK_IN = glob.glob("data/raw/network/*/01. 도로네트워크/2024_JUNKUK_도로.in")[0]

# 가정값 (근거 없음). 코드에 숨기지 않고 파라미터로 둔다.
# 차종 환산계수: 소형·중형·대형 화물차 1대를 승용차 몇 대로 셀지. 근거를 찾지 못한 임시값이다.
PCE = {"소형": 1.0, "중형": 1.5, "대형": 2.5}
# 용량이 차로당 시간당 값이라는 가정(추정)에서, 일 교통량 대비 첨두 1시간 비율. 통행지체함수 식의 0.078에서 가져왔고 의미는 미확인이다.
PEAK_RATIO = 0.078
# 존 중심점 노드 번호는 1~252다. 이보다 큰 번호가 일반 도로 노드다.
ZONE_MAX = 252


def read_links(path):
    # 링크 구간의 'a' 줄을 읽는다. 예: a 698826 676615 1.340 cp 105 2 12 83.4 1400 0
    # 열: 시점, 종점, 길이(km), 수단, 도로등급, 차로수, VDF, 초기속도, 용량, 준공연도
    rows = []
    in_links = False
    with open(path, encoding="cp949", errors="replace") as f:
        for line in f:
            if line.startswith("t links"):
                in_links = True
                continue
            if not in_links or not line.startswith("a "):
                continue
            p = line.split()
            rows.append((int(p[1]), int(p[2]), float(p[3]), int(p[5]), float(p[6]), int(p[7]), float(p[8]), float(p[9])))
    links = pd.DataFrame(rows, columns=["i", "j", "length_km", "type", "lanes", "vdf", "speed", "capacity"])
    # 이동 시간(분) = 길이 / 속도 * 60. 최단경로의 비용으로 쓴다.
    links["minutes"] = links["length_km"] / links["speed"] * 60.0
    return links


def read_node_xy(path):
    # 노드 구간의 'a' 또는 'a*' 줄: a  1 309905.00 554098.00 0 0 11010 -> {노드번호: (x, y)} (미터)
    nodes = {}
    with open(path, encoding="cp949", errors="replace") as f:
        for line in f:
            if line.startswith("t links"):
                break
            if line.startswith("a ") or line.startswith("a*"):
                p = line.split()
                nodes[int(p[1])] = (float(p[2]), float(p[3]))
    return nodes


def build_matrix(links, node_ids):
    # 노드 번호(최대 약 70만)를 0부터 시작하는 위치로 바꿔 희소 행렬을 만든다. 값은 이동 시간이다.
    # 같은 (i, j)가 둘 있으면 더해져 버리므로 중복이 없다는 것을 앞서 확인했다(중복 0개).
    # 존 노드(1~252)로 '들어가는' 커넥터는 행렬에서 뺀다. 존 중심점은 출발·도착 전용인데, 넣어 두면 최단경로가
    # 존 노드를 길목으로 삼아 존 -> 존 -> 존으로 이어 달리는 지름길을 만든다.
    # 도착 존으로 들어가는 마지막 한 걸음은 assign()에서 따로 붙인다.
    position = {}
    for index, node in enumerate(node_ids):
        position[node] = index
    usable = links[links["j"] > ZONE_MAX]
    rows = usable["i"].map(position).to_numpy()
    cols = usable["j"].map(position).to_numpy()
    matrix = csr_matrix((usable["minutes"].to_numpy(), (rows, cols)), shape=(len(node_ids), len(node_ids)))
    return matrix, position


def load_truck_od(year):
    # 화물차 OD(대/일)를 차종별 환산계수로 승용차환산대수(PCU/일)로 바꾼다.
    od = pd.read_parquet(f"data/clean/truck_{year}.parquet")
    od = od[od["o_zone"] != od["d_zone"]].copy()  # 같은 존 안 이동은 도로망을 쓰지 않는 것으로 본다
    od["pcu"] = 0.0
    for kind, factor in PCE.items():
        od["pcu"] += od[kind] * factor
    return od[["o_zone", "d_zone", "pcu"]]


def assign(links, od):
    # 존마다 최단경로 트리를 만들고, 그 트리 위에서 도착지 물량을 뿌리 쪽으로 합산해 링크 부하를 구한다.
    node_ids = np.array(sorted(set(links["i"]) | set(links["j"])))
    matrix, position = build_matrix(links, node_ids)

    # 링크 (i, j) -> 링크 행 번호. 트리의 부모 관계(predecessor)를 링크로 되돌릴 때 쓴다.
    link_row = {}
    for row, (i, j) in enumerate(zip(links["i"], links["j"])):
        link_row[(position[i], position[j])] = row

    # 도착 존으로 들어가는 커넥터(도로 노드 -> 존 노드)를 존별로 모아 둔다. 마지막 한 걸음에서 가장 빠른 것을 고른다.
    entry = {}
    for row, (i, j, minutes) in enumerate(zip(links["i"], links["j"], links["minutes"])):
        if j <= ZONE_MAX:
            entry.setdefault(j, []).append((row, position[i], minutes))

    load = np.zeros(len(links))  # 링크별 부하(PCU/일)
    unreachable = 0.0  # 도달하지 못한 OD의 PCU 합

    origins = sorted(od["o_zone"].unique())
    for count, origin in enumerate(origins):
        origin_pos = position.get(origin)
        if origin_pos is None:
            unreachable += od.loc[od["o_zone"] == origin, "pcu"].sum()
            continue

        # 이 출발지에서 모든 노드까지의 최단 시간과, 최단경로 트리의 부모 노드를 구한다.
        dist, pred = dijkstra(matrix, directed=True, indices=origin_pos, return_predecessors=True)

        # 도착 존마다 '도로 노드 -> 존' 커넥터 중 (그 노드까지 시간 + 커넥터 시간)이 가장 작은 것을 고른다.
        # 그 커넥터에 물량을 얹고, 물량은 그 커넥터의 시점 도로 노드에서 끝나는 것으로 보고 트리를 거슬러 올린다.
        sub = od[od["o_zone"] == origin]
        demand = np.zeros(len(node_ids))
        for dest, pcu in zip(sub["d_zone"], sub["pcu"]):
            best_row = None
            best_node = None
            best_time = np.inf
            for row, node_pos, minutes in entry.get(dest, []):
                total = dist[node_pos] + minutes
                if total < best_time:
                    best_time = total
                    best_row = row
                    best_node = node_pos
            if best_row is None or not np.isfinite(best_time):
                unreachable += pcu
                continue
            load[best_row] += pcu
            demand[best_node] += pcu

        # 출발지에서 먼 노드부터 뿌리로 거슬러 올라가며, 자식의 누적 물량을 부모 쪽 링크에 얹는다.
        order = np.argsort(-np.where(np.isfinite(dist), dist, -1.0))
        for node in order:
            if demand[node] == 0.0 or node == origin_pos:
                continue
            parent = pred[node]
            row = link_row[(parent, node)]
            load[row] += demand[node]
            demand[parent] += demand[node]

        if (count + 1) % 50 == 0:
            print(f"  출발지 {count + 1}/{len(origins)} 처리", flush=True)

    result = links.copy()
    result["load_pcu_day"] = load
    return result, unreachable


def add_ratio(result):
    # 용량 대비 사용 비율. 용량(차로당 시간당 추정) x 차로수 = 링크 시간당 용량, 일 부하 x 첨두율 = 첨두 1시간 부하.
    # 커넥터(등급 999)는 용량이 99999라 비율이 0에 가깝다. 분석에서는 제외한다.
    hourly_capacity = result["capacity"] * result["lanes"]
    result["peak_load"] = result["load_pcu_day"] * PEAK_RATIO
    result["ratio"] = result["peak_load"] / hourly_capacity
    return result


if __name__ == "__main__":
    year = int(sys.argv[1]) if len(sys.argv) > 1 else 2024

    links = read_links(NETWORK_IN)
    print("링크:", len(links), "개")
    od = load_truck_od(year)
    print(f"OD: {len(od)}쌍, 총 {od['pcu'].sum():,.0f} PCU/일 (환산계수 {PCE})")

    result, unreachable = assign(links, od)
    result = add_ratio(result)

    print(f"도달 불가 OD: {unreachable:,.0f} PCU/일 ({unreachable / od['pcu'].sum():.4%})")
    out = f"data/clean/link_load_{year}.parquet"
    result.to_parquet(out, index=False)
    print("저장:", out)

    road = result[result["type"] != 999]
    print("\n비율 상위 10 링크 (커넥터 제외):")
    print(road.sort_values("ratio", ascending=False).head(10)[["i", "j", "type", "lanes", "capacity", "load_pcu_day", "ratio"]].to_string(index=False))
