# -*- coding: utf-8 -*-
"""
_auto_populate_full_entries.py （手動 / 俾 URL 模式專用）
========================================================
用途：
  你俾咗 HKJC racecard 網址之後，直接跑呢條 script，就會自動：
    1. parse 所有該賽馬日（或指定場次）嘅 HKJC racecard
    2. 全數更新 entries / horses：
        last_6 / name / jockey(去減磅綴) / trainer / draw / rating / weight / gear /
        best_time_sec / last_3
    3. 更新 race_info.post_time / num_horses / class / distance_m / track / going
    4. 更新 meta.note / meta.import_from / meta.update_time
    5. ⭐ 保留舊動態欄位：odds_win / odds_place / finish / margin / run_time /
       全部 cc_* 欄 / official_result / payouts / split_times
    6. 可選 --push：自動 git add / commit / push → Vercel auto deploy

用法 1（俾 URL 全自動，推薦）：
  python _auto_populate_full_entries.py --url "https://racing.hkjc.com/zh-hk/local/information/racecard?racedate=2026/10/01&Racecourse=ST&RaceNo=1"

用法 2（指定日期 + 自動偵測場地 + 全 N 場）：
  python _auto_populate_full_entries.py --date 2026-10-01

用法 3（單場）：
  python _auto_populate_full_entries.py --date 2026-10-01 --venue ST --race-no 5

用法 4（做完即 push 去 Vercel）：
  python _auto_populate_full_entries.py --date 2026-10-01 --push

作者：AI 賽馬系統 · 與 _auto_bootstrap_next_raceday.py 共用 parser，確保靜態欄 100% 一致。
"""
import sys
import os
import re
import json
import argparse
import subprocess
from datetime import datetime
from collections import OrderedDict

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)

import _auto_bootstrap_next_raceday as _boot  # 直接重用 parser + _write_current_for


def _parse_url_targets(url):
    """從 URL 提取 date_slash / venue / race_nums.
    e.g. zh-hk URL 或 information/chinese/Racecard.aspx 都兼容。
    """
    mdate = re.search(r'racedate[=:]\s*(\d{4})[-/](\d{1,2})[-/](\d{1,2})', url, re.IGNORECASE)
    mvenue = re.search(r'Racecourse[=:]\s*(ST|HV)', url, re.IGNORECASE)
    mrn = re.search(r'RaceNo[=:]\s*(\d{1,2})', url, re.IGNORECASE)
    if not mdate:
        raise RuntimeError(f"URL 缺少 racedate 參數：{url}")
    y, m, d = mdate.group(1), mdate.group(2), mdate.group(3)
    date_slash = f"{int(y):04d}/{int(m):02d}/{int(d):02d}"
    date_dash = f"{int(y):04d}-{int(m):02d}-{int(d):02d}"
    vc = None
    if mvenue:
        vc = mvenue.group(1).upper()
    race_nums = None
    if mrn:
        race_nums = [int(mrn.group(1))]
    return date_slash, date_dash, vc, race_nums


def _resolve_venue_races(date_slash, vc=None):
    """若 URL / CLI 冇俾 venue 或 race_nums，自動偵測。"""
    venue_cn, vc2, nums = _boot._get_num_races_and_venue(date_slash)
    if vc and vc2 and vc.upper() != vc2:
        print(f"[WARN] CLI --venue={vc.upper()} 與 HKJC 官網={vc2} 唔同，以官網為準")
    return venue_cn, vc2, nums


def _main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default=None, help="HKJC 任何 racecard 頁 URL（單場或首頁都得）")
    ap.add_argument("--date", default=None, help="YYYY-MM-DD 或 YYYY/MM/DD")
    ap.add_argument("--venue", default=None, help="HV / ST（可省略自動偵測）")
    ap.add_argument("--race-no", type=int, default=None, help="單一場次（1..N）；預設所有該日場次")
    ap.add_argument("--skip-rebuild", action="store_true", help="跳過 rebuild_aggregate.ps1")
    ap.add_argument("--push", action="store_true", help="完成後自動 git add -A / commit / push → Vercel deploy")
    args = ap.parse_args()

    summary = OrderedDict([
        ("started_at", datetime.now().strftime("%Y-%m-%d %H:%M:%S")),
        ("date", None),
        ("venue", None),
        ("races_targeted", []),
        ("races_updated", 0),
        ("last6_total_populated", 0),
        ("total_horses", 0),
        ("errors", []),
        ("rebuild_ok", None),
        ("push_ok", None),
    ])

    try:
        if args.url:
            date_slash, date_dash, vc, rns = _parse_url_targets(args.url)
        elif args.date:
            fd = args.date.strip().replace("-", "/")
            m = re.match(r"(\d{4})/(\d{1,2})/(\d{1,2})$", fd)
            if not m:
                raise RuntimeError("--date 格式需為 YYYY-MM-DD 或 YYYY/MM/DD")
            y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
            date_slash = f"{y:04d}/{mo:02d}/{d:02d}"
            date_dash = f"{y:04d}-{mo:02d}-{d:02d}"
            vc = (args.venue or "").upper() or None
            rns = None
        else:
            raise RuntimeError("必須提供 --url 或 --date 其中一個")

        venue_cn, vc2, all_nums = _resolve_venue_races(date_slash, vc=vc)
        vc = vc2
        target_rns = [args.race_no] if args.race_no else (rns or all_nums)
        target_rns = [r for r in target_rns if r in set(all_nums)]
        if not target_rns:
            raise RuntimeError(f"無有效場次（all={all_nums}, target={[args.race_no] if args.race_no else rns}）")

        summary["date"] = date_dash
        summary["venue"] = f"{vc} ({venue_cn})"
        summary["races_targeted"] = target_rns

        print(f"[POPULATE] Target: {date_dash} {venue_cn} ({vc}) races {target_rns}")
        updated_files = []
        total_horses = 0
        last6_count = 0
        for rn in target_rns:
            import_url = (
                f"https://racing.hkjc.com/racing/information/chinese/Racing/Racecard.aspx?"
                f"racedate={date_slash}&Racecourse={vc}&RaceNo={rn}"
            )
            try:
                html = _boot._scraper_mod.fetch_url(import_url, retries=3, delay=2)
            except Exception as e:
                summary["errors"].append(f"R{rn} fetch fail: {e}")
                continue
            if not html or len(html) < 3000:
                summary["errors"].append(f"R{rn} empty ({len(html or '')} bytes)")
                continue
            try:
                obj = _boot._parse_racecard_page(html, date_slash, vc, rn, import_url)
                path, skipped = _boot._write_current_for(obj)
                updated_files.append(os.path.basename(path))
                nh = obj["race_info"]["num_horses"]
                l6c = sum(1 for h in obj.get("horses", []) if h.get("last_6"))
                total_horses += nh
                last6_count += l6c
                print(f"  [OK] R{rn}: {os.path.basename(path)} horses={nh} last6_populated={l6c}/{nh} post_time={obj['race_info']['post_time']}")
            except Exception as e:
                import traceback
                traceback.print_exc()
                summary["errors"].append(f"R{rn} parse/write fail: {e}")

        summary["races_updated"] = len(updated_files)
        summary["total_horses"] = total_horses
        summary["last6_total_populated"] = last6_count

        if summary["races_updated"] > 0 and not args.skip_rebuild and os.path.isfile(_boot.REBUILD_PS1):
            print("[REBUILD] Running rebuild_aggregate.ps1 ...")
            try:
                proc = subprocess.run(
                    ["powershell.exe", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass",
                     "-File", _boot.REBUILD_PS1],
                    cwd=ROOT, timeout=300, check=False,
                )
                summary["rebuild_ok"] = (proc.returncode == 0)
            except Exception as e:
                summary["errors"].append(f"rebuild fail: {e}")
                summary["rebuild_ok"] = False
    except Exception as e_t:
        import traceback
        traceback.print_exc()
        summary["errors"].append(f"top-level: {e_t}")

    if args.push and summary["races_updated"] > 0:
        print("[PUSH] git add -A → commit → push ...")
        try:
            def _run(cmd, check=False):
                p = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True)
                print(">>", " ".join(cmd))
                if p.stdout.strip():
                    print(p.stdout.strip())
                if p.stderr.strip():
                    print("[STDERR]", p.stderr.strip())
                if check and p.returncode != 0:
                    raise RuntimeError(f"command failed ({p.returncode})")
                return p
            _run(["git", "config", "user.name",  "horseking-bot"])
            _run(["git", "config", "user.email", "horseking-bot@users.noreply.github.com"])
            _run(["git", "add", "-A"])
            msg = (f"Auto populate {date_dash} {vc} R{target_rns[0]}-R{target_rns[-1]}: "
                   f"{summary['last6_total_populated']}/{summary['total_horses']} last6, "
                   f"post_time + entries/gear fully parsed")
            _run(["git", "commit", "--allow-empty", "-m", msg])
            p_push = _run(["git", "push", "--force"])
            summary["push_ok"] = (p_push.returncode == 0)
        except Exception as e_push:
            summary["errors"].append(f"git push fail: {e_push}")
            summary["push_ok"] = False

    summary["finished_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print("\n" + json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if (not summary["errors"]) else 2


if __name__ == "__main__":
    sys.exit(_main())
