import asyncio
import json
import sys
from datetime import datetime

from ragas.metrics.collections import AnswerRelevancy, Faithfulness, InstanceSpecificRubrics

sys.path.insert(0, "src/phase6")
from judge import build_embeddings, build_judge_llm

# 저장된 팀 실행 2건에 RAGAS 지표 세 개를 적용한다. 채점 모델 gpt-5.6-terra.
# 건당 모델 호출 6회: Faithfulness 2(쪼개기, 대조) + AnswerRelevancy 3(질문 역생성 x3) + 루브릭 1. 2건이면 12회.
# 채점 모델 호출은 llm.agenerate를 감싸 기록한다(프롬프트 길이와 구조화 출력 원문). 토큰 수는 RAGAS가 돌려주지 않아 재지 못한다.
SAMPLES = [
    ("병목+센터", "data/phase5_20261020_170452.json"),
    ("화물차 도로", "data/phase5_20261021_143708.json"),
]

# 루브릭(채점 기준표): 우리가 겪은 실패 유형을 점수대별로 적었다. 정답은 주지 않는다.
RUBRICS = {
    "score1_description": "근거에 없는 단정을 했다. 도로 용량·혼잡 자료가 없는데 병목이나 정체 지점이라고 단정했거나, 분석가 도구로 할 수 없는 분석을 해 주겠다고 제안했거나, 근거에 없는 숫자를 썼다.",
    "score2_description": "한계 문구는 있으나 결론이 한계와 어긋난다. 예: 한계를 말하면서도 결론에서는 병목이라고 단정한다.",
    "score3_description": "한계는 지켰으나 일부 문장이 근거보다 강하게 단정하거나, 질문에 답하지 못한 부분을 얼버무렸다.",
    "score4_description": "근거에 있는 내용만 쓰고 한계를 지켰으며, 사소한 표현 과장만 있다.",
    "score5_description": "근거에 없는 단정이 없고, 근거가 밝힌 한계를 모두 지키며, 답하지 못한 부분을 숨기지 않고 분명히 말했다.",
}

calls = []  # 채점 모델 호출 기록


def record_calls(llm):
    # instructor가 재시도하면 같은 agenerate 안에서 요청이 여러 번 나간다. 그래서 agenerate가 아니라 실제 요청(client.chat.completions.create)을 센다.
    original_create = llm.client.chat.completions.create
    requests_made = []

    async def counted_create(*args, **kwargs):
        requests_made.append({"response_model": getattr(kwargs.get("response_model"), "__name__", None)})
        return await original_create(*args, **kwargs)

    llm.client.chat.completions.create = counted_create

    original = llm.agenerate

    async def wrapped(prompt, response_model):
        before = len(requests_made)
        result = await original(prompt, response_model)
        calls.append({"model": response_model.__name__, "prompt_chars": len(prompt),
                      "requests": len(requests_made) - before, "output": result.model_dump()})
        return result

    llm.agenerate = wrapped
    return requests_made


async def main():
    llm = build_judge_llm()
    requests_made = record_calls(llm)
    embeddings = build_embeddings()

    # 점검(모델 호출 없음): 임베딩 어댑터가 동작하고 지표 객체가 만들어지는지
    vector = embeddings.embed_text("점검")
    print(f"임베딩 점검: 차원 {len(vector)}")
    faithfulness = Faithfulness(llm=llm)
    relevancy = AnswerRelevancy(llm=llm, embeddings=embeddings)
    rubric = InstanceSpecificRubrics(llm=llm)
    print("지표 객체 생성 OK\n")

    records = []
    for label, path in SAMPLES:
        saved = json.load(open(path, encoding="utf-8"))
        question, answer = saved["question"], saved["answer"]
        contexts = [item["text"] for item in saved["results"]]
        print(f"===== {label} ({path.split('/')[-1]}) =====")
        print("질문:", question)

        start = len(calls)
        f = await faithfulness.ascore(user_input=question, response=answer, retrieved_contexts=contexts)
        r = await relevancy.ascore(user_input=question, response=answer)
        c = await rubric.ascore(rubrics=RUBRICS, user_input=question, response=answer, retrieved_contexts=contexts)
        sample_calls = calls[start:]

        print(f"Faithfulness     : {f.value}")
        print(f"AnswerRelevancy  : {r.value}")
        print(f"루브릭(1~5)      : {c.value}")
        print(f"  루브릭 피드백  : {c.reason}")
        print(f"agenerate {len(sample_calls)}회, 실제 요청 {sum(x['requests'] for x in sample_calls)}회 (종류와 요청 수: {[(x['model'], x['requests']) for x in sample_calls]})")
        verdicts = [s for x in sample_calls if "statements" in x["output"] for s in x["output"]["statements"] if isinstance(s, dict) and "verdict" in s]
        if verdicts:
            bad = [s for s in verdicts if not s["verdict"]]
            print(f"Faithfulness 문장 판정: {len(verdicts)}개 중 뒷받침 안 됨 {len(bad)}개")
            for s in bad:
                print("   안 됨:", s["statement"], "|", s["reason"])
        questions = [x["output"].get("question") for x in sample_calls if "question" in x["output"]]
        print("AnswerRelevancy가 답에서 거꾸로 만든 질문:", questions)
        print()
        records.append({"label": label, "source": path, "question": question, "faithfulness": f.value, "answer_relevancy": r.value,
                        "rubric": c.value, "rubric_feedback": c.reason, "calls": sample_calls})

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out = f"data/phase6_eval_{stamp}.json"
    json.dump({"rubrics": RUBRICS, "records": records}, open(out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("저장:", out)


asyncio.run(main())
