import glob

import openpyxl

# TMS 상시조사 시간평균 시트로 첨두 1시간 비율(최대 시간 교통량 / 일교통량)을 구한다.
# 목적: assign.py의 PEAK_RATIO = 0.078(통행지체함수 식에서 가져온 추정값, 의미 미확인)과 대조한다.
# 고속국도는 구간 하나가 두 줄이다: 첫 줄 열 5~16이 7~18시, 열 17이 주간계 / 둘째 줄 열 5~16이 19~6시, 열 17이 야간계.
# 사용법: uv run python -I src/phase2b/peak_ratio.py


def read_hourly(path, sheet):
    ws = openpyxl.load_workbook(path, read_only=True, data_only=True)[sheet]
    rows = list(ws.iter_rows(values_only=True))
    result = []
    i = 4  # 0부터 센 행 번호. 0~3행은 제목과 머리글
    while i + 1 < len(rows):
        day, night = rows[i], rows[i + 1]
        # 첫 줄에 노선/구간 이름이 있어야 구간의 시작이다. 둘째 줄은 이름이 비어 있다.
        if day[0] is None and day[1] is None:
            i += 1
            continue
        try:
            day_hours = [float(day[k]) for k in range(5, 17)]
            night_hours = [float(night[k]) for k in range(5, 17)]
            day_sum = float(day[17])
            night_sum = float(night[17])
        except (TypeError, ValueError):
            i += 1
            continue
        result.append({
            "route": str(day[0]).strip(), "from": str(day[1]).strip(), "to": str(day[3]).strip(),
            "spot": str(day[4]).strip(), "hours": day_hours + night_hours,
            "day_sum": day_sum, "night_sum": night_sum,
        })
        i += 2
    return result


if __name__ == "__main__":
    path = glob.glob("data/raw/traffic_tms/4. 상시조사 교통량/1. 고속국도/*.xlsx")[0]
    sections = read_hourly(path, "고속국도시간평균")
    print("고속국도 구간:", len(sections))

    bad = 0
    ratios = []
    for s in sections:
        total = sum(s["hours"])
        # 검증: 24시간 합이 주간계 + 야간계와 같아야 한다(시간별 값이 해당 시간 교통량이라는 해석의 확인).
        if abs(total - (s["day_sum"] + s["night_sum"])) > 2:
            bad += 1
        ratios.append(max(s["hours"]) / total)

    print(f"24시간 합 != 주간계+야간계 인 구간: {bad}개")
    ratios_sorted = sorted(ratios)
    n = len(ratios_sorted)
    print(f"첨두 1시간 / 일교통량: 최소 {ratios_sorted[0]:.4f}, 중앙 {ratios_sorted[n // 2]:.4f}, 최대 {ratios_sorted[-1]:.4f}, 평균 {sum(ratios) / n:.4f}")
    print("현재 가정값 PEAK_RATIO = 0.078")
    print("구간별 (상위 5, 하위 5):")
    ranked = sorted(zip(ratios, sections), key=lambda x: x[0])
    for ratio, s in ranked[:5] + ranked[-5:]:
        print(f"  {ratio:.4f}  {s['route']} {s['from']}~{s['to']}")
