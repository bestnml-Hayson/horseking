# 風險登記（Risk Register）

最後更新：2026-11-28　適用版本：v5.86（P0 凍結＋P1 shadow＋P2 快照收集）

| ID | 風險 | 等級 | 狀態 | 影響 | 緩解 | 關閉條件 |
|---|---|---|---|---|---|---|
| R1 | **SP 循環性**：1,048/1,057 場的「賽前賠率」其實是 SP 複製；γ、α、ROI 回測均帶循環 | 高 | 開放 | 任何基於 SP 的參數結論都可能反向 | γ 凍結 1.0、α 維持 0.2/0.35、所有 ROI 標 `SP upper bound`；凍結期內不得改預設 | 真實 pre-race 賠率 ≥50 場完整快照並重跑 honest 回測 |
| R2 | **Shadow 無變異**：歷史 SP 覆蓋≈100%，availability gate／avail_aware 在歷史數據上幾乎冇分別 | 中 | 開放 | 無法用歷史證明 shadow 成效 | shadow 只寫 `pipeline_status`，不動 live；等真實缺賠率場次。2026-11-28 實測 11 場 sparse 全部 coverage=0（賠率未開），非近開跑缺賠率；draw_v2 identity 最大差異 0.00000 | 累積 ≥30 場有缺賠率的真實場次並比較 shadow vs live |
| R3 | **DDL 未套用**：本機 DNS 解析不到 DB host、無 `SUPABASE_DB_URL`／DB 密碼、無 SQL RPC，`odds_snapshots` 表未建立 | 中 | 開放 | 快照只存 JSON，不能 SQL join／跨場查詢 | writer 自動 fallback `pipeline_status.odds_snapshots`；migration 檔已備好；`monthly_data_audit.py` 每月檢查表可用性與 3 個月 escalation 時鐘 | 提供可連 DB 憑證並成功套用 `migrations/add_odds_snapshots.sql` |
| R4 | **Fallback 體積與延遲**：120 日、每 tick 每匹馬一列，JSON read-modify-write 隨時間變大 | 中 | 開放 | tick 寫入延遲上升；單行 JSON 過大 | 去重鍵含 available_at（只去完全重複）；完整度用 per-race `buckets` 索引；每日 log 記大小；`monthly_data_audit.py` 門檻：≥512 KB 壓縮／歸檔、≥2 MB 即時 gzip 並只留 index | 表建立並轉寫 fallback 資料後刪 JSON |
| R5 | **真賽前樣本不足**：只有 9 場 < 50 場門檻；完整快照實測 0/50 | 高 | 開放 | 無法驗證時間加權融合、α 時間加權、drift 特徵 | 每 tick forward 收集；每日 log `complete_pre_race_races = X/50`；每日完整度報表＋每週／每月審計（`docs/MONITORING.md`） | X = 50 且合格場次覆蓋 HV/ST |
| R6 | **draw_v2 誤讀**：draw v2 本來已是 live 預設，shadow 只作身份檢查 | 低 | 已標註 | 可能被誤當成新改善 | 報告、flag registry 均明示「不算新改善」 | —（長期保留標註） |
| R7 | **avail_aware 未驗證**：隔離後 +0.0028、CI 含 0、3/5 fold | 中 | 已否決 | 若誤開會令 NLL 變差 | 維持 flag off，只留 shadow 證據；不再開 combined／stack 變體 | 未來真實缺賠率樣本重測並達標 |
| R8 | **CI 未經實跑**：新增 `.github/workflows/ci.yml` 只在 push 後才首次執行 | 低 | 開放 | 首次 push 可能因環境差異失敗 | 本地已跑同一組 pytest／tsx／validate；CI 失敗不影響 runtime | 首次 push 後 CI 綠燈 |
| R9 | **前端 profile 切換風險**：`NEXT_PUBLIC_MODEL_PROFILE` 可改前端行為 | 低 | 監控 | 若誤設 exp profile 會出 shadow 邏輯 | 預設 `current_v586`；exp profile 只存在於 config，未部署 | 保持預設直至 honest A/B 達標 |
| R10 | **歷史賽果欄位不齊**：`finish_time` 2026-10/11 為 0%，`margin` 2025-09～2026-03 為 0%；班次命名新舊並存 | 中 | 開放 | 任何 speed figure／馬位特徵只能覆蓋部分歷史，跨期比較會偏 | parser 已修（三個 importer 共用）；報表逐月標低覆蓋原因；未重抓前只用 2026-04 後且兩欄齊的場次做 speed 研究 | 重抓 2025-09～2026-11 缺欄場次並把覆蓋率寫入 `pipeline_status.results_quality_report` |
| R12 | **jockey_upgrade 早達標假象**：blend 0.15 首次回測即 ΔNLL<0、CI 全負、4/5 折，但屬多重測試下的單次命中，且覆蓋率僅 87.8%（首月 2025-09 只有 17%） | 中 | 監控 | 若因一次達標就開 live，可能重犯 SP 循環性／樣本不足錯誤 | flag 維持 off；只寫 shadow；正式上線需 ≥50 場真實 pre-race 賠率後獨立 A/B；與 jockeyTrainer 相關 r=0.57（差分）／0.85（水平）→ 只准 blend 合併 | 獨立 A/B 在真實賠率樣本重現 ΔNLL<0 且 CI 全負、≥4/5 折 |
| R11 | **going／track_course 歷史缺值與詞彙漂移**：補全前 18 場為空／英文 `Good`／舊值；舊 scraper 只認 9 種 going，官方「封地」被誤判無效 | 低 | 已緩解 | going 覆蓋不足會令未來跑道偏差研究樣本偏，且舊 whitelist 會靜靜丟值 | 4 個寫入點共用 `scripts/track_meta.py`（canonical＋英文／別名、拒絕多值猜測、加入封地）；`backfill_track_meta.py` httpx 補全（date/race_no 校驗、不覆蓋有效值）；實測 1,088 場 going 99.9%、track_course 100%；唯一缺口為官方取消的 ST-20261114-06 | 每場非取消賽事 going 非空；跑道偏差模型另需每個 going×賽道桶 ≥30 場 |

## 收集進度（2026-11-28 實測）

- 完整快照：**0/50**；partial 0；總追蹤 0；store `pipeline_status`；fallback JSON 2 bytes（空白）。
- 每日 log：tick＋每日 05:00 HKT cleanup 輸出 `complete_pre_race_races = X/50`，
  寫入 `pipeline_status.id='odds_snapshot_progress'`。
- 每日完整度報表：cleanup 自動產生，摘要寫 `pipeline_status.id='odds_snapshot_report'`；
  欄位凍結為 `race_id, race_date, venue, n_runners, n_horses_with_4_buckets,
  odds_nonnull_rate, available_at_complete_rate, bucket_offset_sec, missing_reason`。
- 每週週報：`python scripts/odds_snapshot_report.py --weekly`；每月審計：
  `python scripts/monthly_data_audit.py`；格式見 `docs/MONITORING.md`。
- Shadow 實測：11 場（2026-11-29 ST，全部 coverage=0 賠率未開）→ gate sparse；
  draw_v2 identity 最大差異 0.00000；avail_aware 平均 |Δp_final| 0.00101。
  未有近開跑缺賠率樣本，不可評分。
- 觸發：`complete_pre_race_races = 50` 後才按 `docs/PREREGISTERED_AB.md` 逐項 A/B；
  未達前時間加權融合、α 時間加權、drift 一律不准開。
- 線 2-A 實測（2026-11-28，唯讀）：1,087 場／13,511 匹有完成名次；finish_time 83.8%
  （HV 80.5%、ST 85.7%），margin 27.6%；16 行 margin >30L 屬尾隨馬（保留）；
  頭馬非最快 1 場（ST-20260308-05，94.64 vs 94.62s）。締速基準 28 組（距離未知不進組）。
  報表：`reports/results_quality_2026-11-28.md`、`reports/speed_baseline_2026-11-28.json`。
- 線 2-B 實測（2026-11-28，唯讀）：補全後 1,088 場 going 99.9%（唯一缺口＝官方取消
  ST-20261114-06）、track_course 100%；9 種 going，非好地 25.2%（274 場）。
  分桶：好地 813、好地至快地 229、草地黏地 11、好地至黏地 9、軟地 8、濕慢地 7、
  封地 6、慢地 2、快地 2 → 除好地／好地至快地外全部 <30 場，維持不建跑道偏差模型、flags off。
  報表：`reports/track_meta_2026-11-28.md`、`reports/track_meta_2026-11-28.json`。
- 線 2-C 實測（2026-11-28，離線 honest）：騎師欄位 100% 非空；特徵覆蓋 11,584/13,200
  （87.8%，2025-09 首月只有 17.0%，HV 90.9%／ST 85.9%）；r(score, jockeyTrainer)=0.5738、
  r(current_rate, jockeyTrainer)=0.8458 → 只 blend 合併、不另立因子。honest OOS 423 場：
  blend 0.15 ΔNLL −0.00376（CI −0.00721~−0.00034、4/5 折）達標；blend 0.30 CI 含 0 不達標。
  flag `jockey_upgrade` 維持 off，只寫 shadow。
  報表：`reports/jockey_upgrade_2026-11-28.md`、`reports/jockey_upgrade_2026-11-28.json`。

## 變更紀錄

- 2026-11-28：建立；涵蓋 P0 凍結、P1 shadow、P2 fallback 升級與 DDL 中斷。
- 2026-11-28：加入等待期監控（每日 log／每日完整度報表／每週／每月審計）與收集進度實測。
- 2026-11-28：線 2-A results parser（finish_time／margin）＋品質／覆蓋率報表＋締速基準；
  只 display，flags 全部維持 off。
- 2026-11-28：線 2-B going／track_course 共用 normalizer（含封地）＋4 個寫入點＋
  httpx 補全＋描述性變異報表；跑道偏差模型維持 off（分桶樣本不足）。
- 2026-11-28：線 2-C 騎師升級差特徵（as-of，防洩漏單測）＋shadow＋honest 回測；
  blend 0.15 達標但 flag 維持 off，只准 blend 入 jockeyTrainer，不得另立第 10 因子。
- 相關文件：`reports/phase1_freeze_2026-11-28.md`、`FLAGS.md`、`reports/honest_vs_current_v586.md`。