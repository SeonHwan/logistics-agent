import sys

sys.path.insert(0, "src/phase3")
sys.path.insert(0, "src/phase4")
from draw import save_png
from graph import build_team_graph

# 승인·검증 노드를 끼운 팀 그래프의 구조만 그린다. 그래프를 만드는 것만으로는 모델 호출이 일어나지 않는다.
# 체크포인터는 구조 그림에 영향이 없어 넣지 않는다.
app = build_team_graph(approval=True, verify=True)
print("PNG:", save_png(app, "data/approval_graph.png", "team graph with approval and verify"))
