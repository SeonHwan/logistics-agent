import os

from dotenv import load_dotenv


def make_config():
    # 그래프나 모델을 실행할 때 넘길 config를 만든다: graph.invoke(입력, config=make_config()).
    # Langfuse 키가 .env에 없으면 callbacks 없이 돌아가서, 서버가 꺼져 있어도 프로젝트가 멈추지 않는다.
    load_dotenv()
    if not (os.environ.get("LANGFUSE_PUBLIC_KEY") and os.environ.get("LANGFUSE_SECRET_KEY")):
        return {}

    # 패키지는 여기서 불러온다. 설치되어 있지 않은 환경에서도 이 모듈을 불러올 수 있게 하기 위해서다.
    from langfuse.langchain import CallbackHandler

    return {"callbacks": [CallbackHandler()]}


def flush():
    # 핸들러는 기록을 모아서 나중에 보낸다. 짧게 끝나는 스크립트는 끝나기 전에 서버로 보내도록 비워 줘야 한다.
    if not os.environ.get("LANGFUSE_PUBLIC_KEY"):
        return
    from langfuse import get_client

    get_client().flush()
