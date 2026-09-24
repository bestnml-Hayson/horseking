$ErrorActionPreference = "Continue"
$ErrorActionPreference = "Continue"
# ====== 修復：跨平台自動偵測 repo root，兼容 GitHub Actions Linux + Windows ======
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$rootDir = if ([string]::IsNullOrWhiteSpace($scriptDir)) { (Get-Location).Path } else { $scriptDir }
if (-not $rootDir) { $rootDir = (Get-Location).Path }
$dataDir = Join-Path $rootDir "data"
$publicDataDir = Join-Path $rootDir (Join-Path "public" "data")
$appJsPath = Join-Path $rootDir (Join-Path "public" "app.js")
$logFile = Join-Path $rootDir "sync.log"
$utf8NoBom = [Text.UTF8Encoding]::new($false)
$dataDir = Join-Path $rootDir "data"
$publicDataDir = Join-Path $rootDir "public\data"
$appJsPath = Join-Path $rootDir "public\app.js"
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

# ====== 修復：跨平台 python 自動偵測 (GitHub Actions 用系統 python3) ======
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
Append-Log ("[BOOT] rootDir=" + $rootDir + " python=" + $pythonExe + " pythonOK=" + $pythonOK)

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

# ============ STEP A: _auto_update_results.py（完賽結算 + rename） ============
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
            Append-Log "[Step A] WARN: 冇 JSON output" "WARN"
        }
    } catch {
        Add-Error ("[A] FAIL: " + $_.Exception.Message)
    }
} else {
    Append-Log ("[Step A] SKIP: pythonOK=" + $pythonOK + " script=" + (Test-Path $updateScript)) "WARN"
}

# ============ STEP B: _auto_bootstrap_next_raceday.py（下賽日骨架） ============
$bootstrapScript = Join-Path $rootDir "_auto_bootstrap_next_raceday.py"
$nextDateDash = $null
$nextVenue = $null
if ($pythonOK -and (Test-Path $bootstrapScript)) {
    Append-Log "[Step B] Running _auto_bootstrap_next_raceday.py ..."
    try {
        $raw = & $pythonExe -B $bootstrapScript --min-days 1 2>&1
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
            Append-Log "[Step B] WARN: 冇 JSON output" "WARN"
        }
    } catch {
        Add-Error ("[B] FAIL: " + $_.Exception.Message)
    }
} else {
    Append-Log "[Step B] SKIP" "WARN"
}

# ============ STEP C: _fetch_live_odds.py（賽前 7 日內先抓 odds） ============
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
            Append-Log "[Step C] WARN: 冇 JSON output (odds 可能未開盤，正常)" "WARN"
        }
    } catch {
        Append-Log ("[Step C] WARN: " + $_.Exception.Message) "WARN"
    }
} else {
    if (-not $shouldFetchOdds) {
        Append-Log "[Step C] SKIP: 下一賽日超過 7 日或未知，暫唔抓 odds"
    } else {
        Append-Log "[Step C] SKIP" "WARN"
    }
}

# ============ STEP D: _populate_and_merge_cc.py（合併 on.cc 情報） ============
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

# ============ STEP E: rebuild_aggregate.ps1 + prepare_deploy.ps1 ============
$rebuildScript = Join-Path $rootDir "rebuild_aggregate.ps1"
if (Test-Path $rebuildScript) {
    Append-Log "[Step E] Running rebuild_aggregate.ps1 ..."
    try {
        & powershell.exe -NoProfile -NonInteractive -ExecutionPolicy Bypass -File $rebuildScript 2>&1 | ForEach-Object {
            $l = $_
            if ($l -is [System.Management.Automation.ErrorRecord]) { $l = $l.Exception.Message }
            Append-Log ("  E> " + [string]$l)
        }
        $summary.step_e_rebuild_ok = ($LASTEXITCODE -eq 0)
        Append-Log ("[Step E] rebuild OK=" + $summary.step_e_rebuild_ok)
    } catch {
        Add-Error ("[E] rebuild FAIL: " + $_.Exception.Message)
    }
} else {
    Append-Log "[Step E] SKIP rebuild" "WARN"
}

$prepareScript = Join-Path $rootDir "prepare_deploy.ps1"
if (Test-Path $prepareScript) {
    Append-Log "[Step E] Running prepare_deploy.ps1 (list.json)..."
    try {
        $rawPrep = & powershell.exe -NoProfile -NonInteractive -ExecutionPolicy Bypass -File $prepareScript 2>&1
        foreach ($l in ($rawPrep | ForEach-Object { [string]$_ })) {
            if ($l) { Append-Log ("  E-prep> " + $l) }
        }
    } catch {
        Append-Log ("[E-prep] WARN: " + $_.Exception.Message) "WARN"
    }
}

# ============ STEP F: file sync data→public + update RACE_FILES + write _last_sync.json ============
Append-Log "[Step F] File sync data → public..."
$subDirs = @("history", "profiles", "stats", "references", "trackwork")
foreach ($sd in $subDirs) {
    $srcDir = Join-Path $dataDir $sd
    $dstDir = Join-Path $publicDataDir $sd
    if (-not (Test-Path $dstDir)) { New-Item -ItemType Directory -Path $dstDir -Force | Out-Null }
    if (-not (Test-Path $srcDir)) {
        Append-Log "  Skip $sd (source missing)" "WARN"
        continue
    }
    $files = Get-ChildItem $srcDir -Recurse -File -ErrorAction SilentlyContinue
    foreach ($f in $files) {
        $rel = $f.FullName.Substring($srcDir.Length).TrimStart("\", "/")
        $dstFile = Join-Path $dstDir $rel
        $dstFolder = Split-Path $dstFile -Parent
        if (-not (Test-Path $dstFolder)) { New-Item -ItemType Directory -Path $dstFolder -Force | Out-Null }
        $needCopy = $true
        if (Test-Path $dstFile) {
            $dst = (Get-Item $dstFile).LastWriteTimeUtc
            $src = $f.LastWriteTimeUtc
            if ($dst -ge $src) { $needCopy = $false }
        }
        if ($needCopy) {
            try {
                Copy-Item $f.FullName $dstFile -Force
                $summary.step_f_copied_files++
            } catch {
                Add-Error ("[F] FAIL copy " + $sd + "/" + $rel + " : " + $_.Exception.Message)
            }
        } else {
            $summary.step_f_skipped_files++
        }
    }
}
Append-Log ("[Step F] File sync done: copied=" + $summary.step_f_copied_files + " skipped=" + $summary.step_f_skipped_files)
# ============ STEP G: Fetch + Parse HKJC Live Odds (即時賠率/退出馬/騎師變動) ============
Append-Log "[Step G] Fetch HKJC live odds page (HKJC/racing.hkjc.com)"
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
    $summary.step_g_odds_raw_saved = $true
    Append-Log ("  [G] Raw HTML saved: " + (Get-Item $oddsRawFile).Length + " bytes")

    # 簡單解析獨贏賠率 + 退出馬名單（HTML regex 快速提取，唔洗載入 HTML Agility）
    $html = $resp.Content
    $oddsOut = [ordered]@{
        generated_at = (Get-Date -Format "yyyy-MM-dd HH:mm:ss")
        racedate = $todayHK
        win_odds = @{}
        scratched = @()
        jockey_changes = @()
    }
    try {
        # 提取所有 <a ... title="馬號: XX, 馬名: XXX"> <span ...>賠率</span>
        $oddsCells = [regex]::Matches($html, 'RaceNo=(\d+).*?HorseNo=(\d+).*?class="win".*?>(\d+(?:\.\d+)?)', [System.Text.RegularExpressions.RegexOptions]::Singleline)
        foreach ($m in $oddsCells) {
            $rn = "R" + $m.Groups[1].Value
            $hn = [int]$m.Groups[2].Value
            $odds = [double]$m.Groups[3].Value
            if (-not $oddsOut.win_odds.Contains($rn)) { $oddsOut.win_odds[$rn] = @{} }
            $oddsOut.win_odds[$rn][$hn.ToString()] = $odds
        }
        # 退出馬：搵 "退出" 字樣 + 馬號/馬名
        $scratched = [regex]::Matches($html, '退出.*?No\.?\s*(\d+)', [System.Text.RegularExpressions.RegexOptions]::IgnoreCase)
        foreach ($sm in $scratched) { $oddsOut.scratched += [int]$sm.Groups[1].Value }
        $summary.step_g_odds_parsed = $true
    } catch {
        Append-Log ("  [G] Parse odds WARN: " + $_.Exception.Message) "WARN"
        $summary.step_g_odds_parsed = $false
    }

    $json = $oddsOut | ConvertTo-Json -Depth 10 -Compress
    [IO.File]::WriteAllText($oddsJsonFile, $json, $utf8NoBom)
    Append-Log ("  [G] Parsed odds JSON saved: " + (Get-Item $oddsJsonFile).Length + " bytes")

    # 自動同步去 public/data/odds（Vercel UI 用）
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
$seenRaceId = @{}
if (Test-Path $publicHistDir) {
    $allJson = Get-ChildItem $publicHistDir -Filter "*.json" | Where-Object { $_.Name -notlike "_*" } | Sort-Object Name
    foreach ($jf in $allJson) {
        $skip = $false
        try {
            $raw = [IO.File]::ReadAllText($jf.FullName, $utf8NoBom)
            $mj = [regex]::Match($raw, '"race_id"\s*:\s*"([^"]+)"')
            if ($mj.Success) {
                $rid = $mj.Groups[1].Value
                if ($seenRaceId.ContainsKey($rid)) { $skip = $true } else { $seenRaceId[$rid] = $jf.Name }
            }
        } catch {}
        if (-not $skip) { $raceFilesArray += $jf.Name }
    }
}
$summary.total_races = $raceFilesArray.Count

try {
    $appContent = [IO.File]::ReadAllText($appJsPath, $utf8NoBom)
    $pattern = "(?s)const\s+RACE_FILES\s*=\s*\[(.*?)\]\s*;"
    $m = [regex]::Match($appContent, $pattern)
    if ($m.Success) {
        $oldCount = ([regex]::Matches($m.Groups[1].Value, "'[^']+'")).Count
        $newLines = @()
        $newLines += "  const RACE_FILES = ["
        for ($i = 0; $i -lt $raceFilesArray.Count; $i++) {
            $fn = $raceFilesArray[$i]
            $comma = if ($i -lt $raceFilesArray.Count - 1) { "," } else { "" }
            $newLines += ("    '" + $fn + "'" + $comma)
        }
        $newLines += "  ];"
        $newBlock = $newLines -join "`n"
        $replacement = [regex]::Replace($appContent, $pattern, $newBlock)
        if ($replacement -ne $appContent) {
            [IO.File]::WriteAllText($appJsPath, $replacement, $utf8NoBom)
            $summary.new_races = $summary.total_races - $oldCount
            Append-Log ("[Step F] RACE_FILES updated: old=" + $oldCount + " new=" + $summary.total_races + " delta=" + $summary.new_races)
        } else {
            Append-Log ("[Step F] RACE_FILES no change (" + $oldCount + " files)")
        }
    } else {
        Append-Log "[Step F] WARN: Cannot find RACE_FILES in app.js" "WARN"
    }
} catch {
    Add-Error ("[F] RACE_FILES update FAIL: " + $_.Exception.Message)
}

Append-Log ("=== SYNC END A:u" + $summary.step_a_updated + " B:b" + $summary.step_b_bootstrapped + " C:o" + $summary.step_c_odds_updated + " F:t" + $summary.total_races + " ===")

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
    new_races = $summary.new_races
    total_races = $summary.total_races
        odds_ok = $summary.step_g_odds_ok
    odds_races = $summary.step_g_races
    scratched_count = $summary.step_g_scratched_count
    locked = $summary.locked
    errors = @($summary.errors)
}

$outJson = Join-Path $rootDir "data\_last_sync.json"
try {
    $outObj | ConvertTo-Json -Depth 10 -Compress | Out-File -FilePath $outJson -Encoding utf8
    $p2 = Join-Path $publicDataDir "_last_sync.json"
    Copy-Item $outJson $p2 -Force
} catch {}

$outObj | ConvertTo-Json -Depth 10
