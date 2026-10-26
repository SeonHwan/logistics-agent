import json

import pandas as pd
from openpyxl import load_workbook

from convert import build_jobs


def read_header_sums(xlsx_path, sheet_name):
    # 엑셀 시트의 첫 줄(제목 + 열별 합계)과 둘째 줄(머리글)만 읽어 {열 이름: 합계}로 돌려준다.
    workbook = load_workbook(xlsx_path, read_only=True, data_only=True)
    sheet = workbook[sheet_name]

    first_row = None
    second_row = None
    for index, row in enumerate(sheet.iter_rows(values_only=True)):
        if index == 0:
            first_row = row
        elif index == 1:
            second_row = row
            break
    workbook.close()

    sums = {}
    for column_index, name in enumerate(second_row):
        value = first_row[column_index]
        # 합계가 적힌 칸은 숫자다. 존 번호 열 쪽은 비어 있다(None).
        if isinstance(value, (int, float)):
            sums[str(name)] = float(value)
    return sums


def verify_all(summary_path="data/clean/_summary.json", tolerance=1e-6):
    # 변환 요약의 합계와 엑셀 첫 줄의 합계를 열마다 비교한다.
    with open(summary_path, encoding="utf-8") as f:
        summaries = json.load(f)

    # 저장 이름 -> (엑셀 경로, 시트) 대응
    source_by_name = {}
    for path, sheet, out_name in build_jobs():
        source_by_name[out_name] = (path, sheet)

    problems = 0
    for summary in summaries:
        path, sheet = source_by_name[summary["name"]]
        header_sums = read_header_sums(path, sheet)

        checked = 0
        for column, converted_sum in summary["sums"].items():
            if column not in header_sums:
                print(f"  엑셀 첫 줄에 합계가 없음: {summary['name']} / {column}")
                problems += 1
                continue
            expected = header_sums[column]
            # 합계가 크므로 절대 차이 대신 상대 차이로 본다.
            relative_diff = abs(converted_sum - expected) / max(abs(expected), 1.0)
            if relative_diff > tolerance:
                print(f"  불일치: {summary['name']} / {column}: 변환 {converted_sum:,.2f} 엑셀 {expected:,.2f}")
                problems += 1
            checked += 1
        print(f"{summary['name']}: 열 {checked}개 대조")

    print("불일치·누락:", problems)


def verify_structure(summary_path="data/clean/_summary.json"):
    # 변환된 파일마다 (출발,도착) 조합이 252x252=63,504개이고 중복이 없는지, 존 번호가 1~252인지 확인한다.
    # 열 합계 대조는 열 순서가 어긋나도 통과하므로이 검사가 따로 필요하다.
    with open(summary_path, encoding="utf-8") as f:
        summaries = json.load(f)

    problems = 0
    for summary in summaries:
        table = pd.read_parquet(f"data/clean/{summary['name']}.parquet", columns=["o_zone", "d_zone"])
        pair_count = len(table.drop_duplicates())
        origin_ok = table["o_zone"].min() == 1 and table["o_zone"].max() == 252 and table["o_zone"].nunique() == 252
        destination_ok = table["d_zone"].min() == 1 and table["d_zone"].max() == 252 and table["d_zone"].nunique() == 252
        if len(table) != 63504 or pair_count != 63504 or not origin_ok or not destination_ok:
            print(f"  구조 이상: {summary['name']}: 행 {len(table)}, 조합 {pair_count}, 출발 ok={origin_ok}, 도착 ok={destination_ok}")
            problems += 1
    print(f"구조 검사: {len(summaries)}개 중 이상 {problems}개")


if __name__ == "__main__":
    verify_all()
    verify_structure()
