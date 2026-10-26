import pandas as pd


def load_zones(xlsx_path, sheet_name):
    # 엑셀의 존체계 시트를 읽어 (존번호, 대존번호, 시도, 시군구) 표로 돌려준다.
    raw = pd.read_excel(xlsx_path, sheet_name=sheet_name)

    zone_ids = []
    region17_ids = []
    sido_names = []
    sigungu_names = []

    # 표의 한 줄씩 돌면서 행정구역명("서울특별시_종로구")을 시도와 시군구로 나눈다.
    for index, row in raw.iterrows():
        full_name = row["행정구역명"]
        parts = full_name.split("_", 1)   # 처음 나오는 "_"에서 한 번만 자른다
        zone_ids.append(int(row["존번호"]))
        region17_ids.append(int(row["대존_17"]))
        sido_names.append(parts[0])
        sigungu_names.append(parts[1])

    zones = pd.DataFrame({
        "zone_id": zone_ids,
        "region17": region17_ids,
        "sido": sido_names,
        "sigungu": sigungu_names,
    })
    return zones


def compare_zone_tables(sources):
    # sources는 (엑셀 경로, 시트 이름) 짝의 리스트다. 첫 번째를 기준으로 삼아 나머지가 같은지 본다.
    base_path, base_sheet = sources[0]
    base = load_zones(base_path, base_sheet)
    print(f"기준: {base_path.split('/')[-1]} [{base_sheet}]")

    all_same = True
    for path, sheet in sources[1:]:
        other = load_zones(path, sheet)
        file_name = path.split("/")[-1]

        if len(other) != len(base):
            print(f"다름 (행 수 {len(other)} != {len(base)}): {file_name}")
            all_same = False
            continue

        # 행 수가 같으면 열마다 값이 다른 줄을 센다. 같으면 0이다.
        diff_count = 0
        for column in ["zone_id", "region17", "sido", "sigungu"]:
            for i in range(len(base)):
                if base[column][i] != other[column][i]:
                    diff_count += 1
                    print(f"  다른 값: {file_name} 줄 {i} {column}: {base[column][i]!r} -> {other[column][i]!r}")

        if diff_count == 0:
            print(f"같음: {file_name} [{sheet}]")
        else:
            all_same = False

    return all_same


if __name__ == "__main__":
    car_dir = "data/raw/car00/"
    ton_dir = "data/raw/ton00/2025-OD-FRE-TON-00 전국지역간 품목별 도로물동량 OD(2024년 기준)/"
    rail_dir = "data/raw/ton06/2025-OD-FRE-TON-06 전국지역간 철도항공 수단별 물동량 OD(2024년 기준)/"
    sources = [
        (car_dir + "배포용 (기준년도 2024년) 화물자동차OD_2026.08.21.xlsx", "KTDB 존체계"),
        (car_dir + "배포용 장래년도 화물자동차OD_2026.08.21.xlsx", "KTDB 존체계"),
        (ton_dir + "배포용(기준년도 2024년) 화물물동량OD_2026.08.31.xlsx", "존체계"),
        (ton_dir + "배포용 장래년도(2025-2050) 도로 전체 물동량OD_2026.08.31.xlsx", "존체계"),
        (rail_dir + "(배포용) 2024년 기준 기준년도 및 장래년도 철도화물OD - 26.08.31.xlsx", "존체계"),
        (rail_dir + "(배포용) 2024년 기준 기준년도 및 장래년도 항공화물OD - 26.08.31.xlsx", "존체계"),
    ]
    print("전부 같음:", compare_zone_tables(sources))
