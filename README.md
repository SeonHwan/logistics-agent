# logistics-agent

공개 물류 데이터(KTDB 화물 OD)를 근거로 물류센터 입지·거점 질문에 답하는 **LangGraph 멀티 에이전트**입니다.
질문을 supervisor가 분석가에게 나누고, 분석가들이 병렬로 계산 도구를 호출하고, 취합한 답을 사람이 승인하고 두 모델이 검증합니다.
숫자 계산은 모델이 아니라 파이썬 도구가 하고, 모델은 계획·해석·종합을 맡습니다.

## AI Agent 단계별 프로젝트

AI Agent를 단계별로 만들어 가는 5개 프로젝트 중 **4번째**입니다. 앞 프로젝트에서 남은 한계가 다음 프로젝트를 시작한 이유입니다.

| 순서 | 프로젝트 | 다룬 것 | 남은 한계 → 다음 단계 |
|---|---|---|---|
| 1 | [game-wiki-rag](https://github.com/SeonHwan/game-wiki-rag) | 가상 게임 위키 4문서로 RAG 기본 파이프라인, 하이브리드·리랭커·Contextual Retrieval·GraphRAG, tool-use 에이전트, MCP, LangGraph 기반 Adaptive/Self-RAG | 데이터와 평가 질문이 너무 작아(문서 4개, 질문 12개) 오케스트레이션, 답변 품질 개선, 여러 RAG 기법의 효과를 제대로 확인하기 어려움 → 실제 방대한 데이터로 다시 |
| 2 | [dart-filing-agent](https://github.com/SeonHwan/dart-filing-agent) | DART 사업보고서 5개사 15건(수만 개 청크): 표 행 단위 청킹, bge-m3 dense+sparse 하이브리드, 리랭커 측정, XBRL 값 조회 스토어 | 문서가 전문용어 중심이라 답변이 나아졌는지 확인하려면 용어부터 이해해야 해서 학습 진도가 더딤 → 일반 상식에 가까운 데이터로 |
| 3 | [encykorea-agent](https://github.com/SeonHwan/encykorea-agent) | 한국민족문화대백과사전 15,836건(청크 75,122개): hybrid 검색, 답변 생성 방식 비교, 직접 구현한 도구 호출 에이전트 | RAG 성격이 강해 에이전트 역량을 보여 주는 증거로 약하다고 판단 → 멀티 에이전트·오케스트레이션·LangGraph를 배우는 별도 프로젝트 |
| 4 | **[logistics-agent](https://github.com/SeonHwan/logistics-agent)** | 공개 물류 데이터(KTDB 화물 OD)와 정답이 계산되는 합성 시나리오: LangGraph 멀티 에이전트(supervisor, 병렬 분석가, 취합), 검증 노드, 사람 승인, Langfuse 관측, RAGAS 채점 | 병렬로 도는 에이전트를 더 늘려 멀티 에이전트의 효과를 눈으로 확인하고, MCP 분리와 서빙도 함께 다루려고 → 새 프로젝트로 |
| 5 | [kitchen-agent](https://github.com/SeonHwan/kitchen-agent) | 가상 주방 데이터와 6명의 전문 에이전트(LangGraph), 도구의 MCP 분리, RAGAS 평가, FastAPI 서빙 | — |

### 이전 단계([encykorea-agent](https://github.com/SeonHwan/encykorea-agent))에서 남은 한계
검색과 답변 생성(RAG)의 비중이 커서 에이전트 역량을 보여 주는 증거로는 약하다고 판단했습니다.

### 이번 단계에서 바꾼 것
검색 중심에서 벗어나, 숫자 계산을 도구로 분리해야만 답이 나오는 문제(입지·병목·수송수단)를 골랐습니다. 직접 구현한 도구 호출 루프를 LangGraph로 다시 배선해 그래프가 무엇을 대신하는지 확인하고, supervisor 라우팅, `Send` 병렬 분기, 취합, 사람 승인(`interrupt`), 조건부 재시도 같은 오케스트레이션을 다뤘습니다.

### 이 프로젝트의 한계가 다음 단계로 이어진 이유
이 프로젝트는 Phase 6(평가·관측성)까지 다뤘습니다. 도구를 MCP 서버로 분리하는 것과 서빙(FastAPI + Docker)은 여기서 하지 않고, 병렬로 도는 에이전트를 더 늘려 멀티 에이전트의 효과를 눈으로 확인하는 다음 프로젝트 [kitchen-agent](https://github.com/SeonHwan/kitchen-agent)에서 함께 다루기로 했습니다.

## 구조

```
질문 → supervisor ─┬─ (범위 밖) → decline
                   └─ 분석가 선택 ─(Send, 병렬)→ analyst_run ─→ [approve] ─→ synthesize ─→ [verify_one ×2 → judge]
                                                                                 ▲                   │ 실패(최대 1회)
                                                                                 └───────────────────┘
```

- **supervisor**: 모델이 JSON으로 분석가를 고릅니다. 분석가 설명(하는 일, 예시 질문, 맡지 않는 것)을 지시문에 넣습니다.
- **분석가 5명**: `concentration`(물동량 집중도), `location`(센터 입지 운송비), `mode`(도로·철도·항공 비중), `container`(컨테이너 거점), `road_load`(화물차 부하 순위). 분석가마다 자기 도구만 가집니다.
- **approve**(선택): `interrupt()`로 분석가 결과를 보여 주고 멈춥니다. 응답이 정확히 `yes`일 때만 승인으로 보고 그 밖은 모두 거절입니다.
- **verify**(선택): `claude-opus-5-5`와 `gpt-5.6-terra`가 병렬로 판정하고 한쪽이라도 지적하면 실패입니다. 실패하면 지적 사항을 주고 취합으로 되돌리며 상한은 1회입니다. 판정 JSON 파싱에 실패하면 통과가 아니라 실패로 처리합니다.

### 계산 도구 (`src/phase2/tools.py`)

| 도구 | 하는 일 |
|---|---|
| `list_zones` | 존(시·군·구 252개)을 이름으로 찾기 |
| `zone_concentration` | 존별 (들어오는 양 + 나가는 양)을 존 평균과 비교한 배수. 도로 용량 대비 혼잡이 **아니라** 물동량 집중도 |
| `center_cost` / `best_centers` | 후보지에 센터 한 곳을 두고 전국 수요를 직선 거리로 공급할 때의 총 운송비, 후보 249곳 중 최저 순위 |
| `container_hubs` | 컨테이너 물동량 집중도 |
| `mode_share` | 도로·철도·항공 물량 비중(2024) |
| `road_load` | 도로망에 화물차 OD를 전량 배정해 구한 링크별 부하 순위. 혼잡·병목 판정에는 쓰지 않음 |

각 도구는 결과와 함께 가정(`ASSUMPTIONS`)을 돌려줍니다. 에이전트가 답변에 한계를 쓰게 하려는 설계입니다.

## 데이터와 평가

- **데이터**: KTDB 화물 OD(도로 물동량, 톤급별 화물차 통행량, 철도·항공 물동량), 252개 존, 도로망(링크 92,771개). 원본은 저장소에 없고 `data/raw/`에 직접 받아 둡니다.
- **가정값은 코드에 숨기지 않습니다.** 운송 단가는 안전운송원가(25톤 777원/km ÷ 25톤 = 약 31.08원/톤·km, 적재율 100% 가정의 하한)에서 시작해 파라미터로 두었고, 근거를 찾지 못한 값(차종 환산계수 1.0/1.5/2.5, 우회 계수 1.0)도 파라미터로 두고 `docs/decisions.md`에 근거 없음이라고 적었습니다.
- **정답이 계산되는 합성 시나리오 4개**(`src/phase2/synthetic.py`): 단일 수요지, 과반 규칙, 두 지점 같은 비중, 수요 2배 시 규모 불변. 모두 통과하지만 계산 함수의 정의에서 거의 자명하게 나오는 성질이라 **도구 정확성 확인용**이고 에이전트의 판단력을 재는 평가셋이 아닙니다.
- **관측**: Langfuse를 셀프 호스팅(Docker Compose)으로 연결했습니다(`infra/langfuse/compose.yaml`).
- **평가**: RAGAS(Faithfulness, Answer Relevancy, 루브릭)로 저장된 실행 2건을 사후 채점했습니다. 채점 모델은 `gpt-5.6-terra`입니다.

## 한계

- **검증 재시도 상한(1회)을 넘기면 실패한 채로 끝납니다.** 상한 값은 별다른 근거 없이 제가 정했습니다.
- **병목은 약한 정의입니다.** 기본 병목 지표는 물동량 집중도이고, 도로 배정(`road_load`)은 화물차 부하 순위일 뿐 혼잡도가 아닙니다. 배정 결과는 실측(TMS)과 대조하지 못했습니다. 도로망 좌표계(EPSG:5179가 아님)를 확인하지 못해 외부 좌표와 맞추는 검증을 접었습니다.
- **운송비의 절대 금액은 하한입니다.** 직선 거리, 같은 존 안 이동 0원, 적재율 100% 가정이라 후보 간 상대 비교에만 의미가 있습니다. 외부 통계와 대조하지 않았습니다.
- **품목별 분석은 하지 않았습니다.** 엑셀의 품목 열 번호와 설명자료 코드의 대응이 확정되지 않았습니다.
- **Phase 5, 6의 일부 코드는 리뷰를 거치지 않았습니다.**
- `docs/decisions.md`의 수치와 판정 중 일부는 확인에 쓰고 지운 스크립트로 낸 과거 기록이라 이 저장소에서 다시 실행할 수 없습니다.

## 실행

`.env`에 `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`와 Langfuse 키가 필요하고, 데이터(`data/`)는 저장소에 없습니다. 모델 호출은 비용이 듭니다.

```bash
uv sync

uv run python src/phase1/convert.py            # 원본 엑셀 → Parquet
uv run python src/phase2/prepare.py            # 존·거리·흐름 준비 테이블
uv run python src/phase2/synthetic.py          # 합성 시나리오 4개 검증 (모델 호출 없음)

docker compose -f infra/langfuse/compose.yaml --env-file .env up -d   # Langfuse 서버
uv run python src/phase5/run_approval.py "질문"   # 팀 그래프 한 번 실행 + 터미널에서 승인(yes)
uv run python src/phase6/eval_ragas.py         # data/에 저장된 실행 2건의 RAGAS 사후 채점
```

자세한 결정과 측정 근거는 `docs/decisions.md`에 있습니다.
