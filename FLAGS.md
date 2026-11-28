# Flag 註冊表（v5.86，2026-11-28）

> 規則：所有 flag 預設 `enabled=false`；開啟任何 flag 必須以 **honest_v586** 為基線，通過
> 「ΔNLL < 0、bootstrap 95% CI 全負、≥4/5 walk-forward fold 改善、相關分桶 ≥30 場或 ≥300 runners」。
> SP 賠率只可作上限參考，**不得**作為開 flag 或改預設的依據。

## 已凍結診斷（不是 flag，凍結期內不得改）

| 項目 | 凍結值 | 決定 | Commit |
|---|---|---|---|
| 市場去水 γ | 1.0 | 凍結；SP 循環性未解 | `ee60004` |
| segmented γ | off | 只留 `exp_segmented_gamma`，無 A/B | `ee60004` |
| Platt 校準 | off（identity） | 只留 `exp_platt`，無 A/B | `ee60004` |
| 融合 α | 0.2；極端賠率（<1.8 或 >25）0.35 | 維持；待 ≥50 場真賽前賠率才做時間加權 A/B | `ee60004` |
| ROI 標籤 | `SP upper bound` | 所有含 SP 的回測必須標明 | `ee60004` |

## Flags

| Flag | 預設 | 作用 | 達標條件／現狀 | 接線位置 | Commit | 回滾 |
|---|---|---|---|---|---|---|
| `availability_gate` | off（min_coverage 0.8, sparse_market_weight 0.0） | 有效賠率覆蓋 <80% → 市場權重 0（P_final=P_model） | shadow only；歷史 SP 覆蓋≈100% 無變異，要等真實缺賠率場次 | `scripts/shadow_predictions.py`、`pipeline_status.shadow_predictions` | `f038762` | 刪 flag／刪 shadow key，live 不受影響 |
| `avail_aware` | off（min_coverage 0.8） | 缺值因子權重剔除後 renormalise | 隔離後 **+0.00283**（CI −0.00211~+0.00933、3/5）→ **不採納**；只累積證據，不再開 combined／stack 新變體 | 同上 | `6aa6cdc`、`f038762` | 同上 |
| `draw_v2` | off | draw v2 shadow | **本來已係 live 預設**；shadow 只作身份檢查（預期 Δ≈0），**不算新改善** | 同上 | `f038762` | 同上 |
| `timing_fusion` | off | 依賠率可得性／時間調整市場權重（>2h 0.55、≤2h 0.80、無賠率 0） | 需 ≥50 場完整 pre-race 快照才回測 | `config/model_profiles.json` | `ee60004` | flag off |
| `extreme_favourite_guard` | off（threshold 1.6, max_model_weight 0.5） | 大熱（<1.6）限制模型權重 | OOS 只有 3 場，樣本不足 | 同上 | `ee60004` | flag off |
| `dual_probability` | off | 同時輸出 main / value 機率 | 未評估，無 A/B | 同上 | `ee60004` | flag off |
| `st1000_draw_reversal` | off（draw_k −0.2） | ST 1000m 檔位反轉 | OOS 只有 5 場，維持預設 0 | 同上 | `ee60004` | flag off |
| `speed_engine` | off（display_only） | best_time 速度評分展示 | 混入 P_model 量得 +0.011~+0.032 NLL，只可展示 | 同上 | `ee60004` | flag off |
| `finish_time_margin` | off（display_only） | 完成時間／勝距展示 | 覆蓋率不足，只可展示 | 同上 | `ee60004` | flag off |
| `segmented_gamma` | off | 按賠率分段擬合 γ | 多數 fold 選 1.0，OOS 無改善；凍結診斷 | `scripts/model_config.py` 已讀取 | `ee60004` | flag off |
| `platt` | off（window 150–300） | rolling Platt 校準 | NLL 改善 <0.01，未部署 | 同上 | `ee60004` | flag off |

## 與快照收集相關的開關（非模型 flag）

| 項目 | 設定 | 說明 | Commit |
|---|---|---|---|
| `odds_snapshots` 收集 | 每個 tick 寫入，`source='pre-race'` | 表未建立時寫 `pipeline_status.odds_snapshots`，保留 120 日 | `80cc424`、`2bf3460` |
| 完整場次門檻 | `complete_pre_race_races = X/50` | 四個 bucket（open/60m/15m/close）齊＋odds > 1＋available_at 可解析才計；進度寫 `pipeline_status.odds_snapshot_progress` | `2bf3460` |
| 每日進度 log | tick＋每日 cleanup | `[Snapshot] complete_pre_race_races = X/50 ...`；格式見 `docs/MONITORING.md` | — |
| 每日完整度報表 | 每日 05:00 HKT（daily cleanup） | `reports/odds_snapshot_completeness_<date>.md`；摘要寫 `pipeline_status.odds_snapshot_report` | — |
| 每週完整度週報 | `odds_snapshot_report.py --weekly` | 缺 bucket 頻率、`bucket_offset_sec`、HV/ST 差異；長期缺 → 放寬定義（需記錄）或修 scraper | — |
| 每月數據審計 | `monthly_data_audit.py` | fallback raw/gzip 體積、shadow sparse 次數、3 個月 escalation 時鐘 | — |
| 報表欄位（凍結） | 9 欄 | `race_id, race_date, venue, n_runners, n_horses_with_4_buckets, odds_nonnull_rate, available_at_complete_rate, bucket_offset_sec, missing_reason` | — |
| 時間加權融合 | 未開啟 | ≥50 場完整快照後才討論 | — |