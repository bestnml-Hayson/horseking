# 數據收集監控手冊（等待期，Line 1）

適用：v5.86 數據收集等待期。此文件只描述監控與報表，不改變任何模型 flag 或 live 預設。
門檻：**≥50 場完整 pre-race 快照**（open/60m/15m/close 四 bucket 齊、odds > 1、available_at 可解析）。
未達門檻前：時間加權融合、α 時間加權 A/B、drift 特徵一律不准開。

## 1. 每日 log（自動）

觸發：每個 race-day tick（`scripts/auto_pilot.py`）與每日 05:00 HKT cleanup
（`.github/workflows/daily_cleanup.yml` → `scripts/daily_cleanup.py`）。

指令（手動重跑）：

```bash
python scripts/odds_snapshots.py
```

輸出格式：

```text
[Snapshot] complete_pre_race_races = X/50 | partial=Y | missing={缺 close: n, ...} | store=pipeline_status | fallback=NN.N KB
```

| 欄位 | 意思 | 持久化位置 |
|---|---|---|
| `complete_pre_race_races` | 四 bucket 齊全且每行 odds > 1、available_at 可解析的賽事數 | `pipeline_status.id='odds_snapshot_progress'` |
| `partial_races` | 有快照但未達完整定義的賽事數（不計入 50） | 同上 |
| `missing` | 缺失 bucket 分佈（例如 `缺 close`） | 同上 |
| `store` | `table`（DB）或 `pipeline_status`（fallback） | 同上 |
| `fallback=NN.N KB` | fallback JSON 大小；DB 模式顯示 `n/a` | 同上 |

每日另會自動產生完整度報表（見下）並寫入 `pipeline_status.id='odds_snapshot_report'`。

## 2. 每週快照完整性週報（自動／手動）

```bash
python scripts/odds_snapshot_report.py --weekly --days 7
```

輸出：`reports/odds_snapshot_weekly_<YYYY-MM-DD>.md`；
摘要寫入 `pipeline_status.id='odds_snapshot_weekly_report'`。

模板內容：

| 區塊 | 內容 | 判定 |
|---|---|---|
| 缺 bucket 頻率 | 每個 bucket 在視窗內缺場數／缺場率 | 某 bucket ≥80% 場缺失 → 標「長期缺」 |
| 場地差異 | HV vs ST：完整率、四 bucket 齊馬數、賠率有效率、available_at、offset | 兩場地分開報，不合并結論 |
| `bucket_offset_sec` | 平均／最大偏移秒數、非零偏移賽事數 | 長期非零 → 先查 tick 時鐘 |
| 建議 | 自動列出「長期缺」bucket | 二選一：**放寬 bucket 定義（必須在 FLAGS.md 記錄並保留對照）** 或 **修 scraper**；partial 一律不當完整 |

每日版（同樣欄位，逐場）：

```bash
python scripts/odds_snapshot_report.py
```

產出 `reports/odds_snapshot_completeness_<YYYY-MM-DD>.md`，每場固定欄位：

`race_id | race_date | venue | n_runners | n_horses_with_4_buckets | odds_nonnull_rate | available_at_complete_rate | bucket_offset_sec | missing_reason`

## 3. 每月數據審計（手動／月度例行）

```bash
python scripts/monthly_data_audit.py
```

輸出：`reports/monthly_data_audit_<YYYY-MM>.md`（唯讀，不寫預測）。

檢查清單：

1. **收集進度**：`complete_pre_race_races = X/50`、partial、missing_reason 分佈、store、DB 表是否可用。
2. **Fallback 體積**：raw 與 gzip 大小；≥512 KB 安排壓縮／歸檔，≥2 MB 立即 gzip 歸檔並只保留 index。
3. **availability_gate shadow**：
   - 記錄 sparse / covered 場數；
   - 若 sparse 全部 coverage=0（賠率未開），標明「未開價場次，未可評分」；
   - 若歷史 SP 覆蓋仍≈100%，標明「shadow 無變異，等真實缺賠率場次」；
   - draw_v2 identity 最大差異應為 0（draw_v2 本身已是 live 預設，shadow 只作身份檢查）。
4. **Escalation**：收集開始 2026-11-28；滿 3 個月仍無 DB 表 → 提出 (a) staging IPv4 環境收集＋定期 sync，或 (b) 第三方 storage 寫快照、`pipeline_status` 只存 index。
5. 用報表第 5 節的 R2–R5 更新行同步 `RISKS.md`。

## 4. 不變硬約束

- 完整定義不得為湊數而放寬；partial 不計入 50。
- SP 不得補數當 pre-race 快照。
- 未滿 50 場：不開時間加權融合、α 時間加權 A/B、drift 特徵。
- 任何 flag 改動必須同一 commit 更新 `FLAGS.md`、`RISKS.md`、`reports/honest_vs_current_v586.md`（如涉及）。
- 回測一律日期 walk-forward、as-of、離線；Vercel 只部署前端／API。