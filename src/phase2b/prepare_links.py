import glob
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, "src/phase2b")
from assign import NETWORK_IN, ZONE_MAX, read_node_xy

# link_load_2024.parquet에 링크 양 끝의 좌표와 '가장 가까운 존'을 붙여 도구가 바로 읽을 수 있는 표로 만든다.
# 가장 가까운 존 = 노드 좌표에서 존 중심점(노드 1~252) 중 직선 거리가 가장 짧은 존. 링크가 실제로 그 존에 속한다는 뜻은 아니다.
# 사용법: uv run python src/phase2b/prepare_links.py


def main():
    nodes = read_node_xy(NETWORK_IN)
    zone_ids = [z for z in range(1, ZONE_MAX + 1) if z in nodes]
    zone_xy = np.array([nodes[z] for z in zone_ids])

    links = pd.read_parquet("data/clean/link_load_2024.parquet")
    links = links[links["type"] != 999].copy()  # 존 커넥터는 도로가 아니므로 뺀다

    # 링크 시점 노드의 좌표에서 가장 가까운 존을 찾는다. 링크 9만 개 x 존 249개 거리 행렬은 약 2,200만 칸이라 한 번에 계산해도 된다.
    xy = np.array([nodes[n] for n in links["i"]])
    diff = xy[:, None, :] - zone_xy[None, :, :]
    dist = np.sqrt((diff ** 2).sum(axis=2))
    nearest = dist.argmin(axis=1)
    links["near_zone"] = [zone_ids[k] for k in nearest]
    links["near_km"] = dist.min(axis=1) / 1000.0

    out = "data/clean/link_load_2024_located.parquet"
    links.to_parquet(out, index=False)
    print("저장:", out, " 링크:", len(links))
    print(links["near_km"].describe(percentiles=[.5, .9, .99]).round(1).to_string())


main()
