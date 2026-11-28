# honest_v586 vs current_v586（一頁對照）

日期：2026-11-28　來源：`reports/backtest_honest_2026-11-28.md` / `.json`

## 定義

| Profile | 騎練勝率 | 因子權重 | 賠率 | 用途 |
|---|---|---|---|---|
| `current_v586` | 存檔（含未來賽果） | 已發佈權重（全樣本） | SP | **只作洩漏參考**，重現現行部署行為 |
| `honest_v586` | as-of（只用當日之前） | 每折只用 train fold 擬合 | 標記 pre-race / SP | **唯一未來比較基線** |
| `legacy_v576` | 存檔 | v5.76 舊權重／γ=1.3 | SP | 歷史對照，不作決策 |
| `as-of＋已發佈權重` | as-of | 已發佈 | SP | 診斷用中間變體 |

## 核心結果（423 場 OOS，2026-05-06 → 2026-11-25，5 折 expanding window）

| Variant | NLL | 95% CI NLL | Top1 | Top3 | ROI(EV) |
|---|---|---|---|---|---|
| current_v586 | 2.09304 | 2.01310 ~ 2.17180 | 27.9% | 59.3% | −0.3% |
| as-of＋已發佈權重 | 2.09603 | 2.01560 ~ 2.17430 | 28.1% | 57.9% | −1.6% |
| **honest_v586** | **2.09871** | 2.01900 ~ 2.17750 | 27.9% | 57.2% | −9.5% |
| legacy_v576 | 2.09787 | 2.01390 ~ 2.18240 | 30.0% | 58.2% | −35.6% |

- honest vs current：ΔNLL **+0.00567**，95% CI 0.00043 ~ 0.01086（current 嘅優勢部分來自洩漏）
- as-of vs current：ΔNLL +0.00299，CI 含 0
- honest 跌幅：ΔTop3 −2.1pp、ΔROI(EV) −9.2pp（**SP 值，只屬上限**）

## 真實賽前賠率子集

1057 場中只有 **9 場**有真賽前賠率；honest_v586 在該子集 NLL 1.81151、ROI(EV) −67.3%（樣本太小，不構成結論）。
其餘 1048 場賠率為 SP 複製，所有 γ／α／ROI 結論在凍結期內**不可**用於改預設。

## 使用規則

1. 任何新實驗、flag 開啟、α/γ 調整，一律同 `honest_v586` 比較。
2. `current_v586` 只可重現部署與除錯，不可宣稱改善。
3. ROI 必須標明 `SP upper bound`；真實賽前 ROI 要等 ≥50 場完整快照賽事。
4. 切換 profile：`MODEL_PROFILE=honest_v586`（Python）／`NEXT_PUBLIC_MODEL_PROFILE`（前端），預設仍是 `current_v586`。