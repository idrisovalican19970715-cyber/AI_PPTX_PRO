import sys, hashlib
sys.stdout.reconfigure(encoding="utf-8")
from pptx import Presentation

for path in [
    r"c:\Users\PC\Downloads\AI_Presentation (9).pptx",
    r"c:\Users\PC\Downloads\AI_Presentation (10).pptx",
]:
    try:
        prs = Presentation(path)
    except Exception as e:
        print(f"{path}: ERROR {e}")
        continue
    print("=" * 70)
    print(path.split("\\")[-1])
    hashes = []
    for i, sl in enumerate(prs.slides):
        for sh in sl.shapes:
            if sh.shape_type == 13:
                h = hashlib.md5(sh.image.blob).hexdigest()[:16]
                hashes.append((i + 1, h, len(sh.image.blob)))
    for row in hashes:
        print(f"  slide {row[0]}: {row[2]:>8} bytes  md5={row[1]}")
    u = len(set(x[1] for x in hashes))
    print(f"  TOTAL {len(hashes)} images, {u} unique")
    print()
