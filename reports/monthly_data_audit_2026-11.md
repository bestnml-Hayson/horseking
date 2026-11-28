# 數據收集月度審計（2026-11-28）

唯讀報表：不寫入任何預測、flag 或預設。

## 1. 收集進度

- complete_pre_race_races = **0/50**；partial = 0；總追蹤 = 0。
- 儲存：`pipeline_status`；migration 檔存在：是；DB 表可用：否。
- missing_reason 分佈：無。

## 2. Fallback 體積

- 原始：0.0 KB；gzip 後：0.0 KB。
- 處置：低於 512 KB：可繼續，按月重檢。

## 3. availability_gate / draw_v2 shadow 審計

- shadow 賽事：11；gate sparse：11；covered：0。
- draw_v2 identity 最大差異：0.00000（預期 0；draw_v2 本身已是 live 預設，shadow 只作身份檢查）。
- avail_aware 平均 |Δp_final|：0.00101（未採納，只累積證據）。
- sparse 觸發 11 場，全部 coverage=0（賠率未開）——屬「未開價」而唔係「近開跑缺賠率」，未有可評分樣本；維持 shadow，等真實缺賠率場次。

## 4. 觸發條件與 escalation

- 收集開始：2026-11-28；已過 0 個月。
- fallback 收集第 1 個月（未滿 3 個月）：繼續觀察，按月重檢。
- 50 場門檻未達前：時間加權融合、α 時間加權 A/B、drift 特徵一律不准開。

## 5. RISKS.md 更新清單

- R5（樣本不足）：改為 complete = 0/50，partial = 0。
- R2（shadow 無變異）：sparse 全部為未開價（coverage=0）場次，仍未可評分。
- R4（fallback 體積）：更新 raw/gzip 大小與處置。
- R3（DDL 未套用）：更新 table_ready 與 escalation 狀態。

fallback 收集第 1 個月（未滿 3 個月）：繼續觀察，按月重檢。
