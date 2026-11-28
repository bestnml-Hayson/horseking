# 風險登記（Risk Register）

最後更新：2026-11-28　適用版本：v5.86（P0 凍結＋P1 shadow＋P2 快照收集）

| ID | 風險 | 等級 | 狀態 | 影響 | 緩解 | 關閉條件 |
|---|---|---|---|---|---|---|
| R1 | **SP 循環性**：1,048/1,057 場的「賽前賠率」其實是 SP 複製；γ、α、ROI 回測均帶循環 | 高 | 開放 | 任何基於 SP 的參數結論都可能反向 | γ 凍結 1.0、α 維持 0.2/0.35、所有 ROI 標 `SP upper bound`；凍結期內不得改預設 | 真實 pre-race 賠率 ≥50 場完整快照並重跑 honest 回測 |
| R2 | **Shadow 無變異**：歷史 SP 覆蓋≈100%，availability gate／avail_aware 在歷史數據上幾乎冇分別 | 中 | 開放 | 無法用歷史證明 shadow 成效 | shadow 只寫 `pipeline_status`，不動 live；等真實缺賠率場次 | 累積 ≥30 場有缺賠率的真實場次並比較 shadow vs live |
| R3 | **DDL 未套用**：本機 DNS 解析不到 DB host、無 `SUPABASE_DB_URL`／DB 密碼、無 SQL RPC，`odds_snapshots` 表未建立 | 中 | 開放 | 快照只存 JSON，不能 SQL join／跨場查詢 | writer 自動 fallback `pipeline_status.odds_snapshots`；migration 檔已備好 | 提供可連 DB 憑證並成功套用 `migrations/add_odds_snapshots.sql` |
| R4 | **Fallback 體積與延遲**：120 日、每 tick 每匹馬一列，JSON read-modify-write 隨時間變大 | 中 | 開放 | tick 寫入延遲上升；單行 JSON 過大 | 去重鍵含 available_at（只去完全重複）；完整度用 per-race `buckets` 索引；>50 場後盡快遷表 | 表建立並轉寫 fallback 資料後刪 JSON |
| R5 | **真賽前樣本不足**：只有 9 場 < 50 場門檻 | 高 | 開放 | 無法驗證時間加權融合、α 時間加權、drift 特徵 | 每 tick forward 收集；`complete_pre_race_races = X/50` 每日記錄 | X = 50 且合格場次覆蓋 HV/ST |
| R6 | **draw_v2 誤讀**：draw v2 本來已是 live 預設，shadow 只作身份檢查 | 低 | 已標註 | 可能被誤當成新改善 | 報告、flag registry 均明示「不算新改善」 | —（長期保留標註） |
| R7 | **avail_aware 未驗證**：隔離後 +0.0028、CI 含 0、3/5 fold | 中 | 已否決 | 若誤開會令 NLL 變差 | 維持 flag off，只留 shadow 證據；不再開 combined／stack 變體 | 未來真實缺賠率樣本重測並達標 |
| R8 | **CI 未經實跑**：新增 `.github/workflows/ci.yml` 只在 push 後才首次執行 | 低 | 開放 | 首次 push 可能因環境差異失敗 | 本地已跑同一組 pytest／tsx／validate；CI 失敗不影響 runtime | 首次 push 後 CI 綠燈 |
| R9 | **前端 profile 切換風險**：`NEXT_PUBLIC_MODEL_PROFILE` 可改前端行為 | 低 | 監控 | 若誤設 exp profile 會出 shadow 邏輯 | 預設 `current_v586`；exp profile 只存在於 config，未部署 | 保持預設直至 honest A/B 達標 |

## 變更紀錄

- 2026-11-28：建立；涵蓋 P0 凍結、P1 shadow、P2 fallback 升級與 DDL 中斷。
- 相關文件：`reports/phase1_freeze_2026-11-28.md`、`reports/flag_registry.md`、`reports/honest_vs_current_v586.md`。