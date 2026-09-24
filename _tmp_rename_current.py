# -*- coding: utf-8 -*-
"""
Temporary fix: rename ST-20260927 skeleton files removing _CURRENT suffix,
update public/api/list.json entries correspondingly, push to GitHub.
"""
import json
import os
import shutil

ROOT = os.path.dirname(os.path.abspath(__file__))
DATA_HIST = os.path.join(ROOT, "data", "history")
PUB_HIST = os.path.join(ROOT, "public", "data", "history")
LIST_JSON = os.path.join(ROOT, "public", "api", "list.json")


def main():
    updated = []
    # rename files in data/history
    for fname in list(os.listdir(DATA_HIST)):
        if fname.startswith("ST-20260927-") and fname.endswith("_CURRENT.json"):
            new = fname.replace("_CURRENT.json", ".json")
            src = os.path.join(DATA_HIST, fname)
            dst = os.path.join(DATA_HIST, new)
            shutil.move(src, dst)
            print(f"  DATA rename: {fname} -> {new}")
    # rename files in public/data/history
    for fname in list(os.listdir(PUB_HIST)):
        if fname.startswith("ST-20260927-") and fname.endswith("_CURRENT.json"):
            new = fname.replace("_CURRENT.json", ".json")
            src = os.path.join(PUB_HIST, fname)
            dst = os.path.join(PUB_HIST, new)
            shutil.move(src, dst)
            print(f"  PUB  rename: {fname} -> {new}")
            updated.append(new)
    # update list.json entries — replace _CURRENT entries with clean ones
    with open(LIST_JSON, "r", encoding="utf-8") as f:
        lj = json.load(f)
    new_list = []
    cnt = 0
    for item in lj["race_files"]:
        if "ST-20260927-" in item and "_CURRENT" in item:
            clean = item.replace("_CURRENT.json", ".json")
            new_list.append(clean)
            cnt += 1
        else:
            new_list.append(item)
    lj["race_files"] = new_list
    lj["total"] = len(new_list)
    with open(LIST_JSON, "w", encoding="utf-8") as f:
        json.dump(lj, f, ensure_ascii=False, indent=4)
    print(f"\n  [LIST] updated={cnt}  total={lj['total']}")

if __name__ == "__main__":
    main()
    print("\n  Done. Next step: git add + commit + push.")
