import sys
from html.parser import HTMLParser


class TableText(HTMLParser):
    # 표(table)의 행(tr)마다 셀(td, th) 글자를 모아 한 줄로 낸다. 표 밖 글자는 무시한다.
    def __init__(self):
        super().__init__()
        self.table_depth = 0
        self.cell_parts = None
        self.row = None
        self.table_index = 0

    def handle_starttag(self, tag, attrs):
        if tag == "table":
            self.table_depth += 1
            if self.table_depth == 1:
                self.table_index += 1
                print(f"\n=== 표 {self.table_index}")
        elif tag == "tr" and self.table_depth > 0:
            self.row = []
        elif tag in ("td", "th") and self.table_depth > 0:
            self.cell_parts = []

    def handle_endtag(self, tag):
        if tag in ("td", "th") and self.cell_parts is not None and self.row is not None:
            self.row.append("".join(self.cell_parts).strip())
            self.cell_parts = None
        elif tag == "tr" and self.row is not None:
            if any(self.row):
                print(" | ".join(self.row))
            self.row = None
        elif tag == "table" and self.table_depth > 0:
            self.table_depth -= 1

    def handle_data(self, data):
        if self.cell_parts is not None:
            self.cell_parts.append(data.replace("\n", " "))


if __name__ == "__main__":
    parser = TableText()
    parser.feed(open(sys.argv[1], encoding="utf-8").read())
