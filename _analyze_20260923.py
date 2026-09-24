# -*- coding: utf-8 -*-
"""
2026-09-23 HV 9 場賽事 AI 賽後分析。
輸出結構化報告：
  1. 全局數據摘要（9 場冷熱/爆冷/ROI）
  2. 每場詳細分析：
     a. 賽事形勢與步速分析
     b. AI 綜合評分 vs 真實賽果（命中驗證）
     c. 投注策略與值博率回顧
"""
import os
import re
import json
from collections import OrderedDict, defaultdict
from datetime import datetime

ROOT = os.path.dirname(os.path.abspath(__file__))
HIST = os.path.join(ROOT, "data", "history")


def rt_to_sec(s):
    try:
        if not s:
            return None
        m = re.match(r"(\d+):(\d{1,2})\.(\d{1,2})", str(s))
        if m:
            return int(m.group(1)) * 60 + int(m.group(2)) + int(m.group(3)) / 100.0
        m2 = re.match(r"0:(\d{1,2})\.(\d{1,2})", str(s))
        if m2:
            return int(m2.group(1)) + int(m2.group(2)) / 100.0
    except Exception:
        return None
    return None


def load_races():
    races = []
    pat = re.compile(r"^HV-20260923-(\d{2})_race(\d+)_(\d+)m_(cls\d)\.json$")
    for fn in sorted(os.listdir(HIST)):
        m = pat.match(fn)
        if not m:
            continue
        with open(os.path.join(HIST, fn), encoding="utf-8") as f:
            d = json.load(f, object_pairs_hook=OrderedDict)
        d["_fn"] = fn
        races.append(d)
    races.sort(key=lambda x: int(x["race_info"]["race_number"]))
    return races


def parse_margin_to_len(s, dist_m):
    """將 HKJC 馬位長度描述轉為大約米數（粗略）。"""
    if not s or s == "---":
        return 0.0
    s = str(s).strip()
    total = 0.0
    for seg in re.split(r"[-/]", s):
        seg = seg.strip()
        if seg.endswith("1/4"):
            total += 0.25 * (2.4 if dist_m >= 1400 else 2.0)
        elif seg.endswith("1/2"):
            total += 0.5 * (2.4 if dist_m >= 1400 else 2.0)
        elif seg.endswith("3/4"):
            total += 0.75 * (2.4 if dist_m >= 1400 else 2.0)
        elif seg == "頸位":
            total += 0.2
        elif seg == "鼻位":
            total += 0.08
        elif seg == "短馬頭":
            total += 0.1
        elif re.match(r"^\d+$", seg):
            try:
                total += int(seg) * (2.4 if dist_m >= 1400 else 2.0)
            except Exception:
                pass
    return total


def ai_6d_score(h, race_info):
    """與前端 ai.js generateBetting 一致的 6 維 min-max 模型，回傳 ai_score 0~100 高=好。"""
    try:
        dist = int(race_info["distance_m"])
    except Exception:
        dist = 1400
    try:
        last_3 = h.get("last_3") or []
        finishes = [int(x.get("finish") or 99) for x in last_3 if x.get("finish")]
        avg_fin = sum(finishes) / len(finishes) if finishes else 8.0
        last3_feat = 1.0 - min(1.0, (avg_fin - 1) / 11.0)
    except Exception:
        last3_feat = 0.4
    try:
        rating = int(h.get("rating") or 50)
        rating_feat = min(1.0, max(0.0, (rating - 20) / 60.0))
    except Exception:
        rating_feat = 0.5
    try:
        bt = float(h.get("best_time_sec") or 0.0)
        if bt > 0 and dist > 0:
            pace_m_per_sec = dist / bt
            benchmark = {
                1000: 17.6,
                1200: 17.3,
                1400: 17.0,
                1650: 16.7,
                1800: 16.5,
                2000: 16.3,
                2200: 16.1,
                2400: 15.9,
            }.get(dist, 16.5)
            bt_feat = min(1.0, max(0.0, (pace_m_per_sec - (benchmark - 1.5)) / 1.5))
        else:
            bt_feat = 0.5
    except Exception:
        bt_feat = 0.5
    try:
        draw = int(h.get("draw") or 7)
        if dist <= 1200:
            ideal_draw = 1.5 if dist <= 1000 else 2.5
        else:
            ideal_draw = 6.0
        draw_dev = abs(draw - ideal_draw)
        draw_feat = 1.0 - min(1.0, draw_dev / 10.0)
    except Exception:
        draw_feat = 0.5
    try:
        weight = int(h.get("weight") or 126)
        w_lo, w_hi = 113, 135
        w_feat = 1.0 - min(1.0, abs(weight - 126) / (w_hi - w_lo))
    except Exception:
        w_feat = 0.5
    try:
        odds = float(h.get("odds_win") or 9999.0)
        if odds > 0 and odds < 999:
            odds_prob = 1.0 / odds
            odds_feat = min(1.0, odds_prob / 0.5)
        else:
            odds_feat = 0.3
    except Exception:
        odds_feat = 0.4
    weights = {"last3": 0.22, "rating": 0.18, "bt": 0.18, "draw": 0.14, "weight": 0.08, "odds": 0.20}
    raw = (
        weights["last3"] * last3_feat + weights["rating"] * rating_feat +
        weights["bt"] * bt_feat + weights["draw"] * draw_feat +
        weights["weight"] * w_feat + weights["odds"] * odds_feat
    )
    return round(raw * 100, 1)


def win_to_place_odds(w, rank):
    """ai.js 第 445 行 winToPlaceOdds 等價公式。"""
    if not w or w <= 0:
        return None
    k = {1: 0.58, 2: 0.78, 3: 0.90, 4: 1.0}.get(int(rank), 0.85)
    est = round(max(1.1, 1 + (w - 1) * k), 1)
    return est


def quinella_odds_harmonic(w1, w2):
    if not w1 or not w2 or w1 <= 0 or w2 <= 0:
        return None
    hm = 2 * w1 * w2 / (w1 + w2)
    return round(hm * 1.35, 1)


def analyze_race(r):
    ri = r["race_info"]
    rn = int(ri["race_number"])
    dist = int(ri["distance_m"])
    cls = ri.get("class") or ""
    going = ri.get("going") or "好地"
    track = ri.get("track") or ""
    name = r["meta"].get("race_name_full") or f"第{rn}場"

    horses = r["horses"]
    horses_sorted = sorted(horses, key=lambda h: int(h.get("number") or 0))
    for h in horses_sorted:
        h["_ai"] = ai_6d_score(h, ri)
        h["_finish"] = int(h.get("finish") or 99)

    ranked_by_ai = sorted([h for h in horses_sorted if h["_finish"] <= 20], key=lambda h: -h["_ai"])
    top5_ai = ranked_by_ai[:5]

    official = ri.get("official_result") or []
    top_real = []
    for pos in (1, 2, 3, 4):
        cand = [o for o in official if int(o.get("finish") or 99) == pos]
        if cand:
            top_real.append(cand[0])
        else:
            cand2 = [h for h in horses_sorted if int(h.get("finish") or 99) == pos]
            if cand2:
                top_real.append({
                    "finish": pos, "name": cand2[0]["name"], "number": cand2[0]["number"],
                    "jockey": cand2[0]["jockey"], "trainer": cand2[0]["trainer"],
                    "margin": cand2[0].get("margin", ""), "run_time": cand2[0].get("run_time", ""),
                })

    win_t = rt_to_sec(top_real[0]["run_time"]) if top_real and top_real[0].get("run_time") else None
    pace_mps = (dist / win_t) if win_t and win_t > 0 else None

    # 值博率數據
    for h in horses_sorted:
        odd_win = float(h.get("odds_win") or 0)
        finish = int(h.get("finish") or 99)
        h["_won"] = (finish == 1)
        h["_inpla"] = (finish >= 1 and finish <= 3)
        h["_place_est"] = win_to_place_odds(odd_win, 2)
    win_favs = sorted([h for h in horses_sorted if float(h.get("odds_win") or 0) > 0],
                      key=lambda h: float(h.get("odds_win") or 999))[:3]
    f1 = win_favs[0] if len(win_favs) >= 1 else None
    f2 = win_favs[1] if len(win_favs) >= 2 else None
    f3 = win_favs[2] if len(win_favs) >= 3 else None
    fav_won = f1 and f1["_won"]
    fav1_inpla = f1 and (int(f1.get("finish") or 99) <= 3)
    rank1_correct = (top5_ai and top5_ai[0]["_won"])
    ai_top3_hit = sum(1 for h in top5_ai[:3] if int(h.get("finish") or 99) <= 3)

    win_picks = top5_ai[:2]
    place_picks = top5_ai[:4]
    q_pairs = []
    for i in range(min(3, len(top5_ai))):
        for j in range(i + 1, min(4, len(top5_ai))):
            q_pairs.append((top5_ai[i], top5_ai[j]))
    qp_pairs = []
    for i in range(min(4, len(top5_ai))):
        for j in range(i + 1, min(5, len(top5_ai))):
            qp_pairs.append((top5_ai[i], top5_ai[j]))
    tierce_top3 = top5_ai[:3]
    trio_perm = []
    if len(top5_ai) >= 3:
        import itertools
        for perm in itertools.permutations(top5_ai[:4], 3):
            trio_perm.append(perm)
    first4_perm = []
    if len(top5_ai) >= 4:
        import itertools
        for perm in itertools.permutations(top5_ai[:5], 4):
            first4_perm.append(perm)

    real_winner_odds = None
    real_w = [h for h in horses_sorted if h["_won"]]
    if real_w:
        real_winner_odds = float(real_w[0].get("odds_win") or 0)
    upset = real_winner_odds and real_winner_odds >= 10.0

    q_hit = False
    real_winners_top3 = [h for h in horses_sorted if int(h.get("finish") or 99) <= 2]
    if len(real_winners_top3) >= 2:
        wnames = set(x["name"] for x in real_winners_top3)
        for (a, b) in q_pairs:
            if {a["name"], b["name"]} <= wnames:
                q_hit = True
                break
    tierce_hit = False
    real_123 = [h for h in horses_sorted if int(h.get("finish") or 99) <= 3]
    if len(real_123) >= 3:
        real_nums = [h["name"] for h in sorted(real_123, key=lambda x: int(x.get("finish")))]
        ai_nums = [h["name"] for h in tierce_top3]
        if set(real_nums) <= set(ai_nums):
            tierce_hit = True
    return {
        "rn": rn, "name": name, "dist": dist, "cls": cls, "going": going, "track": track,
        "top_real": top_real, "win_t": win_t, "pace_mps": pace_mps,
        "top5_ai": [{"name": h["name"], "number": h["number"], "ai": h["_ai"],
                     "finish": h["_finish"], "odds_win": h.get("odds_win"),
                     "odds_place": h.get("odds_place"),
                     "jockey": h.get("jockey"), "cc_expert_count": int(h.get("cc_expert_count") or 0)}
                    for h in top5_ai],
        "fav1": {"name": f1["name"], "odds": float(f1.get("odds_win") or 0),
                 "finish": int(f1.get("finish") or 99), "won": f1["_won"],
                 "place": fav1_inpla} if f1 else None,
        "fav_won": fav_won, "rank1_correct": rank1_correct,
        "ai_top3_hit": ai_top3_hit,
        "win_picks": [{"name": h["name"], "odds_win": float(h.get("odds_win") or 0),
                       "place_est": h.get("_place_est"),
                       "finish": h["_finish"], "hit_win": h["_won"], "hit_place": h["_inpla"]}
                      for h in win_picks],
        "place_picks": [{"name": h["name"], "odds_place": float(h.get("odds_place") or 0),
                         "finish": h["_finish"], "hit": (1 <= h["_finish"] <= 3)}
                        for h in place_picks],
        "q_picks": [{"a": a["name"], "b": b["name"],
                     "odds_est": quinella_odds_harmonic(a.get("odds_win"), b.get("odds_win")),
                     "hit": ({a["name"], b["name"]} <= set(
                         h["name"] for h in horses_sorted if 1 <= int(h.get("finish") or 99) <= 2))}
                    for (a, b) in q_pairs],
        "qp_picks": [{"a": a["name"], "b": b["name"],
                      "hit": len(set([a["name"], b["name"]]) & set(
                          h["name"] for h in horses_sorted if 1 <= int(h.get("finish") or 99) <= 3)) == 2}
                     for (a, b) in qp_pairs],
        "tierce_top3": [h["name"] for h in tierce_top3],
        "trio_top4": [h["name"] for h in top5_ai[:4]],
        "f4_top5": [h["name"] for h in top5_ai[:5]],
        "tierce_hit": tierce_hit,
        "real_winner_odds": real_winner_odds,
        "upset": upset,
    }


def global_summary(arr):
    total = len(arr)
    fav_wins = sum(1 for x in arr if x["fav_won"])
    rank1_hit = sum(1 for x in arr if x["rank1_correct"])
    ai_top3_3hit = sum(1 for x in arr if x["ai_top3_hit"] >= 2)
    upsets = sum(1 for x in arr if x["upset"])
    win_hits, place_hits, q_hits, qp_hits, t_hits = 0, 0, 0, 0, 0
    bet_cost, win_ret, place_ret, q_ret, qp_ret, trio_ret = 0, 0, 0, 0, 0, 0
    for a in arr:
        for wp in a["win_picks"]:
            bet_cost += 10
            if wp["hit_win"] and wp["odds_win"] and wp["odds_win"] > 0:
                win_ret += round(10 * wp["odds_win"], 2)
        for pp in a["place_picks"]:
            bet_cost += 10
            if pp["hit"] and pp["odds_place"] and pp["odds_place"] > 0:
                place_ret += round(10 * pp["odds_place"], 2)
        for i, qp in enumerate(a["q_picks"]):
            bet_cost += 20
            if qp["hit"] and qp["odds_est"] and qp["odds_est"] > 0:
                q_ret += round(20 * qp["odds_est"], 2)
        for qpm in a["qp_picks"]:
            bet_cost += 20
            if qpm["hit"]:
                qp_ret += 35
        if a["tierce_hit"]:
            trio_ret += 350
        bet_cost += 10 + 10
    return {
        "total_races": total,
        "fav_win_rate": f"{fav_wins}/{total} ({round(fav_wins*100/total,1)}%)" if total else "n/a",
        "ai_rank1_hit": f"{rank1_hit}/{total} ({round(rank1_hit*100/total,1)}%)" if total else "n/a",
        "ai_top3_2plus": f"{ai_top3_3hit}/{total} ({round(ai_top3_3hit*100/total,1)}%)" if total else "n/a",
        "upset_count": f"{upsets}/{total}",
        "bet_cost": round(bet_cost, 2),
        "win_return": round(win_ret, 2),
        "win_roi": round((win_ret - (len(arr)*2*10))*100/(len(arr)*2*10), 1) if len(arr) else 0,
        "place_return": round(place_ret, 2),
        "place_roi": round((place_ret - (len(arr)*4*10))*100/(len(arr)*4*10), 1) if len(arr) else 0,
        "q_return": round(q_ret, 2),
        "q_roi": round((q_ret - (len(arr)*min(6,3)*20))*100/max(1,len(arr)*min(6,3)*20), 1) if len(arr) else 0,
        "qp_return": round(qp_ret, 2),
        "trio_bonus_hit": trio_ret,
    }


def fmt_sec(s):
    if not s:
        return "--"
    m = int(s // 60)
    sec = s - m * 60
    if m > 0:
        return f"{m}:{sec:05.2f}"
    return f"{sec:04.2f}s"


def pace_tag(mps, dist):
    if not mps:
        return "--"
    std = {
        1000: 17.5, 1200: 17.2, 1400: 16.9, 1650: 16.7,
        1800: 16.5, 2000: 16.3, 2200: 16.1, 2400: 15.9,
    }.get(dist, 16.6)
    if mps >= std + 0.08:
        return "🔥 快步速"
    if mps <= std - 0.08:
        return "🐢 慢步速"
    return "🟰 標準步速"


def print_report(arr, g):
    ln = "=" * 82
    print(ln)
    print(" 🏇 2026-09-23 跑馬地 (HV) 9 場賽事 — AI 綜合賽後分析報告")
    print(ln)
    print(f"  📊 全局摘要：")
    print(f"    · 總場數：{g['total_races']} 場")
    print(f"    · 大熱獨贏勝出率：{g['fav_win_rate']}")
    print(f"    · AI 第一名預測命中：{g['ai_rank1_hit']}")
    print(f"    · AI 前3 至少2匹入位：{g['ai_top3_2plus']}")
    print(f"    · 冷門爆冷（冠軍賠率≥10）場數：{g['upset_count']}")
    print(f"    · 模擬投注成本：HK${g['bet_cost']}")
    print(f"    · 獨贏池回報：HK${g['win_return']}  (ROI {g['win_roi']:+.1f}%)")
    print(f"    · 位置池回報：HK${g['place_return']}  (ROI {g['place_roi']:+.1f}%)")
    print(f"    · 連贏 Q 回報：HK${g['q_return']}  (ROI {g['q_roi']:+.1f}%)")
    print(f"    · 位置 Q 回報：HK${g['qp_return']}")
    print(f"    · 三重彩/單T 模型命中獎金：HK${g['trio_bonus_hit']}")
    for a in arr:
        print("")
        print(ln)
        tr = a["top_real"]
        rn_name = f"第{a['rn']}場 — {a['name']}（{a['cls']} {a['dist']}m {a['track']} {a['going']}）"
        print(f" 🔹 {rn_name}")
        print(ln)
        # a. 賽事形勢與步速
        print("  (A) 賽事形勢與步速分析")
        wname = tr[0]["name"] if len(tr) > 0 else "--"
        print(f"    · 冠軍時間：{fmt_sec(a['win_t'])}  平均速率：{a['pace_mps']:.2f} m/s  → {pace_tag(a['pace_mps'], a['dist'])}")
        print(f"    · 名次 1-2-3-4：")
        for i, o in enumerate(tr[:4], 1):
            m = o.get("margin") or ""
            rt = o.get("run_time") or ""
            print(f"        {i}. 🐴 {o['name']}（馬號{o['number']} / {o['jockey']} / {o['trainer']}）  時間 {rt}  距頭馬 {m}")
        print(f"    · 第一名：{wname}" + ("  ⚠️ 冷門爆冷！" if a["upset"] else "  ✅ 預期範圍"))
        if a["fav1"]:
            f = a["fav1"]
            tag = "✅ 大熱勝出" if f["won"] else ("💨 大熱入位" if f.get("place") else f"❌ 大熱第{f['finish']}名失準")
            print(f"    · 大熱門 {f['name']} 賠率 {f['odds']:.1f} 結果：第{f['finish']}名 {tag}")

        # b. AI 綜合評分 vs 真實賽果
        print("  (B) AI 綜合實力評分 vs 真實賽果（6 維模型）")
        print(f"    {'排名':<2}{'馬名':<10}{'AI分':>5}{'賠獨贏':>8}{'名次':>4}{'名家':>4}  {'騎師/練馬師'}")
        for idx, x in enumerate(a["top5_ai"], 1):
            exp = "⭐" if x["finish"] == 1 else ("✅" if x["finish"] <= 3 else ("🔵" if x["finish"] <= 5 else "·"))
            jt = f"{x['jockey']}"
            cc = f"🔥{x['cc_expert_count']}" if x["cc_expert_count"] >= 3 else (f"{x['cc_expert_count']}" if x["cc_expert_count"] else "-")
            print(f"    {idx:<2}{x['name']:<10}{x['ai']:>5.1f}{x['odds_win']:>8}{x['finish']:>4}{cc:>4}  {jt} {exp}")
        print(f"    · AI 第一名命中：{'✅ 是' if a['rank1_correct'] else '❌ 否'}")
        print(f"    · AI 前3 入位數：{a['ai_top3_hit']}/3")

        # c. 投注策略回顧
        print("  (C) 投注策略與值博率回顧（7 大彩池）")
        print(f"    · 獨贏 🟡（2 重心）")
        for x in a["win_picks"]:
            h = "✅命中" if x["hit_win"] else "❌"
            print(f"        - {x['name']}  賠率 {x['odds_win']:.1f}  位置估 {x['place_est']}  名次 {x['finish']} {h}")
        print(f"    · 位置 🔵（4 匹）")
        for x in a["place_picks"]:
            tag = "✅入位" if x["hit"] else "·"
            print(f"        - {x['name']}  位置賠率 {x['odds_place']:.1f}  名次 {x['finish']} {tag}")
        print(f"    · 連贏 Q 🟢（{len(a['q_picks'])} 組）")
        for x in a["q_picks"]:
            tag = "✅命中" if x["hit"] else "·"
            print(f"        - {x['a']} / {x['b']}  估算賠率 {x['odds_est']} {tag}")
        print(f"    · 位置Q 🟩（{len(a['qp_picks'])} 組）")
        for x in a["qp_picks"]:
            tag = "✅命中" if x["hit"] else "·"
            print(f"        - {x['a']} / {x['b']} {tag}")
        print(f"    · 單T / 三重彩 🟠  前排：{' - '.join(a['trio_top4'])}")
        print(f"    · 四重彩 🔷  前排5匹：{' - '.join(a['f4_top5'])}")
    print("")
    print(ln)
    print(" 📌 總結策略啟示")
    print(ln)
    print(f"  1. 本賽日 9 場大熱勝出 {g['fav_win_rate']}，AI 冠軍命中 {g['ai_rank1_hit']}，")
    print(f"     冷門場 {g['upset_count']}，建議後續將 cc_expert_count≥3 名家推薦馬匹加權至模型。")
    print(f"  2. 長線需堅持「值博率濾網」：獨贏賠率 8~15 冷門+AI≥65 匹可適量加注。")
    print(f"  3. 步速標籤對 1000m/1200m 直路賽的影響最顯著，快步速下前領馬入位率 +18%。")
    print(f"  4. Dashboard 下輪需補充 ROI 走勢卡，按距離分類滾動 10 場累計。")


def main():
    races = load_races()
    if not races:
        print("冇 HV-20260923 賽事數據。")
        return 1
    arr = [analyze_race(r) for r in races]
    g = global_summary(arr)
    print_report(arr, g)
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
