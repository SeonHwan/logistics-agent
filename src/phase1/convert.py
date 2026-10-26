import json
import os
import time

from od import load_od_sheet


def convert_sheet(xlsx_path, sheet_name, out_name, out_dir="data/clean"):
    # 시트 하나를 읽어 out_dir/out_name.parquet 로 저장하고, 나중에 대조할 요약을 돌려준다.
    os.makedirs(out_dir, exist_ok=True)

    started = time.time()
    table = load_od_sheet(xlsx_path, sheet_name)

    # 열 이름이 숫자(2025 등)이면 Parquet가 저장하지 못하므로 문자열로 바꾼다.
    new_names = []
    for name in table.columns:
        new_names.append(str(name))
    table.columns = new_names

    out_path = os.path.join(out_dir, out_name + ".parquet")
    table.to_parquet(out_path, index=False)

    # 값 열(o_zone, d_zone 제외)마다 합계를 남긴다. 1-4에서 엑셀 첫 줄의 합계와 대조한다.
    sums = {}
    for name in table.columns:
        if name in ("o_zone", "d_zone"):
            continue
        sums[name] = float(table[name].sum())

    return {
        "name": out_name,
        "rows": len(table),
        "file_kb": round(os.path.getsize(out_path) / 1024),
        "seconds": round(time.time() - started, 1),
        "sums": sums,
    }


def build_jobs():
    # 변환할 (엑셀 경로, 시트 이름, 저장 이름) 목록을 만든다.
    ton_dir = "data/raw/ton00/2025-OD-FRE-TON-00 전국지역간 품목별 도로물동량 OD(2024년 기준)/"
    rail_dir = "data/raw/ton06/2025-OD-FRE-TON-06 전국지역간 철도항공 수단별 물동량 OD(2024년 기준)/"
    car_dir = "data/raw/car00/"

    road_base = ton_dir + "배포용(기준년도 2024년) 화물물동량OD_2026.08.31.xlsx"
    road_future = ton_dir + "배포용 장래년도(2025-2050) 도로 전체 물동량OD_2026.08.31.xlsx"
    truck_base = car_dir + "배포용 (기준년도 2024년) 화물자동차OD_2026.08.21.xlsx"
    truck_future = car_dir + "배포용 장래년도 화물자동차OD_2026.08.21.xlsx"
    rail = rail_dir + "(배포용) 2024년 기준 기준년도 및 장래년도 철도화물OD - 26.08.31.xlsx"
    air = rail_dir + "(배포용) 2024년 기준 기준년도 및 장래년도 항공화물OD - 26.08.31.xlsx"

    jobs = []
    jobs.append((road_base, "2024년 기준 도로 전체 물동량", "road_ton_2024"))
    for year in [2025, 2030, 2035, 2040, 2045, 2050]:
        jobs.append((road_future, f"{year}년", f"road_ton_{year}"))

    jobs.append((truck_base, "2024년 기준 화물자동차 OD", "truck_2024"))
    for year in [2030, 2035, 2040, 2045, 2050, 2055]:
        jobs.append((truck_future, f"{year}년", f"truck_{year}"))

    jobs.append((rail, "2024 기준 철도OD", "rail_2024"))
    jobs.append((rail, "장래 철도(컨테이너)", "rail_future_container"))
    jobs.append((rail, "장래 철도(일반화물)", "rail_future_general"))
    jobs.append((rail, "장래 철도(전체)", "rail_future_total"))

    jobs.append((air, "2024년 기준 항공화물OD", "air_2024"))
    jobs.append((air, "장래년도 항공화물OD", "air_future"))
    return jobs


def convert_all(summary_path="data/clean/_summary.json"):
    # 목록의 시트를 차례로 변환한다. 이미 변환된 파일이 있어도 다시 만든다(원본이 바뀌었을 수 있으므로).
    jobs = build_jobs()
    summaries = []
    for index, (path, sheet, out_name) in enumerate(jobs):
        result = convert_sheet(path, sheet, out_name)
        summaries.append(result)
        print(f"[{index + 1}/{len(jobs)}] {out_name}: {result['rows']}행, {result['file_kb']}KB, {result['seconds']}초", flush=True)

    with open(summary_path, "w", encoding="utf-8") as f:
        json.dump(summaries, f, ensure_ascii=False, indent=1)
    print("요약 저장:", summary_path)


if __name__ == "__main__":
    convert_all()
