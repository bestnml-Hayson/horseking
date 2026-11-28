# Phase 0 審計報告 — 2026-11-28

**範圍**：現有 codebase、Supabase schema、特徵覆蓋、回測流程、leakage 風險、baseline 指標。
**方法**：只讀查詢（`scripts/phase0_audit.py`，原始輸出 `reports/phase0_audit_2026-11-28.json`）＋現有 WF 報告 `reports/backtest_phase12_2026-11-28.md` 覆核。本輪未改任何模型預設或 DB schema。

---

## 0. 結論摘要

1. **規格書寫的 baseline 已過時。** 規格以 γ=1.3、20/80 為現行系統；實際 production 自 v5.86（commit `1e1233b`）起是 **γ=1.0、α=0.2（賠率 <1.8 或 >25 時 0.35）、T=8 identity（校準檢驗後未部署）**。Phase 0 同時保留 `legacy_v576`（γ1.3）作對照，但所有新實驗的 baseline 應以 **current_v586** 為準。
2. **市場是主要信號。** 138 場 OOS：純熱門 Top-1 25.4%、最高負磅 18.1%、P_model 14.5%、P_final 26.1%。9 因子模型單獨仍跑輸「買熱門」與「買最高負磅」，P_final 只比純熱門高 0.7pp。任何新特徵／校準的合理期望是「小幅改善排序或機率質素」，不是大幅提升命中率。
3. **數據覆蓋要分三層看。** 今日卡（2026-11-29）覆蓋良好：official_rating 100%、best_time 67.4%、form 89.4%、gear 81.6%；近 130 場（10-11→11-25）大致符合規格數字（best_time 59.5%、sectional 78.3%、form 73.1%、rating 79.1%）；但全庫 347 場（6-03→11-25）明顯較低（rating 40.3%、best_time 30.9%、sectional 29.4%、form 44.2%、gear 34.4%）。**回測不可只用全庫數字，也不可把近 130 場的覆蓋當成全市場。**
4. **賠率歷史不具備「賽前價」資格。** 346 場可比較賽事中 **337 場的 `race_runners.win_odds` 是 SP 複製**，只有 HV-20261007 一個賽馬日（9 場）有真實賽前價；`pipeline_status.odds_drift` 目前 0 場、0 點，時間戳歷史不存在。**Phase 1 的「開賽前 >2h / ≤2h」動態融合無法用歷史回測驗證，只能先實作 + 收集，≥50 場後才可啟用。**
5. **現有 v5.86 的部分增益有 leakage 疑慮。** jockey/trainer 勝率在每次 scrape 時以「全庫所有已完成賽事」重算（`auto_scraper.py:109-141`、`backfill_history.py:446-483`），歷史補抓的場次會帶入之後的賽果；`weights_active.json` 以 2026-07-01→11-25 的 274 場擬合，與 OOS 測試段 2026-10-07→11-25 重疊。**Phase 1a 必須用「每折只用訓練段」＋「按賽日截止的 jockey/trainer 率」重跑 baseline，才可作日後比較基準。**
6. **多項規格功能因樣本／變異不足，只能做 flag，不能改預設：** going（近 139 場 99 場好地、40 場空，無變異）、沙田 1000m 檔位反轉（OOS 僅 5 場）、極端大熱 <1.6 護欄（OOS 僅 3 場）、finish_time／margin（近 130 場 0%）。這些保留 experimental flag 並在 UI 標示，不寫死規則。
7. **工程底座缺口：** 無 feature flag／profile 機制、無自動化測試（package.json 只有 dev/build/start/lint）、Python 與 TS 常數各自硬編碼、`market_calibrator.py` / `model_calibrator.py` / `speed_engine.py` / `pace_simulator.py` / `odds_tracker.py` / `backtest_engine.py` 全部不存在；`odds_snapshots`、`model_weights`、`race_reviews` 三個 table 未建立；復盤寫入 `ai_performance`，只有文字＋少數 JSON，無 log_loss/Brier/error attribution。

---

## 1. Codebase 盤點

| 功能 | 現況 | 位置 |
|---|---|---|
| P_model 9 因子＋softmax | 前端與 Python 各一份 | `lib/race-utils.ts`（`computeClientPredictions`、`computeBenterBreakdown`）、`scripts/ai_review.py` |
| P_market／融合 | γ=1.0、α=0.2、極端 0.35 | `lib/race-utils.ts`、`scripts/model_config.py` |
| 校準 | 只有 temperature power（T=8 identity），無 Platt/isotonic 部署 | 同上 |
| 權重重校 | conditional logit、80/20、±6pp、≥30 場自動 | `scripts/recalibrate_weights.py` |
| 回測 | 5 折 expanding WF、γ grid、校準、α sweep、特徵消融 | `scripts/backtest_models.py` |
| 賠率快照 | tick 寫 `pipeline_status.odds_drift`（3 日保留、24 點） | `scripts/odds_injection.py` |
| 沿途走位 | `race_runners.sectional_times = "N|p1 p2 p3 p4"` | `scripts/run_style.py`、`scripts/backfill_run_styles.py` |
| 復盤 | 寫 `ai_performance`；有 top1/top3/ROI、key_factors JSON | `scripts/ai_review.py`、`app/api/pipeline/ai-review/route.ts` |
| EV／Kelly | EV>0.10 + pFinal≥0.05 出 WIN；Python `is_value_bet` EV>0.15；**正 EV 搜索未限 Top-K** | `lib/betting-engine.ts:7-10,122-207`、`scripts/benter_model.py:633` |
| UI | 9 因子拆解、Δ 排位、待定 indicator、賠率走勢 | `app/components/HorseDetailDrawer.tsx`、`AIRaceAnalysis.tsx`、`RaceTable.tsx` |
| Config | 只有 `weights_active.json` / `pipeline_status.model_weights_active` override；**無 flag/profile** | `scripts/model_config.py`、`lib/race-utils.ts:77-130` |
| 測試 | **無**（無 test script、無 test 目錄） | `package.json` |

---

## 2. 數據覆蓋（實測）

### 2.1 今日卡 2026-11-29（沙田 11 場 / 141 匹）

| 欄位 | 覆蓋 | 備註 |
|---|---|---|
| official_rating | 141/141 (100%) | 可用 |
| form_history（卡面近績） | 126/141 (89.4%) | 可用 |
| gear | 115/141 (81.6%) | 可用 |
| best_time | 95/141 (67.4%) | 可用（僅展示） |
| actual_weight / 檔位 | 100% | 可用 |
| track_course | 11/11 場 | 可用 |
| going | 0/11 場 | 賽前未公佈；歷史亦幾乎無變異 |
| weight_change 欄 | 0% | 賽前正常；改用 history 自算（上仗負磅 95.3%） |
| sectional_times / finish_time / margin / age / career_* / trial/fitness / win_odds | 0% | 未跑／未開賠率，正常；**不可用 placeholder 計數值** |

### 2.2 近 130 場（2026-10-11→11-25，規格數字對應樣本）

| 欄位 | 覆蓋 | 規格書 | 判定 |
|---|---|---|---|
| best_time | 59.5% | 58–67% | 一致 |
| sectional_times | 78.3% | 78% | 一致 |
| form_history（卡面欄） | 73.1% | 72–89% | 一致 |
| gear | 67.7% | 72–89% | 略低 |
| official_rating | 79.1% | 100% | 歷史檔較低；今日卡 100% |
| jockey/trainer_win_rate | 79.2% | 100% | 歷史檔較低；今日卡由 scraper 補 |
| actual_weight | 95.0% | 100% | 接近 |
| finish_time / margin | **0%** | 0% | Phase 2b 完全 blocked |
| win_odds（有效 >1） | 99.9% | — | 但 337/346 場為 SP 複製 |

### 2.3 全庫 347 場（2026-06-03→11-25，4,316 匹；343 場可用）

| 欄位 | 覆蓋 | 用途判定 |
|---|---|---|
| draw / actual_weight | 100% / 98.2% | 可用 |
| jockey/trainer_win_rate | 89.0% | 可用，但有 leakage（見 §4） |
| rest_days | 89.0% | 可用 |
| gear | 34.4% | 可用但稀疏，逐場 gate |
| form_history（卡面欄） | 44.2% | **與 DB 推導歷史不同**：≥1 仗歷史 95.3%、≥3 仗 87.4% |
| official_rating | 40.3% | 稀疏；rating ablation 只覆蓋 110/138 場 |
| best_time | 30.9% | 稀疏；只可作展示 |
| sectional_times | 29.4% | 稀疏；pace 特徵要逐場 gate |
| finish_time / margin | 48.7% / 43.1% | 只存在舊資料；近 130 場 0%，不可依賴 |
| age / career_starts / trial_count / fitness_score | 9.9% / 9.9% / 2.5% / 5.1% | 全空級別，禁止做因子 |
| season_prize | 40.3% | 稀疏，只可作實驗 |
| going | 好地 288/347；慢地 2、快地 2、空 51 | **近乎無變異，不可做因子** |
| track_course | 85.6% | 可用 |

### 2.4 其他結構性發現

- **歷史推導覆蓋其實不差**：13 個月 1,088 場已完成賽事（2025-09-07→2026-11-25）形成 11,593 條樣本馬往績；95.3% 馬匹有 ≥1 仗、87.4% 有 ≥3 仗、76.1% 有同場同程、46.7% 有 ≥3 次同場同程。form 因子應以 DB 歷史為主，不應被卡面 `form_history` 的 44% 誤導。
- **騎師逐場欄位齊全**：歷史每仗的 `jockey` 覆蓋 100% → 「騎師升級差」技術上可行，不是 blocked；只需在 client `HorseRaceRecord` / history fetch 補 `jockey`（現時 client 未取此欄）。
- **class_level 兩套命名混用**：OOS 138 場中「第四班 49、第三班 32、第五班 17、Class 4 13、Class 3 8、第二班 7、Class 5 6、Class 2 1、空 5」。分桶前必須正規化，否則同一班被拆散。
- **檔位資料異常**：347 場有 11 場出現 draw > 實際出馬數（可能包含後備／退出馬）；draw_v2 要 clamp 並記錄。
- **rating 與 classMov 相關性**：OOS 4,000+ runner 樣本 r = **−0.28**（< |0.65|）→ 按規格暫不需要合併評分與升降班，但要保留檢查。
- **`odds_snapshots` / `model_weights` / `race_reviews` 不存在**；migration `migrations/add_run_style_and_market_tables.sql` 與 `scripts/apply_migrations.py` 均未提交、未執行。現時 drift 存 `pipeline_status` JSON（3 日後清空，目前 0 場）。

---

## 3. Baseline 指標（現有 WF，138 場 OOS，2026-10-07→11-25）

| 配置 | NLL | Brier | ECE | Top-1 | Top-3 | ROI (SP 上限) |
|---|---|---|---|---|---|---|
| 純熱門（最低賠率） | — | — | — | 0.254 | — | — |
| 最高負磅 | — | — | — | 0.181 | — | — |
| P_model raw | 2.42774 | 0.07419 | 0.0191 | 0.145 | 0.384 | — |
| P_market γ=1.0 | 2.16494 | 0.06913 | — | 0.254 | — | — |
| legacy_v576（γ1.3、20/80、舊特徵） | 2.19554 | 0.06963 | — | 0.261 | 0.536 | −67.5% |
| **current_v586**（γ1.0、α0.2/極端0.35、新特徵） | **2.16700** | **0.06939** | — | **0.254** | **0.551** | **+3.9%** |

- 校準：temperature NLL 2.42544、Platt 2.42333、isotonic 2.61473；raw ECE 0.0191 已最低 → v5.86 決定不部署校準。
- γ grid 只做過 {1.0,1.1,1.2,1.3,1.4,1.5}；規格要求的 1.05/1.15/1.25 未做。
- 融合 α sweep 0.0–0.5；動態極端 α=0.35 @ (<1.8 或 >25) NLL 2.17097；分段 γ 全 1.0。
- **所有 ROI 都是 SP 上限**：只有 9 場真實賽前價（HV-20261007，101/108 匹與 SP 不同），不可當可下注回報。

---

## 4. Leakage／方法論審計

| # | 風險 | 證據 | 影響 | 處理 |
|---|---|---|---|---|
| L1 | **SP 當賽前價** | 346 場中 337 場 `race_runners.win_odds` = `race_results` SP；drift 0 場 | 融合權重、γ、ROI 全部樂觀；時序融合不可驗證 | 標記 `odds_kind`；ROI 只用 9 場 honest 樣本；Phase 3 建 snapshots |
| L2 | **jockey/trainer 率非日期截止** | `auto_scraper.py:109-141` 每次用全庫已完成賽事重算；`backfill_history.py:446-483` 相同；32 位騎師中僅 5 位只有一個率值，中位 6 個、最多 9 個不同值 | 歷史補抓場次帶入未來賽果；v5.86 權重與特徵增益可能被高估 | 回測改用「該賽日前的累積勝率」；production 保留 racecard/即時率；Phase 1a 重跑 |
| L3 | **權重擬合與測試段重疊** | `weights_active.json` 以 2026-07-01→11-25 274 場擬合；OOS 測試 10-07→11-25 | 特徵消融與 staged 改善有 in-sample 成分 | 每折只用 train 重新擬合或凍結 hand-set 權重；報告分開「fold-fitted」與「deployed」 |
| L4 | **稀疏特徵的覆蓋選擇** | rating 40% 全庫/80% 近 130；best_time 31%/60%；sectional 29%/78% | ablation n=110/138，外部有效性低 | 每個特徵報覆蓋子集＋全市場分層；未達門檻不改預設 |
| L5 | **going 無變異** | 近 139 場 99 好地、40 空；全庫僅 4 場非好地 | 不可做因子；強行做等於常數 | 排除，只留 missing indicator |
| L6 | **極端大熱／沙田 1000m 樣本過細** | OOS：min odds<1.6 僅 3 場；ST 1000m 僅 5 場（全庫 18 場） | 軟護欄、檔位反轉無法驗證 | 只做 flag，預設關閉；樣本門檻未達不啟用 |
| L7 | **finish_time / margin 世代斷層** | 近 130 場 0%；全庫 49%/43% 只存在舊資料 | speed engine 只能靠 best_time；Phase 2b blocked | 不新增爬蟲；等 results parser 補欄後另開 flag |
| L8 | **class_level 命名不一** | 中英文混用、5 場空 | 分桶統計會斷裂 | 正規化 parser + 單元測試 |
| L9 | **history 是否含當場** | `priorStarts` 用 `race_date < 當日`，同日只跑一場 | 暫無 leakage | 加 regression test 鎖定 |
| L10 | **多重比較／桶內樣本** | 138 場 OOS；HV 65 / ST 73；距離/班次/賠率桶更薄 | 容易過擬合，單桶波動大 | 預註冊指標、bootstrap by race day、最低樣本＋收縮 |

---

## 5. 規格逐項 Gap 分析

### Phase 1

| 規格 | 現況 | Gap／決定 |
|---|---|---|
| 1.1 market_calibrator.py；γ grid 1.0–1.3（含 1.05/1.15/1.25）；分段 γ flag | γ grid 已做（欠 1.05/1.15/1.25）；banded 已試（全 1.0）；**無獨立 module** | 抽 module、補 grid、banded 用「分段 γ 同場歸一化」＋WF 擬合；預設暫維持 γ=1.0 |
| 1.2 model_calibrator.py；rolling M=150–300 Platt；≥500 isotonic；場內歸一化；樣本不足 fallback | calibration 已在 backtest 內試 temperature/Platt/isotonic；T=8 identity；**無 module、無 rolling M** | 抽 module；Platt 以每折 train 最近 M 場擬合；預設不啟用，除非 ≥4/5 折改善 |
| 1.3 動態融合：缺賠率/<80% w_m=0；early >2h 0.55；late ≤2h 0.80；需 available_at | 現時 α=0.2 + 極端 0.35；**無時間戳、無 snapshots 歷史** | 先實作 availability rule（可回測）；timing profile 只可 flag + 收集 ≥50 場，未證實不啟用 |
| 1.4 極端大熱 <1.6 軟懲罰（不硬 clip） | 現時無 clip；只有極端 α | 做 flag；OOS 僅 3 場 → 預設關閉 |
| 1.5 主概率＋價值概率雙輸出；正 EV 限模型 Top3/5 | 單一 P_final；EV 搜索全場（`betting-engine.ts`），未限 Top-K | 新增 `p_main` / `p_value` profile flag；value EV 只掃 model Top3/5；預設保持舊輸出直到回測 |

### Phase 2

| 規格 | 現況 | Gap |
|---|---|---|
| A 檔位：實際馬數、比例、HV/ST、場地×途程×馬數分桶、ST1000 反轉 flag | v5.86 已用實際 N＋比例＋HV/ST k 值；未做分桶 WF；ST1000 無 flag（亦無硬編碼） | 加分桶回測；ST1000 flag 預設關閉（OOS 5 場） |
| B 沿途走位：末段名次變化、pace pressure count、三場景、覆蓋 <60% 降權 C_form | 已有跑法分類/預測步速；未抽 late gain/pressure；無場景概率 | 新 `pace_features` flag；覆蓋 gating；不假造段落時間 |
| C 途程變化：今場−上場、增/縮 400m、同程缺失 indicator | 未實作 | 新 flag，先特徵後回測 |
| D 騎練：Beta 收縮 α=30 μ0=.085；條件化；組合另計；騎師升級差 | 現時 raw 率（60/40 混合）；無收縮／條件化；升級差未做（技術可行） | 新 flag；history jockey 100% 可用；client 需補 jockey 欄位 |
| E 近況/負磅/評分：距離場地匹配、DNF 剔除、時間衰減 .35/.25/…；負磅變動/場均差/見習減磅；評分排名/均值/最高/百分位；season_prize 代理；|r|>0.65 合併 | 現有貝氏收縮、rating 混入 class（0.35）、lastWeight delta（展示）；未做距離匹配/衰減/DNF/場均差/season_prize/corr 檢查（實測 classMov vs rating r=−0.28） | 分拆 flag；先做可回測特徵 |
| F speed_engine.py：parse 1.21.30、分層 μ/σ、<4 退回全季、Z→50+15Z、clip、無紀錄不填 0 | 已有 `parseBestTime`、同場同程排名；無獨立 engine、無分層 fallback | 抽 `speed_engine.py`；ablation 顯示入模型變差（+0.011/+0.037 NLL）→ 只展示 |
| 2b finish_time/margin parser flag | 近 130 場 0%；舊資料有但斷層 | blocked；不新增爬蟲，等 results parser 補欄 |

### Phase 3

| 規格 | 現況 | Gap |
|---|---|---|
| backtest_engine.py；Top1/Top1 入 Q/Top3/LogLoss/Brier/ECE/分區間 ROI；baseline vs 實驗；CI/最小樣本 | `backtest_models.py` 已有大部分統計；未做 Top1 入 Q、位置率、CI、通用分桶 | 重構成 engine＋bucket report；加入 bootstrap CI/門檻 |
| pace_simulator.py；覆蓋 <60% 降權、≥60% 三場景合成 | 只有 `predictPace` 單一標籤 | 新 module + flag |
| odds_tracker.py；open/T-60/T-15/臨場、drop%、rank delta；≥50 場 A/B | `pipeline_status.odds_drift` 有 open/last/points；3 日清空；無 table | 新 tracker；先存 JSON/新 table；≥50 場前不啟用 |
| race_reviews JSON：race_id/top1_hit/top3_hit/log_loss/brier/pace_actual_vs_pred/error attribution/calibration_bias/ai_summary | `ai_performance` 只有 top1/top3/ROI＋文字；無 log_loss/Brier | 新 table 或新 JSON 欄位；DDL 未驗證 |

---

## 6. 實施計劃（待確認後執行，每項獨立 commit + flag）

### 6.0 共通底座（Commit A）
- 新增 `config/model_profiles.json`：`legacy_v576`、`current_v586`、`exp_*`；內容含 γ、α、T、weights、feature flags。
- Python `model_config.py` 與 TS `lib/race-utils.ts` 改為讀同一 JSON（Next 直接 import JSON；client 仍可經 `/api/model-config` 取 runtime override）。**預設 profile = current_v586，行為零改變**。
- 加 `scripts/validate_config.py`＋pytest；加 `tests/test_config.py`。
- 加 feature flag schema（boolean/number），所有新功能默認 `false`。

### 6.1 Phase 1a：誠實 baseline（Commit B，不改 production）
- 每折只用 train 段擬合權重（或凍結 hand-set）＋jockey/trainer 率按賽日截止（由 DB history 累積）。
- 把 `odds_kind`（pre-race / SP）帶入樣本；ROI 只報 honest 子集；NLL/Brier 分「SP-optimistic」與「honest」。
- 重跑 γ grid（含 1.05/1.15/1.25）、T/α、特徵消融，出 `reports/phase1a_honest_2026-*.md`。**這是日後所有 A/B 的唯一 baseline。**

### 6.2 Phase 1b：market_calibrator.py（Commit C）
- 全局 γ＋banded γ（熱門 <3.5、中價 3.5–12、冷門 >12；同場歸一化、統一擬合）。
- 只有 ≥4/5 折改善＋bootstrap 95% CI 排除 0，才更新 profile；否則 `exp_market_*` flag。

### 6.3 Phase 1c：model_calibrator.py（Commit D）
- rolling Platt（M=150/200/300）、樣本 ≥500 才試 isotonic；場內歸一化；樣本不足 fallback 並標記。
- 以 NLL + Brier + ECE 三重門檻；ECE 不得變差（現時 raw ECE 0.0191 已很好）。

### 6.4 Phase 1d：dynamic fusion（Commit E）
- `availability rule`：有效賠率 <80% → w_m=0（P_final=P_model），可回測（歷史全數 ≥90%，只有 production Stage 1 受影響）。
- `timing rule`：early >2h w_m=0.55、late ≤2h w_m=0.80；**flag 預設關閉**，開始寫 `odds_snapshots`（或 `pipeline_status` 新 row）附 `available_at`；≥50 場後才 A/B。
- `extreme α` 保留現行；`extreme fav <1.6` 軟懲罰 flag 預設關閉（OOS 3 場）。
- 不動「極端大熱硬 clip」——現時亦無 clip。

### 6.5 Phase 1e：雙概率（Commit F）
- `p_main`（P_final，排序/命中率）＋`p_value`（EV 導向，只在 model Top3/5 內搜正 EV）；`betting-engine` 讀 profile，預設維持單一輸出；UI 只在新 profile 顯示。

### 6.6 Phase 2（每項一 flag/commit，先特徵、後回測、再決定）
- G1 draw buckets（HV/ST × 途程 × 實際馬數；ST1000 反轉 flag 關閉；clamp draw>N）。
- G2 pace features（末段名次變化、pace pressure count、三場景；覆蓋 <60% 時 pace 權重乘 C_form，剩餘按比例分給騎練/市場；不假造）。
- G3 trip change（今場−上場途程、±400m、同程缺 indicator）。
- G4 jockey/trainer Beta（α=30、μ0=.085；場地/途程/班次條件化；組合另計）。
- G5 jockey upgrade diff（client 補 history `jockey`；用今場騎師率 − 近 3 仗平均騎師率）。
- G6 form v2（距離/場地匹配、DNF 剔除、時間衰減 .35/.25/其餘；貝氏收縮保留）。
- G7 weight/rating v2（負磅變動/場均差；評分排名/均值/最高/百分位；season_prize 代理；corr 檢查）。
- G8 speed_engine.py（分層 μ/σ、<4 退回、clip 50+15Z；預期只展示）。
- 每項報告：覆蓋子集 n、整體＋分桶 NLL/Brier/Top1/Top3/位置率/ROI、5 折一致性、CI。

### 6.7 Phase 3（Phase 1/2 穩定後）
- `backtest_engine.py`：Top1 入 Q、位置率、分桶 ROI、bootstrap CI、最小樣本門檻；預註冊指標。
- `pace_simulator.py`：覆蓋 gating＋三場景；未證實前 flag。
- `odds_tracker.py`：open/T-60/T-15/臨場 snapshot、drop%/rank delta；≥50 場 A/B 才可入預設。
- `race_reviews`：結構化 JSON（top1_hit/top3_hit/log_loss/brier/pace_actual_vs_pred/error_attribution/calibration_bias/ai_summary）；table 或 `ai_performance` 新 JSON 欄。DDL 先用 migration 驗證，失敗則 fallback JSON。

### 6.8 發布護欄
- 整體 OOS ≥100 場；場地 ≥40；距離/班次/賠率桶 ≥30 場或 ≥300 runner，否則與相鄰桶共享（hierarchical pooling）。
- 只有 ≥4/5 折改善、bootstrap by race day 95% CI 排除 0、無任何桶 NLL 退步 >0.02，才改預設；否則留 `exp_*`。
- 保留權重 ±6pp＋≥30 場再擬合；refit 必須用日期截止率與 train-only 樣本。
- 每次改動有 pytest（parser/calibrator/WF split/leakage regression）、報告、UI 缺失標記；可一鍵 profile 回滾。

---

## 7. 風險清單（按嚴重度）

| 嚴重度 | 風險 | 緩解 |
|---|---|---|
| 高 | **賠率 SP 污染**：337/346 場非賽前價；只有 9 場 honest | ROI 不作決策；fusion 只用 NLL + honest 子集；Phase 3 收集 snapshots |
| 高 | **jockey/trainer 率 look-ahead** 令 v5.86 增益高估 | Phase 1a 日期截止重算 + fold-fitted 權重重跑，必要時回退特徵 |
| 高 | **權重擬合與測試段重疊** | 每折 train-only 擬合；deployed 表只用於 production，不參與評估 |
| 高 | **時間融合無法回測**（無 available_at 歷史） | flag 關閉；≥50 場有時間戳賽事後 A/B；不合規不啟用 |
| 中高 | 稀疏欄位（rating/best_time/sectional/gear）令 ablation 樣本僅 110–138 場 | 分層覆蓋報告；最小樣本門檻；未達標不改預設 |
| 中高 | 多重比較／桶內樣本太細 | 預註冊指標、CI、FDR；ST1000/極端大熱 flag 關 |
| 中 | going 無變異 | 不做因子，只做 missing indicator |
| 中 | class_level 命名混亂、draw>N 異常 | 正規化＋單元測試；clamp |
| 中 | finish_time/margin 斷層，speed 只能 best_time | Phase 2b blocked；不新增爬蟲 |
| 中 | 無測試、config 雙份 | Commit A 統一 JSON＋pytest；TS 端加 test |
| 低中 | DDL 未驗證（三張 table 不存在） | 先試 migration；失敗 fallback `pipeline_status` JSON |
| 低中 | UI 複雜度上升（新因子/雙概率/flag） | 預設隱藏實驗因子；chip + 待定 indicator；A/B 開關 |
| 低 | 現時 P_model Top1 低於最高負磅／熱門 | 明確定位：market anchor 為主、model 為 tilt；不以 Top1 單指標發布 |

---

## 8. 需要你確認的 4 件事

1. **Baseline 認定**：Phase 0 以 `current_v586`（γ1.0）為 production baseline，同時保留 `legacy_v576`（γ1.3）作歷史對照——是否同意？
2. **樣本策略**：Phase 1（市場/校準）用全庫 1,088 場做 WF；Phase 2 稀疏特徵用 347 場／138 場 OOS 子集並報覆蓋——是否同意？
3. **DDL**：`odds_snapshots`／`race_reviews` 先用 migration 建 table，失敗則 fallback `pipeline_status` JSON；是否同意先試？（另一選擇：完全不 DDL，只用 JSON。）
4. **測試依賴**：允許加入 pytest（Python）＋ vitest/tsx（TS）作測試腳本；是否同意？

確認後我由 Commit A（config/profile + 零行為改動）與 Commit B（honest baseline 重跑）開始，逐項 flag 上；未達 OOS 門檻的功能不會改預設。