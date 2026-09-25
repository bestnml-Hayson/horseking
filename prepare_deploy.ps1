$root = if ($PSScriptRoot) { $PSScriptRoot } else { (Get-Location).Path }
$histDir = Join-Path $root "public\data\history"
$apiDir = Join-Path $root "public\api"
$dataListDir = Join-Path $root "public\data"
$aiEngineDir = Join-Path $root "public\ai_engine"
$srcAiDir = Join-Path $root "ai_engine"
New-Item -ItemType Directory -Force -Path $aiEngineDir | Out-Null
if (Test-Path $srcAiDir) {
  Get-ChildItem $srcAiDir -Filter "*.js" -File | ForEach-Object {
    Copy-Item -Path $_.FullName -Destination (Join-Path $aiEngineDir $_.Name) -Force
  }
}
if (-not (Test-Path $apiDir)) { New-Item -ItemType Directory -Path $apiDir -Force | Out-Null }
if (-not (Test-Path $dataListDir)) { New-Item -ItemType Directory -Path $dataListDir -Force | Out-Null }
$utf8NoBom = [Text.UTF8Encoding]::new($false)

$list = [ordered]@{
    generated_at = (Get-Date).ToString("o")
    total = 0
    race_files = @()
}
$seenRid = @{}
$files = Get-ChildItem $histDir -Filter "*.json" -ErrorAction SilentlyContinue |
    Where-Object { $_.Name -notlike "_*" } |
    Sort-Object Name
$allRidGroups = @{}
foreach ($f in $files) {
    try {
        $raw = [IO.File]::ReadAllText($f.FullName, [Text.UTF8Encoding]::new($false))
        $m = [regex]::Match($raw, '"race_id"\s*:\s*"([^"]+)"')
        if ($m.Success) {
            $rid = $m.Groups[1].Value
            if (-not $allRidGroups.ContainsKey($rid)) { $allRidGroups[$rid] = @() }
            $allRidGroups[$rid] += $f.Name
        }
    } catch {}
}
foreach ($rid in $allRidGroups.Keys) {
    $candidates = $allRidGroups[$rid]
    $picked = $null
    foreach ($c in $candidates) {
        if ($c -match '_CURRENT\.json$') { $picked = $c; break }
    }
    if (-not $picked) { $picked = $candidates[0] }
    $list.race_files += $picked
}
$list.total = $list.race_files.Count
$json = $list | ConvertTo-Json -Depth 10
[IO.File]::WriteAllText((Join-Path $apiDir "list.json"), $json, $utf8NoBom)
[IO.File]::WriteAllText((Join-Path $dataListDir "list.json"), $json, $utf8NoBom)
Write-Host ("Generated list.json (api & data): total=" + $list.total)

# ===== UPDATE .gitignore (full 版，防止洩漏 tokens/logs) =====
$gitIgnore = @"
# === Secrets 機密，絕對唔可以上傳 ===
_ngrok_token.txt
_ngrok_basicauth.txt
*.token
*.pem
*.key
.env
.env.*

# === Logs 同 temp ===
*.log
sync.log
ngrok.log
server.log
*.tmp
*_tmp*.html
_tmp*.html
_tmp*.txt

# === PowerShell / Scheduler temp ===
_Debug/
_debug_*
*.pid
*.ps1xml

# === System junk ===
Thumbs.db
.DS_Store
desktop.ini
`$RECYCLE.BIN/
System Volume Information/

# === IDE / Editor ===
.vscode/
.idea/
*.swp
*.swo
*~

# === Node (Vercel 自動裝，唔使上) ===
node_modules/
npm-debug.log*
yarn-debug.log*
yarn-error.log*
.pnpm-debug.log*

# === Vercel local CLI cache ===
.vercel/
.vercel_project.json

# === 原始 HKJC PDF / debug HTML (唔需要 deploy，留本地) ===
data/references/*.pdf
data/references/_debug*.html
"@
[IO.File]::WriteAllText((Join-Path $root ".gitignore"), $gitIgnore, $utf8NoBom)
Write-Host "Updated .gitignore"

# ===== UPDATE .vercelignore (Vercel deploy 唔應該 upload 嘅) =====
$vercelIgnore = @"
# === Secrets 同 config 永遠唔好 deploy ===
_ngrok_token.txt
_ngrok_basicauth.txt
.env

# === Logs + temp ===
*.log
*.tmp
_tmp*
_debug*

# === 原始 scraper / scheduler ps1，Vercel 只 deploy public/ 其實唔會用到，但防止 ===
*.ps1
*.bat
*.cmd

# === 原始 root/data 都唔好傳 (只係 repo root /data/，唔包括 public/data/ 下面嘅 files) ===
/data/
scraper/
pdf/

# === 白名單：public/data/ 內所有 races/profiles/stats 一定要 deploy (PWA 靜態資料來源) ===
!public/data/**

# === PDF 原始排位卡 (太大，冇需要 deploy) ===
public/data/references/*.pdf
public/data/references/_debug*.html
public/data/賽事日期*.csv
"@
[IO.File]::WriteAllText((Join-Path $root ".vercelignore"), $vercelIgnore, $utf8NoBom)
Write-Host "Updated .vercelignore"

# ===== UPDATE refresh_static.json 同步 latest total_races =====
$refresh = [ordered]@{
    ok = $true
    status = "static-deploy"
    message = "Data refreshed on Vercel deploy. For live updates, run sync_data locally then git push / redeploy."
    copied_files = 0
    total_races = $list.total
    generated_at = (Get-Date).ToString("o")
    hint_manual = "Run: powershell -File sync_data.ps1 ; git add -A ; git commit -m 'data: refresh' ; git push  (Vercel auto rebuild)"
}
[IO.File]::WriteAllText((Join-Path $apiDir "refresh_static.json"), ($refresh | ConvertTo-Json -Depth 10), $utf8NoBom)
Write-Host ("Updated refresh_static.json total_races=" + $list.total)
