# 賽前賠率快照完整度報表（2026-11-28）

- 資料來源：`pipeline_status`（表未建立時為 `pipeline_status.odds_snapshots` fallback）
- 完整賽事：**0/50**（已追蹤 0 場；四 bucket 齊全才計入）
- 完整定義：open/60m/15m/close 四個 bucket 各至少一行有效賠率（odds > 1、available_at 可解析）；partial 一律不當完整。
- Bucket 邊界（距開跑）：open >60、60m 16–60、15m 6–15、close ≤5 分鐘；bucket_offset_sec = 抓取時間落在名義 window 以外的秒數（平均/最大，open 以 60–180 為目標）。
- 本報表唯讀，不會改動任何預測或預設。

## 結果

目前 **0 場**已收集快照。原因：尚未有 race-day tick 在市前窗口內抓到賠率，或表／fallback 仍未有寫入。下一次賽日 tick 後重跑：

```bash
python scripts/odds_snapshot_report.py
```
