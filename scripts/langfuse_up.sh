#!/usr/bin/env bash
# Langfuse 서버를 수동으로 올린다. 프로젝트 루트 어디서 실행해도 되도록 먼저 루트로 이동한다.
# 사용법: bash scripts/langfuse_up.sh        (올리기)
#         bash scripts/langfuse_up.sh stop   (내리기, 데이터는 볼륨에 남는다)
set -e
cd "$(dirname "$0")/.."

COMPOSE="docker compose -f infra/langfuse/compose.yaml --env-file .env"

if [ "$1" = "stop" ]; then
    # 컨테이너만 멈춘다. 볼륨(데이터)은 지우지 않는다.
    $COMPOSE stop
    exit 0
fi

# 컨테이너 6개를 백그라운드로 기동한다.
$COMPOSE up -d

# web이 응답할 때까지 최대 120초 기다린다. 처음 올릴 때는 DB 준비 때문에 1분 가까이 걸릴 수 있다.
echo "web 응답 대기 중..."
for i in $(seq 1 60); do
    code=$(curl -s -o /dev/null -w "%{http_code}" --max-time 2 http://localhost:3000/api/public/health || true)
    if [ "$code" = "200" ]; then
        echo "Langfuse 준비됨: http://localhost:3000"
        exit 0
    fi
    sleep 2
done

echo "120초 안에 준비되지 않았습니다. 상태 확인: $COMPOSE ps" >&2
exit 1
