import json
import os
import sys

import requests
from dotenv import load_dotenv

# Langfuse 서버에서 observation(모델 호출·도구 호출·노드 한 단계)을 읽어 data/에 저장한다. 읽기 전용이다.
# 키는 .env에서 읽기만 하고 출력하지 않는다. 사용법: uv run python src/phase4/fetch_langfuse.py [가져올 개수]


def main():
    load_dotenv()
    host = os.environ["LANGFUSE_HOST"].rstrip("/")
    auth = (os.environ["LANGFUSE_PUBLIC_KEY"], os.environ["LANGFUSE_SECRET_KEY"])
    limit = int(sys.argv[1]) if len(sys.argv) > 1 else 100

    response = requests.get(
        host + "/api/public/v2/observations",
        # 기본 조회에는 입출력·토큰이 빠져 있어 fields로 요청한다
        params={"limit": limit, "fields": "core,basic,time,io,model,usage,metadata"},
        auth=auth,
        timeout=30,
    )
    print("HTTP", response.status_code)
    response.raise_for_status()
    body = response.json()

    with open("data/langfuse_observations.json", "w", encoding="utf-8") as f:
        json.dump(body, f, ensure_ascii=False, indent=1)

    items = body.get("data", [])
    print("최상위 키:", list(body.keys()))
    print("가져온 개수:", len(items))
    if items:
        print("첫 항목 필드:", list(items[0].keys()))


main()
