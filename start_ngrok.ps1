$ErrorActionPreference = 'Stop'
Set-Location "D:\Trae\horse"
$token = [IO.File]::ReadAllText("D:\Trae\horse\_ngrok_token.txt").Trim()
$ba = [IO.File]::ReadAllText("D:\Trae\horse\_ngrok_basicauth.txt").Trim()
Write-Host "TOKEN_LEN=$($token.Length) BA_LEN=$($ba.Length)"
if ([string]::IsNullOrWhiteSpace($token) -or [string]::IsNullOrWhiteSpace($ba)) {
    Write-Error "MISSING CRED FILES"; exit 1
}
$env:NGROK_AUTHTOKEN = $token
$logPath = "D:\Trae\horse\ngrok.log"
if (Test-Path $logPath) { Remove-Item $logPath -Force }

$psi = New-Object Diagnostics.ProcessStartInfo
$psi.FileName = "D:\Trae\horse\ngrok.exe"
$psi.Arguments = 'http 8081 --host-header="localhost:8081" --log="D:\Trae\horse\ngrok.log" --log-format json'
$psi.UseShellExecute = $false
$psi.CreateNoWindow = $true
$psi.WorkingDirectory = "D:\Trae\horse"
$psi.Environment["NGROK_AUTHTOKEN"] = $token
$p = [Diagnostics.Process]::Start($psi)
Write-Host "NGROK_PID=$($p.Id)"
Start-Sleep -Seconds 15

try {
    $r = Invoke-RestMethod -Uri "http://127.0.0.1:4040/api/tunnels" -TimeoutSec 8
    foreach ($t in $r.tunnels) {
        Write-Host ("TUNNEL: " + $t.proto + " -> " + $t.public_url + "  [local=" + $t.config.addr + "]")
    }
} catch {
    Write-Host "API_FAIL: $($_.Exception.Message)"
    if (Test-Path $logPath) { Write-Host "=== LOG TAIL 30 ==="; Get-Content $logPath -Tail 30 }
}
