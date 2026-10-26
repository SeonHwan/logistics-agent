import sys
import zipfile
from pathlib import Path


def decode_name(raw_name):
    # 윈도우에서 만든 zip은 한글 파일명을 cp949로 저장한다. 파이썬은 cp437로 읽으므로 되돌려 읽는다.
    try:
        return raw_name.encode("cp437").decode("cp949")
    except (UnicodeEncodeError, UnicodeDecodeError):
        return raw_name


def extract(zip_path, out_dir):
    # out_dir은 비어 있는 새 폴더여야 한다.
    out_dir = Path(out_dir).resolve()
    if out_dir.exists() and any(out_dir.iterdir()):
        raise SystemExit(f"비어 있지 않은 폴더입니다: {out_dir}")
    out_dir.mkdir(parents=True, exist_ok=True)

    with zipfile.ZipFile(zip_path) as z:
        for info in z.infolist():
            name = decode_name(info.filename)
            target = (out_dir / name).resolve()
            # zip 안의 경로가 out_dir 밖을 가리키면(../ 등) 건너뛰지 않고 중단한다.
            if out_dir not in target.parents and target != out_dir:
                raise SystemExit(f"폴더 밖으로 나가는 경로입니다: {name}")
            if info.is_dir():
                target.mkdir(parents=True, exist_ok=True)
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            with z.open(info) as src, open(target, "wb") as dst:
                while True:
                    block = src.read(1024 * 1024)
                    if not block:
                        break
                    dst.write(block)
            print(f"{target.stat().st_size:>12,}  {target.relative_to(out_dir)}")


if __name__ == "__main__":
    extract(sys.argv[1], sys.argv[2])
