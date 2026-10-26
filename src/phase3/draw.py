import subprocess
import sys

sys.path.insert(0, "src/phase3")


def to_dot(app, title=""):
    # 컴파일된 LangGraph 그래프의 노드와 엣지를 Graphviz DOT 텍스트로 바꾼다. 네트워크를 쓰지 않는다.
    graph = app.get_graph()

    lines = ["digraph G {"]
    # 다크 모드 IDE에서 보기 좋게 배경을 검정으로 두고, 선·제목·선 라벨은 밝은 색으로 그린다.
    lines.append('  bgcolor="black"; rankdir=TB; nodesep=0.5; ranksep=0.6;')
    lines.append('  node [fontname="NanumGothic, Noto Sans CJK KR, sans-serif", fontsize=13, shape=box, style="rounded,filled", fillcolor="#f2f0ff", color="#5b4fd6"];')
    lines.append('  edge [fontname="NanumGothic, Noto Sans CJK KR, sans-serif", fontsize=11, color="#cccccc", fontcolor="#cccccc"];')
    if title:
        lines.append(f'  labelloc=t; label="{title}"; fontsize=15; fontcolor="white";')

    # 노드: 시작과 끝은 원 모양으로 따로 그린다.
    for node_id in graph.nodes:
        if node_id == "__start__":
            lines.append(f'  "{node_id}" [label="START", shape=circle, fillcolor="#e8f5e9", color="#2e7d32"];')
        elif node_id == "__end__":
            lines.append(f'  "{node_id}" [label="END", shape=doublecircle, fillcolor="#fdecea", color="#c62828"];')
        else:
            lines.append(f'  "{node_id}" [label="{node_id}"];')

    # 엣지: 조건부 엣지는 점선, 일반 엣지는 실선. 조건 이름(data)이 있으면 라벨로 붙인다.
    for edge in graph.edges:
        style = "dashed" if edge.conditional else "solid"
        label = f', label="{edge.data}"' if edge.data else ""
        lines.append(f'  "{edge.source}" -> "{edge.target}" [style={style}{label}];')

    lines.append("}")
    return "\n".join(lines)


def save_png(app, png_path, title=""):
    # DOT 텍스트를 만들어 dot 프로그램으로 PNG로 그린다. dot이 없으면 DOT 파일만 남기고 알린다.
    dot_text = to_dot(app, title)
    dot_path = png_path.rsplit(".", 1)[0] + ".dot"
    with open(dot_path, "w", encoding="utf-8") as f:
        f.write(dot_text)
    try:
        subprocess.run(["dot", "-Tpng", "-Gdpi=150", dot_path, "-o", png_path], check=True)
    except FileNotFoundError:
        print("dot 프로그램이 없어 DOT 파일만 저장했습니다:", dot_path)
        return None
    return png_path

