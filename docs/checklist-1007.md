# 10/7 Happy Valley 賽日手動 Checklist

> R1 開跑: 18:35 | 9 場賽事 | 場地: HV

---

## 賽前 (已完成 ✅)

- [x] 賽事資料爬取 (`auto_scraper.py --date 2026-10-07`)
- [x] Benter P_model 計算 (`benter_model.py --mode supabase`)
- [x] 賽事時間修正 (ACTUAL_RACE_TIMES 已加入 10/7)

---

## 賽前 — 賠率注入 (開跑前 1~2 小時，約 16:30~17:30)

```powershell
# Step 1: 爬最新獨贏賠率
python scripts/auto_scraper.py --date 2026-10-07 --odds-only

# Step 2: Odds Injection → 計算 P_final / EV / Kelly
python scripts/odds_injection.py --date 2026-10-07

# Step 3: 重算 Benter (確保 P_model 最新)
python scripts/benter_model.py --mode supabase
```

**驗證:** 前端賠率唔再顯示「待定」，P_final / EV / Kelly 有數值

---

## 開跑前 15 分鐘 — 高頻賠率 (可選，約 18:20)

```powershell
# 每 10 秒 poll 一次賠率，最多跑 20 分鐘
python scripts/live_high_frequency_pacing.py --date 2026-10-07
```

**注意:** 呢個會 lock 住 terminal，跑完先可以做其他嘢

---

## 賽後 — 匯入賽果 (尾場結束後，約 23:00)

```powershell
# Step 4: 匯入全部 9 場賽果
python scripts/post_race_import.py --date 2026-10-07 --all
```

**驗證:** 每場顯示第一名馬號，is_finished = true

---

## 賽後 — AI 復盤 (賽果匯入後)

```powershell
# Step 5: AI Review — 每場生成評語
python scripts/ai_review.py --date 2026-10-07

# Step 6: Performance Analyzer — 分析模型表現
python scripts/post_race_analyzer.py --date 2026-10-07
```

**驗證:** 前端「AI 復盤」tab 有 10/7 數據

---

## 疑難排解

| 問題 | 解決 |
|------|------|
| `auto_scraper --odds-only` 無數據 | HKJC 未開投注，等一陣再試 |
| `odds_injection.py` 報錯 "no odds found" | 先跑 `auto_scraper --odds-only` |
| `post_race_import.py` 搵唔到賽果 | HKJC 未更新賽果，等 5 分鐘再試 |
| Supabase 連接失敗 | 檢查 `.env.local` 入面 SUPABASE_URL 同 SUPABASE_SERVICE_KEY |
| 前端無更新 | Vercel 自動 deploy，等 1-2 分鐘；或手動 `git push` |

---

## 快速一鍵 (複製貼上)

```powershell
# === 賽前 (16:30~17:30) ===
python scripts/auto_scraper.py --date 2026-10-07 --odds-only && python scripts/odds_injection.py --date 2026-10-07 && python scripts/benter_model.py --mode supabase

# === 賽後 (23:00) ===
python scripts/post_race_import.py --date 2026-10-07 --all && python scripts/ai_review.py --date 2026-10-07 && python scripts/post_race_analyzer.py --date 2026-10-07
```
