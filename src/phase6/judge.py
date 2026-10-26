from dotenv import load_dotenv
from openai import AsyncOpenAI
from ragas.llms.base import llm_factory

# RAGAS 채점 모델(gpt-5.6-terra) 만들기. 평가 스크립트들이 같이 쓴다.
# RAGAS는 모델 이름이 'gpt-<정수>'로 시작할 때만 추론 모델로 보고 요청 인자를 맞춘다(max_tokens -> max_completion_tokens,
# temperature=1, top_p 제거). 'gpt-5.6-terra'는 '5.6'이 정수가 아니라 이 처리를 받지 못해, 기본값(temperature=0.01, top_p=0.1)이
# 그대로 나가 서버가 400으로 거부한다. 그 처리를 생성 뒤에 직접 한다(model_args는 평범한 딕셔너리다).
# 출력 토큰 상한: RAGAS 소스 주석은 추론 모델의 구조화 출력에 4096 이상을 권한다. 그러나 4096은 답이 긴 질문의 Faithfulness 대조에서
# 잘렸다(IncompleteOutputException). 이 상한은 추론 토큰까지 포함하므로 16384로 올렸다.
MAX_COMPLETION_TOKENS = 16384
JUDGE_MODEL = "gpt-5.6-terra"


def build_judge_llm():
    load_dotenv(".env")
    client = AsyncOpenAI()
    llm = llm_factory(JUDGE_MODEL, client=client)
    llm.model_args["temperature"] = 1.0
    llm.model_args.pop("top_p", None)
    llm.model_args.pop("max_tokens", None)
    llm.model_args["max_completion_tokens"] = MAX_COMPLETION_TOKENS
    return llm


# 임베딩: fastembed(Qdrant 팀 라이브러리)의 multilingual-e5-large를 RAGAS가 요구하는 형식(BaseRagasEmbedding)으로 감싼다.
# 추상 메서드는 embed_text, aembed_text 둘뿐이고 여러 문장 버전은 기반 클래스가 개별 호출로 처리해 준다.
# e5 계열 모델 카드는 입력 앞에 'query: ' 같은 접두어를 권하는 것으로 기억하나 확인하지 않았고, 여기서는 붙이지 않는다.
EMBED_MODEL = "intfloat/multilingual-e5-large"


def build_embeddings():
    import asyncio

    from fastembed import TextEmbedding
    from ragas.embeddings.base import BaseRagasEmbedding

    class FastEmbedAdapter(BaseRagasEmbedding):
        def __init__(self):
            super().__init__()
            self.model = TextEmbedding(model_name=EMBED_MODEL, cache_dir="data/fastembed_cache")

        def embed_text(self, text, **kwargs):
            return list(self.model.embed([text]))[0].tolist()

        async def aembed_text(self, text, **kwargs):
            return await asyncio.to_thread(self.embed_text, text)

    return FastEmbedAdapter()
