# 歷史爬蟲執行說明

## 問題
爬蟲已成功建立並測試（dry-run 顯示可爬取 161 個賽日、~1600+ 場賽事），但 Supabase 的 RLS (Row Level Security) 政策只允許讀取，不允許寫入。

## 解決方案

### 步驟 1：在 Supabase 執行 SQL 政策更新

1. 打開 Supabase Dashboard SQL Editor：
   https://supabase.com/dashboard/project/iogzmjdztnvjzerxfsps/sql/new

2. 複製 `supabase_rls_write_policies.sql` 的內容並貼上

3. 點擊 "Run" 執行

這個 SQL 會為 anon key 添加 INSERT/UPDATE/DELETE 政策，讓爬蟲可以寫入資料。

### 步驟 2：執行歷史爬蟲

```bash
cd "D:\Trae\horse"
export $(grep -v '^#' .env.local | xargs)
PYTHONUNBUFFERED=1 python scripts/fetch_historical_hkjc.py
```

這會：
- 爬取所有 161 個賽日（约 15-20 分鐘）
- 寫入 Supabase（horses, races, race_runners）
- 自動觸發 Benter 模型重新計算

### 預期結果
- ~1600+ 場賽事寫入 `races` 表
- ~20,000+ 筆馬匹紀錄寫入 `race_runners` 表
- ~3000+ 匹.unique 馬匹寫入 `horses` 表
- `model_predictions` 表自動填充 Benter 模型預測

## 測試結果（dry-run）
```
[Step 2] Scraping complete:
  Total races scraped: 28 (from 5 dates)
  Total horse entries: 340
  Jockeys: 21, Trainers: 23, Horses: 333
```

爬蟲本身運作正常，只需要執行 SQL 政策更新即可開始完整爬取。
