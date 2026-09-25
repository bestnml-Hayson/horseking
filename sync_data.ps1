$ErrorActionPreference = "Continue"
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$rootDir = if ([string]::IsNullOrWhiteSpace($scriptDir)) { (Get-Location).Path } else { $scriptDir }
if (-not $rootDir) { $rootDir = (Get-Location).Path }
$dataDir = Join-Path $rootDir "data"
$publicDataDir = Join-Path $rootDir (Join-Path "public" "data")
$appJsPath = Join-Path $rootDir (Join-Path "public" "app.js")
$logFile = Join-Path $rootDir "sync.log"
$utf8NoBom = [Text.UTF8Encoding]::new($false)

function Append-Log {
    param([string]$Msg, [string]$Level = "INFO")
    $line = "[" + (Get-Date -Format "yyyy-MM-dd HH:mm:ss") + "][" + $Level + "] " + $Msg
    try { [IO.File]::AppendAllText($logFile, $line + "`r`n", $utf8NoBom) } catch {}
    Write-Host $line
}

function ExtractJson([string]$text) {
    if ([string]::IsNullOrWhiteSpace($text)) { return $null }
    $lastOpen = $text.LastIndexOf('{')
    $lastClose = $text.LastIndexOf('}')
    if ($lastOpen -lt 0 -or $lastClose -lt 0 -or $lastClose -le $lastOpen) { return $null }
    try {
        return $text.Substring($lastOpen, ($lastClose - $lastOpen + 1)) | ConvertFrom-Json -ErrorAction Stop
    } catch {
        return $null
    }
}

function Get-IntOr([object]$val, [int]$def = 0) {
    if ($null -eq $val) { return $def }
    try { return [int]$val } catch { return $def }
}

function Get-StrOr([object]$val, [string]$def = $null) {
    if ($null -eq $val) { return $def }
    $s = [string]$val
    if ([string]::IsNullOrWhiteSpace($s)) { return $def }
    return $s
}

Append-Log "=== SYNC START ==="

function Find-PythonExe {
    $candidates = @(
        (Join-Path $rootDir (Join-Path ".venv" "Scripts" "python.exe")),
        (Join-Path $rootDir (Join-Path ".venv" "bin" "python3")),
        "python3", "python", "py -3", "py"
    )
    foreach ($c in $candidates) {
        try {
            $null = & $c --version 2>&1
            if ($LASTEXITCODE -eq 0) { return $c }
        } catch {}
    }
    return $null
}
$pythonExe = Find-PythonExe
$pythonOK = (-not [string]::IsNullOrWhiteSpace($pythonExe))

function Find-PwshExe {
    $candidates = @("pwsh", "powershell", "powershell.exe", "pwsh-preview")
    foreach ($c in $candidates) {
        try {
            $null = & $c --version 2>&1
            if ($LASTEXITCODE -eq 0) { return $c }
        } catch {}
    }
    return $null
}
$pwshExe = Find-PwshExe
Append-Log ("[BOOT] rootDir=" + $rootDir + " python=" + $pythonExe + " pythonOK=" + $pythonOK + " pwshExe=" + $pwshExe)

$summary = [ordered]@{
    start_time = (Get-Date -Format "yyyy-MM-dd HH:mm:ss")
    step_a_updated = 0
    step_a_renamed = 0
    step_b_bootstrapped = 0
    step_b_next_date = $null
    step_b_next_venue = $null
    step_b_races = 0
    step_c_odds_updated = 0
    step_d_cc_ok = $false
    step_e_rebuild_ok = $false
    step_f_copied_files = 0
    step_f_skipped_files = 0
    step_g_odds_ok = $false
    step_g_races = 0
    step_g_scratched_count = 0
    total_races = 0
    new_races = 0
    locked = $false
    errors = New-Object System.Collections.Generic.List[string]
}

function Add-Error([string]$msg) {
    $summary.errors.Add($msg)
    Append-Log $msg "ERROR"
}

$histDir = Join-Path $dataDir "history"
$publicHistDir = Join-Path $publicDataDir "history"
foreach ($sd in @("history", "profiles", "stats", "references", "trackwork")) {
    $dstDir = Join-Path $publicDataDir $sd
    if (-not (Test-Path $dstDir)) { New-Item -ItemType Directory -Path $dstDir -Force | Out-Null }
}

$updateScript = Join-Path $rootDir "_auto_update_results.py"
if ($pythonOK -and (Test-Path $updateScript)) {
    Append-Log "[Step A] Running _auto_update_results.py ..."
    try {
        $raw = & $pythonExe -B $updateScript 2>&1
        $outText = ($raw | Out-String).Trim()
        foreach ($l in ($raw | ForEach-Object { [string]$_ })) {
            if ($l -and -not $l.StartsWith("{")) { Append-Log ("  A> " + $l) }
        }
        $json = ExtractJson $outText
        if ($json) {
            $summary.step_a_updated = Get-IntOr $json.updated
            $summary.step_a_renamed = Get-IntOr $json.renamed
            if ($json.errors -and $json.errors.Count -gt 0) {
                foreach ($e in $json.errors) { Add-Error ("[A] " + [string]$e) }
            }
            Append-Log ("[Step A] OK: updated=" + $summary.step_a_updated + " renamed=" + $summary.step_a_renamed)
        } else {
            Append-Log "[Step A] WARN: no JSON output" "WARN"
        }
    } catch {
        Add-Error ("[A] FAIL: " + $_.Exception.Message)
    }
} else {
    Append-Log ("[Step A] SKIP: pythonOK=" + $pythonOK + " script=" + (Test-Path $updateScript)) "WARN"
}

$bootstrapScript = Join-Path $rootDir "_auto_bootstrap_next_raceday.py"
$nextDateDash = $null
$nextVenue = $null
if ($pythonOK -and (Test-Path $bootstrapScript)) {
    Append-Log "[Step B] Running _auto_bootstrap_next_raceday.py (AUTO next raceday detection) ..."
    $bArgs = @("--min-days", "0")
    try {
        $raw = & $pythonExe -B $bootstrapScript @bArgs 2>&1
        $outText = ($raw | Out-String).Trim()
        foreach ($l in ($raw | ForEach-Object { [string]$_ })) {
            if ($l -and -not $l.StartsWith("{")) { Append-Log ("  B> " + $l) }
        }
        $json = ExtractJson $outText
        if ($json) {
            $summary.step_b_bootstrapped = Get-IntOr $json.bootstrapped
            $summary.step_b_next_date = Get-StrOr $json.next_date
            $summary.step_b_next_venue = Get-StrOr $json.venue
            $summary.step_b_races = Get-IntOr $json.race_count
            $nextDateDash = $summary.step_b_next_date
            $nextVenue = $summary.step_b_next_venue
            if ($json.errors -and $json.errors.Count -gt 0) {
                foreach ($e in $json.errors) {
                    $estr = [string]$e
                    if ($estr -match "Cannot find next race day") {
                        Append-Log ("  [B] INFO: " + $estr) "INFO"
                    } else {
                        Add-Error ("[B] " + $estr)
                    }
                }
            }
            Append-Log ("[Step B] OK: bootstrapped=" + $summary.step_b_bootstrapped + " next=" + $nextDateDash + "/" + $nextVenue + " races=" + $summary.step_b_races)
        } else {
            Append-Log "[Step B] WARN: no JSON output" "WARN"
        }
    } catch {
        Add-Error ("[B] FAIL: " + $_.Exception.Message)
    }
} else {
    Append-Log "[Step B] SKIP" "WARN"
}

$oddsScript = Join-Path $rootDir "_fetch_live_odds.py"
$shouldFetchOdds = $false
if ($nextDateDash -and $nextVenue) {
    try {
        $nd = [DateTime]::ParseExact($nextDateDash, "yyyy-MM-dd", $null)
        $diff = ($nd - (Get-Date).Date).TotalDays
        if ($diff -ge 0 -and $diff -le 7) { $shouldFetchOdds = $true }
    } catch {}
}
if ($pythonOK -and (Test-Path $oddsScript) -and $shouldFetchOdds) {
    Append-Log ("[Step C] Fetching odds for " + $nextDateDash + "/" + $nextVenue + " ...")
    try {
        $raw = & $pythonExe -B $oddsScript --date $nextDateDash --venue $nextVenue 2>&1
        $outText = ($raw | Out-String).Trim()
        foreach ($l in ($raw | ForEach-Object { [string]$_ })) {
            if ($l -and -not $l.StartsWith("{")) { Append-Log ("  C> " + $l) }
        }
        $json = ExtractJson $outText
        if ($json) {
            $summary.step_c_odds_updated = Get-IntOr $json.updated_files
            if ($json.errors -and $json.errors.Count -gt 0) {
                foreach ($e in $json.errors) { Append-Log ("  [C] WARN: " + [string]$e) "WARN" }
            }
            Append-Log ("[Step C] OK: odds_updated=" + $summary.step_c_odds_updated)
        } else {
            Append-Log "[Step C] WARN: no JSON output (odds may not be live yet, normal)" "WARN"
        }
    } catch {
        Append-Log ("[Step C] WARN: " + $_.Exception.Message) "WARN"
    }
} else {
    if (-not $shouldFetchOdds) {
        Append-Log "[Step C] SKIP: next race > 7 days away or unknown"
    } else {
        Append-Log "[Step C] SKIP" "WARN"
    }
}

$ccMergeScript = Join-Path $rootDir "_populate_and_merge_cc.py"
if ($pythonOK -and (Test-Path $ccMergeScript)) {
    $ccArgs = @()
    if ($nextDateDash -and $nextVenue) {
        $ymdNoDash = $nextDateDash -replace "-", ""
        $ccArgs = @("--date", $ymdNoDash, "--venue", $nextVenue, "--next-date")
    }
    Append-Log ("[Step D] Running _populate_and_merge_cc.py " + ($ccArgs -join " ") + " ...")
    try {
        $raw = & $pythonExe -B $ccMergeScript @ccArgs 2>&1
        foreach ($l in ($raw | ForEach-Object { [string]$_ })) {
            if ($l) { Append-Log ("  D> " + $l) }
        }
        $exitCC = $LASTEXITCODE
        $summary.step_d_cc_ok = ($exitCC -eq 0)
        Append-Log ("[Step D] OK=" + $summary.step_d_cc_ok + " (exit=" + $exitCC + ")")
    } catch {
        Add-Error ("[D] FAIL: " + $_.Exception.Message)
    }
} else {
    Append-Log "[Step D] SKIP" "WARN"
}

$rebuildScript = Join-Path $rootDir "rebuild_aggregate.ps1"
if (Test-Path $rebuildScript) {
    Append-Log "[Step E] Running rebuild_aggregate.ps1 ..."
    try {
        & $pwshExe -NoProfile -NonInteractive -ExecutionPolicy Bypass -File $rebuildScript 2>&1 | ForEach-Object {
            $l = $_
            if ($l -is [System.Management.Automation.ErrorRecord]) { $l = $l.Exception.Message }
            Append-Log ("  E> " + [string]$l)
        }
        $summary.step_e_rebuild_ok = ($LASTEXITCODE -eq 0)
        Append-Log ("[Step E] rebuild OK=" + $summary.step_e_rebuild_ok)
    } catch {
        Add-Error ("[E] FAIL: " + $_.Exception.Message)
    }
    $prepareScript = Join-Path $rootDir "prepare_deploy.ps1"
    if (Test-Path $prepareScript) {
        Append-Log "[Step E-2] Running prepare_deploy.ps1 ..."
        try {
            & $pwshExe -NoProfile -NonInteractive -ExecutionPolicy Bypass -File $prepareScript 2>&1 | ForEach-Object {
                $l = $_
                if ($l -is [System.Management.Automation.ErrorRecord]) { $l = $l.Exception.Message }
                Append-Log ("  E2> " + [string]$l)
            }
            Append-Log ("[Step E-2] prepare exit=" + $LASTEXITCODE)
        } catch { Append-Log ("[E-2] FAIL: " + $_.Exception.Message) "WARN" }
    }
} else {
    Append-Log "[Step E] SKIP (rebuild_aggregate.ps1 not found)" "WARN"
}

# Step H: 用 HKJC racecard 全覆蓋靜態排位欄位（last_6/gear/post_time/name/jockey/...）
# 自動用 Step B detect 出嘅 next date + venue；若 Step B 冇 detect 則 skip
$populateScript = Join-Path $rootDir "_auto_populate_full_entries.py"
$summary.step_h_populate_ok = $false
if ($pythonOK -and (Test-Path $populateScript) -and $nextDateDash -and $nextVenue) {
    Append-Log ("[Step H] Running _auto_populate_full_entries.py --date " + $nextDateDash + " --venue " + $nextVenue + " (ALL races, preserve odds/cc_* fields) ...")
    try {
        $popArgs = @("--date", $nextDateDash, "--venue", $nextVenue, "--skip-rebuild")
        $rawPop = & $pythonExe -B $populateScript @popArgs 2>&1
        foreach ($l in ($rawPop | ForEach-Object { [string]$_ })) {
            if ($l -and -not $l.StartsWith("{")) { Append-Log ("  H> " + $l) }
        }
        $outTextPop = ($rawPop | Out-String).Trim()
        $jsonPop = ExtractJson $outTextPop
        if ($jsonPop) {
            $summary.step_h_races_updated = Get-IntOr $jsonPop.races_updated 0
            $summary.step_h_last6_populated = Get-IntOr $jsonPop.last6_total_populated 0
            $summary.step_h_total_horses = Get-IntOr $jsonPop.total_horses 0
            if ($jsonPop.errors -and $jsonPop.errors.Count -gt 0) {
                foreach ($he in $jsonPop.errors) { Append-Log ("  [H] WARN: " + [string]$he) "WARN" }
            }
            $summary.step_h_populate_ok = $true
            Append-Log ("[Step H] OK: races=" + $summary.step_h_races_updated + " last6=" + $summary.step_h_last6_populated + "/" + $summary.step_h_total_horses)
        } else {
            Append-Log "[Step H] WARN: no JSON summary (script may have failed)" "WARN"
        }
    } catch {
        Append-Log ("[Step H] WARN: " + $_.Exception.Message) "WARN"
    }
} else {
    if (-not $nextDateDash -or -not $nextVenue) {
        Append-Log "[Step H] SKIP: Step B 未 detect 到下一賽馬日（如果要手動指定日期/俾 URL，直接跑 _auto_populate_full_entries.py）" "WARN"
    } else {
        Append-Log "[Step H] SKIP: 腳本不存在或 python 不可用" "WARN"
    }
}

# Step I: HKJC Fetch ALL 6 Data Sources（晨操/形勢/異常/獸醫/賽事報告）
# 依賴 Step H 已經 populate 晒基礎 JSON（搵到 race JSON file 先 merge）
# ⭐ 完全唔覆蓋靜態 12 欄 + odds/cc_*/official_result，只 merge 新動態補充欄（trackwork_score/form_score/except_score/vet_score/...）
$fetchAllScript = Join-Path $rootDir "_hkjc_fetch_all_racedata.py"
$summary.step_i_fetchall_ok = $false
$summary.step_i_horses_with_supplement = 0
$summary.step_i_errors = @()
if ($pythonOK -and (Test-Path $fetchAllScript) -and $nextDateDash -and $nextVenue) {
    Append-Log ("[Step I] Running _hkjc_fetch_all_racedata.py --date " + $nextDateDash + " --venue " + $nextVenue + " (fetch trackwork/formline/except/vet/report ALL races)...")
    try {
        $fiArgs = @("--date", $nextDateDash, "--venue", $nextVenue, "--skip-rebuild")
        $rawFi = & $pythonExe -B $fetchAllScript @fiArgs 2>&1
        foreach ($l in ($rawFi | ForEach-Object { [string]$_ })) {
            if ($l -and -not $l.StartsWith("{") -and $l -ne "==== STEP I SUMMARY ====" -and $l -ne "========================") {
                Append-Log ("  I> " + $l)
            }
        }
        $outTextFi = ($rawFi | Out-String).Trim()
        $jsonFi = ExtractJson $outTextFi
        if ($jsonFi) {
            $summary.step_i_races_processed = Get-IntOr $jsonFi.total_horses_with_supplement -1
            $summary.step_i_horses_with_supplement = Get-IntOr ($jsonFi.total_horses_with_supplement -as [int]) 0
            if ($jsonFi.errors -and $jsonFi.errors.Count -gt 0) {
                $summary.step_i_errors = @($jsonFi.errors | ForEach-Object { [string]$_ } | Select-Object -First 10)
                foreach ($e in $summary.step_i_errors) { Append-Log ("  [I] WARN: " + $e) "WARN" }
            }
            $summary.step_i_per_info_bytes = $jsonFi.per_info_fetch_bytes
            $summary.step_i_fetchall_ok = $true
            Append-Log ("[Step I] OK: horses_with_supplement=" + $summary.step_i_horses_with_supplement)
        } else {
            Append-Log "[Step I] WARN: no JSON summary (parser may be empty or HKJC page 404) → safe skip" "WARN"
        }
    } catch {
        Append-Log ("[Step I] SAFE SKIP (HKJC fetch 失敗唔會令 pipeline fail): " + $_.Exception.Message) "WARN"
        $summary.step_i_fetchall_ok = $false
    }
} else {
    if (-not $nextDateDash -or -not $nextVenue) {
        Append-Log "[Step I] SKIP: Step B 未 detect 到下一賽馬日（手動用 _hkjc_fetch_all_racedata.py --date）" "WARN"
    } else {
        Append-Log "[Step I] SKIP: 腳本不存在或 python 不可用" "WARN"
    }
}

# Step J: on.cc 東方日報 auto fetch（最後來料 / 排位差異 / 晨操摘要 / 名家心水 / 退馬表）
# ⭐ 只覆蓋 cc_* 專屬欄；絕對唔碰靜態 core 12 欄 / odds / official_result / Step I supplement 8+ 新欄
# ⭐ Safe skip：首頁 CF block 或任何頁 404 唔 kill pipeline
$onccFetchScript = Join-Path $rootDir "_oncc_fetch_all.py"
$summary.step_j_oncc_ok = $false
$summary.step_j_expert_horses = 0
$summary.step_j_errors = @()
if ($pythonOK -and (Test-Path $onccFetchScript) -and $nextDateDash -and $nextVenue) {
    Append-Log ("[Step J] Running _oncc_fetch_all.py --date " + $nextDateDash + " --venue " + $nextVenue + " (on.cc 東方日報 fetch)...")
    try {
        $jArgs = @("--date", $nextDateDash, "--venue", $nextVenue)
        $rawJ = & $pythonExe -B $onccFetchScript @jArgs 2>&1
        foreach ($l in ($rawJ | ForEach-Object { [string]$_ })) {
            if ($l -and -not $l.StartsWith("{") -and $l -ne "==== STEP J (ON.CC) SUMMARY ====" -and $l -ne "================================") {
                Append-Log ("  J> " + $l)
            }
        }
        $outTextJ = ($rawJ | Out-String).Trim()
        $jsonJ = ExtractJson $outTextJ
        if ($jsonJ) {
            $summary.step_j_expert_horses = Get-IntOr $jsonJ.expert_horses_total 0
            $summary.step_j_tw_horses = Get-IntOr $jsonJ.tw_horses_total 0
            $summary.step_j_barrier_horses = Get-IntOr $jsonJ.barrier_horses_total 0
            if ($jsonJ.errors -and $jsonJ.errors.Count -gt 0) {
                $summary.step_j_errors = @($jsonJ.errors | ForEach-Object { [string]$_ } | Select-Object -First 10)
                foreach ($e in $summary.step_j_errors) { Append-Log ("  [J] WARN: " + $e) "WARN" }
            }
            $summary.step_j_oncc_ok = $true
            Append-Log ("[Step J] OK: expert=" + $summary.step_j_expert_horses + " tw=" + $summary.step_j_tw_horses + " barrier=" + $summary.step_j_barrier_horses)
        } else {
            Append-Log "[Step J] WARN: no JSON summary (on.cc homepage 可能被 CF block → safe skip)" "WARN"
        }
    } catch {
        Append-Log ("[Step J] SAFE SKIP (on.cc fetch fail 唔會 kill pipeline): " + $_.Exception.Message) "WARN"
        $summary.step_j_oncc_ok = $false
    }
} else {
    if (-not $nextDateDash -or -not $nextVenue) {
        Append-Log "[Step J] SKIP: Step B 未 detect 到下一賽馬日（手動用 _oncc_fetch_all.py --date）" "WARN"
    } else {
        Append-Log "[Step J] SKIP: 腳本不存在或 python 不可用" "WARN"
    }
}

Append-Log "[Step F] Syncing data/* -> public/data/*"
$subDirs = @("history", "stats", "profiles", "references", "trackwork", "odds")
$f_copied = 0
$f_skipped = 0
foreach ($sub in $subDirs) {
    $src = Join-Path $dataDir $sub
    $dst = Join-Path $publicDataDir $sub
    if (-not (Test-Path $src)) { continue }
    if (-not (Test-Path $dst)) { New-Item -ItemType Directory -Path $dst -Force | Out-Null }
    Get-ChildItem -Path $src -Recurse -File | ForEach-Object {
        $rel = $_.FullName.Substring($src.Length).TrimStart('\', '/')
        $destFile = Join-Path $dst $rel
        $destDir = Split-Path -Parent $destFile
        if (-not (Test-Path $destDir)) { New-Item -ItemType Directory -Path $destDir -Force | Out-Null }
        $doCopy = $true
        if (Test-Path $destFile) {
            try {
                $srcHash = (Get-FileHash -Path $_.FullName -Algorithm MD5).Hash
                $dstHash = (Get-FileHash -Path $destFile -Algorithm MD5).Hash
                if ($srcHash -eq $dstHash) { $doCopy = $false; $f_skipped++ }
            } catch {}
        }
        if ($doCopy) {
            try { Copy-Item -Path $_.FullName -Destination $destFile -Force; $f_copied++ } catch {}
        }
    }
}
$summary.step_f_copied_files = $f_copied
$summary.step_f_skipped_files = $f_skipped
Append-Log ("[Step F] File sync done: copied=" + $f_copied + " skipped=" + $f_skipped)

Append-Log "[Step G] Fetch HKJC live odds page"
$oddsDir = Join-Path $dataDir "odds"
$publicOddsDir = Join-Path $publicDataDir "odds"
if (-not (Test-Path $oddsDir)) { New-Item -ItemType Directory -Path $oddsDir -Force | Out-Null }
if (-not (Test-Path $publicOddsDir)) { New-Item -ItemType Directory -Path $publicOddsDir -Force | Out-Null }

$todayHK = (Get-Date).ToString("yyyy-MM-dd")
$oddsUrl = "https://racing.hkjc.com/racing/information/chinese/Racing/Odds.aspx?racedate=$($todayHK -replace '-','/')"
$oddsRawFile = Join-Path $oddsDir "$todayHK.html"
$oddsJsonFile = Join-Path $oddsDir "$todayHK.json"
$summary.step_g_odds_ok = $false
try {
    $resp = Invoke-WebRequest -Uri $oddsUrl -UseBasicParsing -TimeoutSec 45 -ErrorAction Stop
    [IO.File]::WriteAllText($oddsRawFile, $resp.Content, $utf8NoBom)
    Append-Log ("  [G] Raw HTML saved: " + (Get-Item $oddsRawFile).Length + " bytes")

    $html = $resp.Content
    $oddsOut = [ordered]@{
        generated_at = (Get-Date -Format "yyyy-MM-dd HH:mm:ss")
        racedate = $todayHK
        win_odds = @{}
        scratched = @()
        jockey_changes = @()
    }
    try {
        $oddsCells = [regex]::Matches($html, 'RaceNo=(\d+).*?HorseNo=(\d+).*?class="win".*?>(\d+(?:\.\d+)?)', [System.Text.RegularExpressions.RegexOptions]::Singleline)
        foreach ($m in $oddsCells) {
            $rn = "R" + $m.Groups[1].Value
            $hn = [int]$m.Groups[2].Value
            $odds = [double]$m.Groups[3].Value
            if (-not $oddsOut.win_odds.Contains($rn)) { $oddsOut.win_odds[$rn] = @{} }
            $oddsOut.win_odds[$rn][$hn.ToString()] = $odds
        }
        $scratched = [regex]::Matches($html, '退出.*?No\.?\s*(\d+)', [System.Text.RegularExpressions.RegexOptions]::IgnoreCase)
        foreach ($sm in $scratched) { $oddsOut.scratched += [int]$sm.Groups[1].Value }
    } catch {
        Append-Log ("  [G] Parse odds WARN: " + $_.Exception.Message) "WARN"
    }

    $json = $oddsOut | ConvertTo-Json -Depth 10 -Compress
    [IO.File]::WriteAllText($oddsJsonFile, $json, $utf8NoBom)
    Append-Log ("  [G] Parsed odds JSON saved: " + (Get-Item $oddsJsonFile).Length + " bytes")

    Copy-Item $oddsRawFile (Join-Path $publicOddsDir "$todayHK.html") -Force
    Copy-Item $oddsJsonFile (Join-Path $publicOddsDir "$todayHK.json") -Force
    $summary.step_g_odds_ok = $true
    $summary.step_g_races = $oddsOut.win_odds.Keys.Count
    $summary.step_g_scratched_count = $oddsOut.scratched.Count
    Append-Log ("  [G] OK races=" + $summary.step_g_races + " scratched=" + $summary.step_g_scratched_count)
} catch {
    Append-Log ("  [G] Fetch FAIL (normal if no race today): " + $_.Exception.Message) "WARN"
    $summary.step_g_odds_ok = $false
}

$raceFilesArray = @()
$seenRidGroups = @{}
if (Test-Path $publicHistDir) {
    $allJson = Get-ChildItem $publicHistDir -Filter "*.json" | Where-Object { $_.Name -notlike "_*" } | Sort-Object Name
    foreach ($jf in $allJson) {
        try {
            $raw = [IO.File]::ReadAllText($jf.FullName, $utf8NoBom)
            $mj = [regex]::Match($raw, '"race_id"\s*:\s*"([^"]+)"')
            if ($mj.Success) {
                $rid = $mj.Groups[1].Value
                if (-not $seenRidGroups.ContainsKey($rid)) { $seenRidGroups[$rid] = New-Object System.Collections.Generic.List[string] }
                $seenRidGroups[$rid].Add($jf.Name)
            }
        } catch {}
    }
    foreach ($rid in $seenRidGroups.Keys) {
        $cands = $seenRidGroups[$rid]
        $picked = $null
        foreach ($c in $cands) {
            if ($c -match '_CURRENT\.json$') { $picked = $c; break }
        }
        if (-not $picked) { $picked = $cands[0] }
        $raceFilesArray += $picked
    }
}
$summary.total_races = $raceFilesArray.Count

try {
    $summary.new_races = $seenRidGroups.Count
    $summary.locked = $false
    $outObj = [ordered]@{
        ok = ($summary.errors.Count -eq 0)
        start_time = $summary.start_time
        end_time = (Get-Date -Format "yyyy-MM-dd HH:mm:ss")
        updated = $summary.step_a_updated
        renamed = $summary.step_a_renamed
        bootstrapped = $summary.step_b_bootstrapped
        next_date = $summary.step_b_next_date
        next_venue = $summary.step_b_next_venue
        odds_updated = $summary.step_c_odds_updated
        cc_ok = $summary.step_d_cc_ok
        rebuild_ok = $summary.step_e_rebuild_ok
        copied_files = $summary.step_f_copied_files
        skipped_files = $summary.step_f_skipped_files
        odds_ok = $summary.step_g_odds_ok
        odds_races = $summary.step_g_races
        scratched_count = $summary.step_g_scratched_count
        new_races = $summary.new_races
        total_races = $summary.total_races
        locked = $summary.locked
        errors = @($summary.errors)
    }
    $lastSyncPath = Join-Path $publicDataDir "_last_sync.json"
    [IO.File]::WriteAllText($lastSyncPath, ($outObj | ConvertTo-Json -Depth 10 -Compress), $utf8NoBom)
    $listJsonPath = Join-Path $publicDataDir "list.json"
    if (-not (Test-Path $listJsonPath)) {
        [IO.File]::WriteAllText($listJsonPath, (($raceFilesArray | ConvertTo-Json -Compress)), $utf8NoBom)
    }
    Append-Log ("[FINAL] total_races=" + $summary.total_races + " new_races=" + $summary.new_races + " errors=" + $summary.errors.Count)
} catch {
    Append-Log ("[FINAL] FAIL: " + $_.Exception.Message) "ERROR"
}

Append-Log "=== SYNC END ==="
exit (if ($summary.errors.Count -eq 0) { 0 } else { 1 })
