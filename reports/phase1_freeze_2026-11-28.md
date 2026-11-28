# Phase 1 凍結報告（2026-11-28）

## 結論

- Phase 1 診斷全部**凍結**：唔會因為 SP 循環回測而改任何預設。
- 唯一未來比較基線 = **honest_v586**；current_v586 只做 leakage 參照；legacy_v576 只做歷史參照。
- segmented γ、Platt 只保留 flag（`exp_segmented_gamma` / `exp_platt`），default off、唔排 A/B。
- α 維持 0.2（極端賠率 0.35），並註明「SP 循環假象，待真實賽前賠率 ≥50 場才做時間加權 A/B」。
- 所有 ROI 數字一律標示「**SP 上限**」。
- P1（availability gate shadow＋draw_v2／avail_aware shadow）與 P2（`odds_snapshots` forward 收集）全部 default off，陰影輸出唔改 live P_final。

## 基線凍結

| 角色 | Profile | 用途 | 依據 |
|---|---|---|---|
| **唯一未來基線** | `honest_v586` | 之後所有 Phase 1/2/3 改動都對佢做 paired 比較 | `reports/backtest_honest_2026-11-28.md` / `.json` |
| Leakage 參照（只讀） | `current_v586` | 量化 leakage 幅度，不作決策依據 | 同上 |
| 歷史參照（只讀） | `legacy_v576` | v5.76 行為回溯 | 同上 |

凍結基準數字（423 場 OOS，2026-05-06 → 11-25，全部 ROI 為 SP 上限）：

| Variant | NLL | Top1 | Top3 | ROI(EV) | ECE |
|---|---|---|---|---|---|
| honest_v586（基線） | 2.09871 | 27.9% | 57.2% | −9.5% | 0.0076 |
| current_v586（leakage 參照） | 2.09304 | 27.9% | 59.3% | −0.3% | 0.0102 |

- honest 相對 current：ΔNLL +0.00567（CI 0.00043–0.01086）、Top3 −2.1pp、ROI(EV) −9.2pp——呢個差距就係 leakage 嘅代價，之後任何「改善」都要以 honest 為起點計。
- 只有 9 / 1057 場有真實賽前賠率，其餘為 SP 複製；**α / ROI 類結論一律視為 SP 上限，不可作為上線依據**。

## Phase 1 凍結決策

| 項目 | 決策 | 證據 | Flag 狀態 |
|---|---|---|---|
| 市場指數 γ | **凍結 1.0** | SP NLL：γ=1.0 2.09072；1.1 2.09331；1.2 2.10203；1.3 2.11637。逐折選 [1.1,1.1,1.0,1.1,1.1] 只換來 2.09478（SP，<0.005） | 無 flag，常數凍結 |
| 分段 γ（按賠率區間） | **只留 flag，唔排 A/B** | 分段 NLL 2.09267 vs 固定 2.09072，無實質改善；SP 循環 | `exp_segmented_gamma`，off，no A/B |
| Platt 校準 | **只留 flag，唔排 A/B** | raw 2.29699 → Platt 2.29092（<0.01），temperature 2.29385；改善幅度不足以排 A/B | `exp_platt`，off，no A/B |
| 融合 α | **維持 0.2；極端賠率 0.35** | 逐折選 α=0.0，只因為 P_market 同 SP 同源（循環）；α=0（2.09072）vs α=0.2（2.09871）唔可以用嚟砍模型權重 | 無 flag，常數凍結＋註解 |
| ROI 標籤 | **一律「SP 上限」** | 9 場真實賽前賠率不足以支撐 ROI 推論 | 報告/輸出層標示 |

`config/model_profiles.json` 新增 `frozen_diagnostics` 區塊，將以上決策、as-of 日期（2026-11-28）同基線報告路徑寫入設定，Python/TS 共用。

## Flag 清單（現時全部 `enabled=false`）

| Experiment | 參數 | 用途 | 狀態 |
|---|---|---|---|
| `segmented_gamma` | 賠率分段 γ | Phase 1 凍結診斷 | off，不排 A/B |
| `platt` | window 150–300 | Phase 1 凍結診斷 | off，不排 A/B |
| `avail_aware` | min_coverage 0.8 | Phase 2：缺值因子權重剔除後 renormalise；隔離回測未通過（見下節） | off，shadow（P1） |
| `availability_gate` | min_coverage 0.8、sparse_market_weight 0.0 | Phase 1：有效賠率覆蓋 <80% → 市場權重 0（P_final=P_model） | off，shadow（P1） |
| `draw_v2` | — | Phase 2：draw v2 已上線（factors.draw_k + features.draw_field_size），shadow 係身份檢查 | off，shadow（P1） |
| `timing_fusion` | no-odds wm=0、min_coverage 0.8、far/near wm | 時間加權融合（今次**唔開**，等真實 pre-race 賠率） | off，等 ≥50 場 |
| `extreme_favourite_guard` | 1.6 / cap 0.5 | 極端熱門保護 | off |
| `dual_probability` | — | 主/值博雙概率 | off |
| `st1000_draw_reversal` | −0.2 | ST 1000m 檔位反轉（僅 5 場） | off |
| `speed_engine` | display_only | 速度引擎 | off，僅展示 |
| `finish_time_margin` | display_only | 完成時間/勝距（覆蓋 0%） | off，僅展示 |

P1/P2 新增 flag（同為 default off，獨立 commit 落地）：

- `availability_gate`：今場有效賠率覆蓋 <80% → 市場權重 = 0（P_final=P_model）；shadow 只記錄，不動 live。
- `draw_v2`：現行 draw_v2 已是 live 預設，Phase 2 的 shadow 係一致性檢查（預期 Δ≈0），會如實記錄。
- `avail_aware`：由 `availability_renorm` 改名，shadow 記錄；隔離回測未通過，只作前瞻量度。

## Phase 2 隔離修正（2026-11-28）

Commit B 原本的 `avail_aware` 列（ΔNLL −0.03449）係「deployed 因子＋renorm」對「pre2 因子」，基線唔對等，數字混入咗已上線的 form shrinkage／rating blend／draw v2 增益。已修正為同一因子集上只切換 renormalisation，並重跑 honest 報告：

| 比較 | ΔNLL | 95% CI | 改善折 | 結論 |
|---|---|---|---|---|
| `avail_aware`（pre2 基線，隔離） | +0.00283 | −0.00211 ~ +0.00933 | 3/5 | **未通過**，唔當已驗證 |
| `avail_aware_on_combined`（deployed 基線，隔離） | +0.00168 | −0.00278 ~ +0.00774 | 2/5 | **未通過** |
| `avail_aware_stack`（舊比較，只作審計） | −0.03449 | −0.07075 ~ −0.00381 | 5/5 | 混入已上線增益，不可引用 |
| `draw_v2` | −0.01916 | −0.02812 ~ −0.01014 | 5/5 | **通過**——但 draw_v2 **本來已係 live 預設**，本次 shadow 只作身份檢查（預期 Δ≈0），**不算新改善** |

因此 Phase 2 只有 `draw_v2` 達採納門檻，而佢唔係新改善；`avail_aware` 隔離後 +0.0028（CI 含 0、3/5 fold）**不採納**，維持 default off 的 shadow flag，只作未來真實賽前賠率場次的證據累積，**不會再開 combined／stack 等新變體**（該兩個只存在於回測審計輸出，不設 flag）。

## Shadow 輸出格式（P1 實作規格，凍結）

由 tick 的賠率注入步驟自動寫入（`auto_pilot.inject_missing_odds`），亦可手動執行 `python scripts/shadow_predictions.py --date YYYY-MM-DD --venue ST`。寫入 `pipeline_status`（id=`shadow_predictions`）嘅 JSON，每場一筆、每 tick 覆寫最新版本，保留 7 日：

```json
{
  "race_no": 1,
  "race_date": "2026-12-02",
  "generated_at": "2026-12-02T18:05:00+08:00",
  "profile": "current_v586",
  "meta": {"runners": 14, "covered": 14, "total": 14, "odds_coverage": 1.0},
  "flags": {"availability_gate": false, "draw_v2": false, "avail_aware": false},
  "live": {"<runner_id>": {"p_model": 0.1123, "p_final": 0.1234}},
  "shadow": {
    "availability_gate": {
      "meta": {"gate": "covered", "coverage": 1.0, "min_coverage": 0.8, "market_weight": null},
      "runners": {"<runner_id>": {"p_final": 0.1234}}
    },
    "draw_v2": {
      "meta": {"status": "already_live"},
      "runners": {"<runner_id>": {"p_final": 0.1234}}
    },
    "avail_aware": {
      "meta": {"gate": "always", "min_coverage": 0.8},
      "runners": {"<runner_id>": {"p_final": 0.1250, "used_weight": 0.8333, "missing": ["pace"]}}
    }
  }
}
```

規則：

- shadow 只寫 `pipeline_status`，**唔會**寫入 `model_predictions.final_prob`，live P_final 不變。
- 前端/投注引擎唔讀 shadow key；回滾 = 刪 flag 或刪 key，即時生效。
- 歷史賽事 SP 覆蓋 ≈100%，所以 availability gate 嘅 shadow 變異數接近 0；真正評估要等未來出現缺賠率／賽前快照嘅場次。
- `draw_v2` shadow 同 live 完全相同（已上線），屬身份檢查；`avail_aware` 一律套用重正規化（同回測變體一致），`min_coverage` 只記錄、暫不設門檻。

## odds_snapshots 遷移（P2 規格，凍結）

目標 schema（forward 收集，**唔回填**歷史 SP 當賽前）：

| 欄位 | 型別 | 說明 |
|---|---|---|
| `id` | BIGSERIAL PK | |
| `race_id` | TEXT NOT NULL | 對應 races.race_id |
| `horse_id` | TEXT NOT NULL | 馬匹識別（runner 對應） |
| `odds` | NUMERIC(7,2) NOT NULL | 該時點勝出賠率 |
| `available_at` | TIMESTAMPTZ NOT NULL | 該賠率實際可得時間（pre-race 使用嘅唯一憑證） |
| `source` | TEXT CHECK ('pre-race','SP') | 賽前抓取 vs 賽後 SP |
| `snapshot_type` | TEXT CHECK ('open','60m','15m','close') | 距開跑時點分類 |
| `captured_at` | TIMESTAMPTZ DEFAULT now() | 寫入時間 |

- 索引：`UNIQUE (race_id, horse_id, snapshot_type, available_at)`（每個實際抓取時刻一列，只去掉完全相同時間的重複）＋`(race_id, available_at DESC)`；RLS 只讀 policy。
- Bucket 邊界（距開跑分鐘）：`>60` → `open`、`16–60` → `60m`、`6–15` → `15m`、`≤5` → `close`。同一 bucket 可有多個時點，完整度以「四個 bucket 都最少有一口價」計。
- 使用規則：`available_at IS NULL` 或 `source='SP'` 嘅行只可用於賽後評估，**永不**進入 pre-race fusion backtest；writer 只寫 `source='pre-race'`，SP 永不經此路徑。
- 觸發條件：累積 ≥50 場「完整快照」賽事（open/60m/15m/close 齊全）後，才討論時間加權融合、α 時間加權 A/B、drift 特徵。進度行 `complete_pre_race_races = X/50` 由 tick 及每日 `daily_cleanup.py`／`python scripts/odds_snapshots.py` 輸出，並寫入 `pipeline_status.id='odds_snapshot_progress'`。
- 由今日（2026-11-28）起 forward 收集。**DDL 狀態（2026-11-28）**：`db.<ref>.supabase.co` 由本機 DNS 完全解析失敗（A/AAAA 皆無）、env 無 `SUPABASE_DB_URL`／`DATABASE_URL`，而 service_role key 係 JWT 唔係 DB 密碼；DB 亦冇 `exec_sql`／`run_sql` RPC，`apply_migrations.py` 套用失敗。表未建立前 writer 自動退回 `pipeline_status.id='odds_snapshots'`（同形狀：`races.<race_id>.rows.<horse_id|type|available_at>`），**保留 120 日**，每 tick 並更新 `buckets` 索引供完整度計算；pipeline 不中斷。migration 檔已備好，日後有可連 DB 憑證時直接套用，再將 fallback 資料轉寫入表。

## 風險

1. **SP 循環性**：9 場真實賽前賠率，任何 α/ROI/γ 結論都只係 SP 上限；凍結期間唔可以引用 SP 回測去改預設。
2. **Shadow 無變異**：歷史 SP 覆蓋接近 100%，availability gate 嘅 shadow 喺歷史數據上睇唔出分別；必須等真實缺賠率場次。
3. **draw_v2 已上線**：佢嘅 shadow 係事後一致性檢查（預期 Δ≈0），唔係新改善；報告會照實寫，避免誤導。
4. **遷移暫時套用唔到**：本環境 DNS 完全解析不到 DB host、無 DB 連線字串／密碼、亦無 SQL RPC；`odds_snapshots` 表未建立，資料暫存喺 `pipeline_status`（同形狀、120 日保留）。快照只可經 script 讀取，不能 SQL join；≥50 場門檻按實際四-bucket 完整度計算。fallback JSON 會隨場次增長（120 日估算 ≈數萬行），每次寫入係 read-modify-write，延遲會升，屬已知代價。
5. **每個 item 獨立 commit、default off**：任何一步都可以單獨 revert，唔影響 live 預設。

## 回滾

- P0：revert 本 commit（只改 config/metadata 命名＋報告），預設常數冇變。
- P1：將三個 shadow flag 保持 `enabled=false` 或 revert commit；shadow key 冇 consumer。
- P2：表係新增，唔影響現有讀取路徑；writer 有 `pipeline_status.odds_snapshots` fallback。回滾 = 移除兩個 hook 呼叫或 revert commit；已收集快照可按 race_id 刪除。