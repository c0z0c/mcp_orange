"""폴더 트리의 (상대경로, 크기, 수정시각) 목록을 해시로 남기고 비교한다.
테스트용 Orange 설치(D:\\Orange3-3.32.0, D:\\Orange3-3.40.0)를 *수정하지 않았는지* 확인하는 용도.

    python snapshot_tree.py save  <폴더> <결과.json>
    python snapshot_tree.py diff  <폴더> <결과.json>      (다르면 종료코드 1)
"""
import hashlib
import json
import os
import sys


def snapshot(root):
    entries = {}
    for dp, dns, fns in os.walk(root):
        for n in fns:
            p = os.path.join(dp, n)
            try:
                st = os.stat(p)
            except OSError:
                continue
            entries[os.path.relpath(p, root)] = (st.st_size, int(st.st_mtime))
        for n in dns:  # 빈 폴더/새 폴더 생성도 잡는다
            entries[os.path.relpath(os.path.join(dp, n), root) + os.sep] = (0, 0)
    digest = hashlib.sha1(json.dumps(sorted(entries.items())).encode()).hexdigest()
    return {"root": root, "count": len(entries), "digest": digest, "entries": entries}


def main(argv):
    mode, root, out = argv
    snap = snapshot(root)
    if mode == "save":
        with open(out, "w", encoding="utf-8") as f:
            json.dump(snap, f)
        print("saved %d entries, digest %s" % (snap["count"], snap["digest"][:12]))
        return 0
    with open(out, encoding="utf-8") as f:
        old = json.load(f)
    if old["digest"] == snap["digest"]:
        print("UNCHANGED %s (%d entries)" % (root, snap["count"]))
        return 0
    o, n = old["entries"], snap["entries"]
    added = sorted(set(n) - set(o))
    removed = sorted(set(o) - set(n))
    changed = sorted(k for k in set(o) & set(n) if tuple(o[k]) != tuple(n[k]))
    print("CHANGED %s: +%d -%d ~%d" % (root, len(added), len(removed), len(changed)))
    for tag, lst in (("+", added), ("-", removed), ("~", changed)):
        for k in lst[:15]:
            print("  %s %s" % (tag, k))
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
