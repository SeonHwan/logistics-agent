def text_of(content):
    # 모델 응답 content는 문자열이거나 블록 목록이다. 문자열이면 그대로 돌려준다.
    if isinstance(content, str):
        return content

    # 블록 목록이면 type이 "text"인 블록의 글만 이어 붙인다(thinking 블록 등은 건너뛴다).
    text = ""
    for block in content:
        if isinstance(block, dict) and block.get("type") == "text":
            text += block.get("text", "")
    return text
