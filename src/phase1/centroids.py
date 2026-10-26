import sys


def read_centroids(path):
    # 노드 구간에서 'a*'로 시작하는 줄을 읽어 {노드번호: (x, y, 행정코드)}를 만든다.
    result = {}
    with open(path, encoding="cp949", errors="replace") as f:
        for line in f:
            if line.startswith("t links"):
                break
            if not line.startswith("a*"):
                continue
            parts = line.split()
            # 예: a*  1 309905.00 554098.00 0 0 11010
            node_id = int(parts[1])
            x = float(parts[2])
            y = float(parts[3])
            code = parts[6] if len(parts) > 6 else ""
            result[node_id] = (x, y, code)
    return result


if __name__ == "__main__":
    centroids = read_centroids(sys.argv[1])
    missing = [z for z in range(1, 253) if z not in centroids]
    extra = [n for n in centroids if n > 252]
    print("센트로이드 수:", len(centroids))
    print("1~252 중 빠진 번호:", missing)
    print("252보다 큰 센트로이드:", extra)
