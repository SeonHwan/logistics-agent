import re
import sys
import zipfile

# .hwpx는 zip 안의 XML이다. Contents/section*.xml 에서 글자(hp:t)와 표 구분을 뽑는다. 외부 데이터이므로 정규식으로 글자만 꺼낸다.
path = sys.argv[1]
z = zipfile.ZipFile(path)
sections = sorted(n for n in z.namelist() if re.search(r"Contents/section\d+\.xml$", n))
print("섹션 파일:", sections, file=sys.stderr)
for name in sections:
    xml = z.read(name).decode("utf-8")
    # 문단(hp:p) 단위로 나눠서 각 문단의 글자(hp:t)를 이어 붙인다.
    for paragraph in re.findall(r"<hp:p\b.*?</hp:p>", xml, flags=re.S):
        pieces = re.findall(r"<hp:t[^>]*>(.*?)</hp:t>", paragraph, flags=re.S)
        text = "".join(pieces).strip()
        if text:
            print(re.sub(r"<[^>]+>", "", text))
