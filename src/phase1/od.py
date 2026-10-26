import pandas as pd


def find_zone_columns(raw):
    # 앞 4개 열 중 서로 다른 값이 252개인 열 2개를 찾아 (출발 열, 도착 열) 이름을 돌려준다.
    # 열 머리글이 값과 어긋난 시트가 있어서이름을 믿지 않고 값으로 판정한다.
    # 출발 존은 같은 값이 252행 연속하다 바뀌므로 값이 덜 바뀌는 쪽이 출발, 더 자주 바뀌는 쪽이 도착이다.
    candidates = []
    for name in raw.columns[:4]:
        if raw[name].nunique() == 252:
            candidates.append(name)
    if len(candidates) != 2:
        raise ValueError(f"서로 다른 값이 252개인 열이 2개가 아닙니다: {candidates}")

    change_counts = []
    for name in candidates:
        values = raw[name].tolist()
        changes = 0
        for i in range(1, len(values)):
            if values[i] != values[i - 1]:
                changes += 1
        change_counts.append(changes)

    if change_counts[0] < change_counts[1]:
        return candidates[0], candidates[1]
    return candidates[1], candidates[0]


def load_od_sheet(xlsx_path, sheet_name):
    # OD 시트 하나를 읽어 (o_zone, d_zone, 값 열들) 표로 돌려준다.
    # 첫 줄은 제목과 열 합계이고 둘째 줄이 머리글이라 header=1로 읽는다(0부터 세므로 둘째 줄).
    raw = pd.read_excel(xlsx_path, sheet_name=sheet_name, header=1)

    origin_column, destination_column = find_zone_columns(raw)

    # 이름으로 짐작한 열과 값으로 판정한 열이 다르면 알린다.
    name_based_origin = None
    name_based_destination = None
    for name in raw.columns[:4]:
        if str(name) in ("O_252", "O_250"):
            name_based_origin = name
        elif str(name) in ("D_252", "D_250"):
            name_based_destination = name
    mismatch = (origin_column != name_based_origin) or (destination_column != name_based_destination)
    if mismatch:
        print(f"  [머리글 어긋남] {sheet_name}: 머리글상 출발={name_based_origin}, 도착={name_based_destination} "
              f"-> 값으로 판정한 출발={origin_column}, 도착={destination_column}")

    # 값 열은 앞 4열(존 번호 4개)을 뺀 나머지다. 모든 파일에서 값 열은 5번째부터 시작한다.
    value_columns = list(raw.columns[4:])

    result = raw[[origin_column, destination_column] + value_columns].copy()
    result = result.rename(columns={origin_column: "o_zone", destination_column: "d_zone"})
    return result
