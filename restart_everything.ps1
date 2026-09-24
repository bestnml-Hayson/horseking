$ErrorActionPreference = "Continue"
$root = "D:\Trae\horse"
Set-Location $root

Write-Host "=== STEP 0: Clean old processes ==="
Get-Process -Name ngrok -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
Get-NetTCPConnection -LocalPort 9000 -ErrorAction SilentlyContinue | ForEach-Object {
    if ($_.OwningProcess -gt 4) {
        try { Stop-Process -Id $_.OwningProcess -Force -ErrorAction SilentlyContinue } catch {}
    }
}
Start-Sleep -Seconds 3

Write-Host "=== STEP 1: Start build_server.ps1 (port 9000) ==="
$psi = New-Object Diagnostics.ProcessStartInfo
$psi.FileName = "powershell.exe"
$psi.Arguments = '-NoProfile -ExecutionPolicy Bypass -File "' + $root + '\build_server.ps1"'
$psi.UseShellExecute = $false
$psi.CreateNoWindow = $true
$psi.WorkingDirectory = $root
$srv = [Diagnostics.Process]::Start($psi)
Write-Host ("SERVER PID=" + $srv.Id + " ... wait 15s")
Start-Sleep -Seconds 15

try {
    $req = Invoke-WebRequest "http://localhost:9000/" -UseBasicParsing -TimeoutSec 15
    Write-Host ("OK Server HTTP " + $req.StatusCode + " bytes=" + $req.RawContentLength)
} catch {
    Write-Host ("FAIL Server: " + $_.Exception.Message)
    exit 1
}

Write-Host ""
Write-Host "=== STEP 2: Start Ngrok (no basic auth) ==="
$token = [IO.File]::ReadAllText($root + "\_ngrok_token.txt").Trim()
$ngrokLog = $root + "\ngrok.log"
if (Test-Path $ngrokLog) { Remove-Item $ngrokLog -Force -ErrorAction SilentlyContinue }

$psi2 = New-Object Diagnostics.ProcessStartInfo
$psi2.FileName = $root + "\ngrok.exe"
$psi2.Arguments = 'http 9000 --host-header="localhost:9000" --log="' + $ngrokLog + '" --log-format json'
$psi2.UseShellExecute = $false
$psi2.CreateNoWindow = $true
$psi2.WorkingDirectory = $root
$psi2.EnvironmentVariables["NGROK_AUTHTOKEN"] = $token
$ng = [Diagnostics.Process]::Start($psi2)
Write-Host ("NGROK PID=" + $ng.Id + " ... wait 18s")
Start-Sleep -Seconds 18

Write-Host ""
Write-Host "=== STEP 3: Fetch new HTTPS URL from Ngrok API ==="
$url = $null
for ($i=0; $i -lt 5; $i++) {
    try {
        $r = Invoke-RestMethod "http://127.0.0.1:4040/api/tunnels" -TimeoutSec 10
        $https = ($r.tunnels | Where-Object { $_.proto -eq "https" } | Select-Object -First 1)
        if ($https) { $url = $https.public_url; break }
    } catch { Start-Sleep -Seconds 3 }
}

if (-not $url) {
    Write-Host "FAIL: Cannot get Ngrok URL. Check ngrok.log."
    Get-Content $ngrokLog -ErrorAction SilentlyContinue | Select-Object -Last 20
    exit 2
}

Write-Host ""
Write-Host "======================================================"
Write-Host ("  IPHONE URL (Safari paste, NO PASSWORD!):  " + $url)
Write-Host "======================================================"
Write-Host ""

Write-Host "=== STEP 4: Verify endpoints (NO AUTH = 200) ==="
curl.exe -sS -m 12 -o NUL -w "index       NO-AUTH code=%{http_code} size=%{size_download}B`n" $url
curl.exe -sS -m 12 -o NUL -w "manifest    code=%{http_code} size=%{size_download}B`n" ($url + "/manifest.webmanifest")
curl.exe -sS -m 12 -o NUL -w "sw.js       code=%{http_code} size=%{size_download}B`n" ($url + "/sw.js")
curl.exe -sS -m 12 -o NUL -w "icon-192    code=%{http_code} size=%{size_download}B`n" ($url + "/data/icons/icon-192.png")
curl.exe -sS -m 12 -o NUL -w "history.js  code=%{http_code} size=%{size_download}B`n" ($url + "/data/history/race_index.json")

Write-Host ""
Write-Host "=== SAVE URL to ngrok_url.txt ==="
Set-Content -Path ($root + "\ngrok_url.txt") -Value $url -Encoding UTF8
Write-Host ("Saved to: " + $root + "\ngrok_url.txt")
