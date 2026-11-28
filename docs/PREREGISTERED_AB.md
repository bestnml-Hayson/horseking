# 預先註冊 A/B 計劃（≥50 場完整 pre-race 快照後執行）

狀態：**已預先註冊，未執行**。本文件在未見真實樣本結果前寫定，不含任何真實數據結論。
基線：**honest_v586**（唯一比較基線）。`current_v586` 只作洩漏幅度參考；`legacy_v576` 只作歷史參考。
生效條件：`complete_pre_race_races = 50`（四 bucket 齊＋odds > 1＋available_at 可解析）。未達前，
時間加權融合、α 時間加權 A/B、drift 特徵一律不准開。

## 0. 共通協定（四項 A/B 全部適用）

- 回測：按日期 walk-forward，5 折 expanding window，嚴禁 random split；任何需要擬合的參數
  （例如 drift 係數）只可在 train fold 內擬合，test fold 只可預測。
- 洩漏防護：騎師／練馬師勝率用 as-of 版本；賽前賠率只用 `source='pre-race'` 且 `available_at`
  在開跑前的行；SP 只可作上限參考，不得當作 pre-race 快照。
- 主指標：**ΔNLL**（variant − honest_v586，越低越好）。採納門檻全部滿足：
  1. `ΔNLL < 0`；
  2. bootstrap 95% CI **全負**（upper < 0），cluster bootstrap 1000 次、seed 42；
  3. ≥4/5 walk-forward fold 改善；
  4. 樣本門檻：整體 ≥50 場；任何分桶結論需該桶 ≥30 場**或** ≥300 runners。
- 分開報告、不作採納依據：Top1、Top1 入 Q、Top3、EV ROI（真實賽前價）、Top1 ROI。
  不得單靠 Top1／Top3／ROI 採納；若 Top1 或 Top3 絕對值轉差 >2pp，需先書面解釋，否則暫緩。
- 分桶：HV/ST、短途（≤1200m）/長途（>1200m）、班次。**50 場只夠整體結論**；
  分桶樣本不足時只報整體，明確寫「不結論」，不得用整體結果代替分桶結論。
- 評估節點：首次在 50 場完整快照；若 CI 未定論，下一次在 75 場、再下一次 100 場。
  不得在中途偷看後改指標、改門檻、改分桶或提前上線。
- 失敗處理：一律維持 flag off／shadow，不改 live 預設；可保留 shadow 繼續累積。
- 每項獨立 commit、獨立報告、可回滾；成功採納才更新 `FLAGS.md`、`RISKS.md`、
  `reports/honest_vs_current_v586.md`。

## 1. α 時間加權（優先次序 1）

**假設**：模型權重 α 應隨賠率資訊時間變化；在真实 pre-race 賠率下，α=0.2（現行）較
α=0（純市場）或 α=0.35 更優，或其中一個 variant 顯著更優。

| 項目 | 內容 |
|---|---|
| 基線 | honest_v586：α=0.2、γ=1.0、T=8、identity 校準 |
| Variants | A0：α=0；A1：α=0.35（不含極端賠率帶）；A2：0.2 vs 0.35 兩段式（<1.8 或 >25 用 0.35，其餘 0.2） |
| 主要指標 | ΔNLL（整體） |
| 次要（分開報告） | Top1、Top1 入 Q、Top3、EV ROI、Top1 ROI |
| 門檻 | ΔNLL < 0、95% CI 全負、≥4/5 fold、整體 ≥50 場 |
| 預期樣本 | 50 場完整快照（整體）；分桶只在 ≥30 場或 ≥300 runners 時報 |
| 失敗處理 | 維持 α=0.2；variant 留 shadow／文檔，不改預設 |
| 注意 | 只在真實 pre-race 賠率上評估；SP 樣本不納入 |

## 2. timing 融合（優先次序 2）

**假設**：距開跑 >2 小時的舊賠率資訊較弱，應用較低市場權重（0.55）；≤2 小時用 0.80；
現行固定 0.80 在早段場次過度依賴舊價。

| 項目 | 內容 |
|---|---|
| 基線 | 固定市場權重 0.80（即 α=0.2） |
| Variant | 時間分段：>2h → 0.55；≤2h → 0.80；無賠率 → 0（P_final=P_model） |
| 主要指標 | ΔNLL（整體） |
| 次要（分開報告） | Top1、Top1 入 Q、Top3、EV ROI、Top1 ROI |
| 門檻 | ΔNLL < 0、95% CI 全負、≥4/5 fold、整體 ≥50 場 |
| 預期樣本 | 50 場中需同時有 >2h 與 ≤2h 的有效快照；若 >2h 子集 <30 場或 <300 runners，只報整體、該子集「不結論」 |
| 失敗處理 | 維持固定 0.80；`timing_fusion` 保持 off |

## 3. odds_drift（優先次序 3）

**假設**：賠率走勢（落飛幅度、rank_delta）在價格水平之外含額外資訊；開賽前明顯收飛
（drift < 0）或排名上升（rank_delta > 0）的馬，實際表現優於市場隱含。

| 項目 | 內容 |
|---|---|
| 特徵定義 | 以 open bucket（>60m）為參考、close bucket（≤5m）為終點：`drift = (open − close) / open`；`rank_delta = rank_open − rank_close`（正 = 收飛）。缺任一 bucket → 該馬 excluded，不填補、不插值 |
| 基線 | honest_v586（無 drift 特徵） |
| Variant | 在 train fold 內以 conditional logit 擬合 drift / rank_delta 係數，test fold 只應用；不得用 test 期資料擬合 |
| 主要指標 | ΔNLL（整體） |
| 次要（分開報告） | Top1、Top1 入 Q、Top3、EV ROI、Top1 ROI |
| 門檻 | ΔNLL < 0、95% CI 全負、≥4/5 fold、整體 ≥50 場；drift 子集需 ≥30 場或 ≥300 runners |
| 預期樣本 | 50 場中每場至少 open＋close 兩個時點；不足則「不結論」，繼續收集 |
| 失敗處理 | `odds_drift` 保持 off；現有 UI 賠率走勢卡只作展示，不入權重 |
| 泄漏注意 | drift 只用開跑前快照；賽後 SP 不得回填成 close |

## 4. availability_gate（優先次序 4）

**假設**：今場有效賠率覆蓋 <80% 時，將市場權重設 0（P_final=P_model）優於按覆蓋賠率融合。

| 項目 | 內容 |
|---|---|
| 基線 | 現行融合（覆蓋賠率 renormalise，市場權重 0.80） |
| Variant | 覆蓋 <80% → 市場權重 0；≥80% 不變 |
| 評分子集 | **0 < coverage < 80%** 的真實場次；coverage=0（完全未開價）屬 identity，live 已等於 P_model，另行記錄但不計入評分 |
| 主要指標 | ΔNLL（子集） |
| 次要（分開報告） | Top1、Top1 入 Q、Top3、EV ROI、Top1 ROI |
| 門檻 | ΔNLL < 0、95% CI 全負、≥4/5 fold、子集 ≥30 場或 ≥300 runners |
| 預期樣本 | 50 場完整快照**不保證**含缺賠率場次；此項樣本獨立累積。沒有足夠 sparse 場次就「不結論」 |
| 失敗處理 | flag 保持 off；只留 shadow 證據 |
| 現狀（2026-11-28） | shadow 11 場 sparse 全部 coverage=0（賠率未開），不可評分 |

## 5. ≥50 場後的執行規則

1. 先跑 baseline（honest_v586）與 shadow 現狀，確認無漂移（ΔNLL ≈ 0、draw_v2 identity ≈ 0）。
2. 按本文件次序逐項做，**一次只開一個 flag**。
3. 每項：獨立 commit、獨立報告、可回滾；報告寫明整體結果與（合格時）分桶結果。
4. 達標才考慮預設；未達標一律留 shadow，不改 live 預設。
5. 50 場只答整體有冇增量；分桶樣本不足時明確寫「不結論」。

## 6. 硬約束（違反即停）

1. 不得為湊 50 場放寬「完整」定義；partial 不計。
2. 不得用 SP 補數當 pre-race 快照。
3. 未夠 50 場不得偷跑時間加權融合、α 時間加權 A/B、drift 特徵。
4. 不得因等待期長而開新 Phase 1 功能（γ 分段、Platt 已診斷不值錢）。
5. 未經 honest 回測，finish_time/margin、going、騎師升級差不得入權重。
6. 50 場後 A/B 不得中途加指標或改門檻。
7. 所有新特徵／flag 必須配置化、可開關、可 A/B、可回滾，保留舊行為基線。
8. 回測一律日期 walk-forward，嚴禁 random split；新特徵附 as-of 測試防 leakage。
9. 回測／訓練離線跑；Vercel 只部署前端／API。

## 7. 判定邏輯驗證

- 共用統計框架：`scripts/stat_eval.py`（bootstrap CI、fold 判定、分桶樣本檢查、variant 評估）。
- 單元測試：`tests/test_stat_eval.py` 驗證判定邏輯（CI 全負、≥4/5 fold、分桶門檻），
  以合成數據測試，**不載入任何真實賽事數據、不產生真實結論**。
- 本文件存在性由 CI 檢查（`.github/workflows/ci.yml`）及 `tests/test_preregistered_ab.py` 驗證。