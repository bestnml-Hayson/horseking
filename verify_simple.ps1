$u = (Get-Content D:\Trae\horse\ngrok_url.txt -ErrorAction SilentlyContinue).Trim()
if (-not $u) { $u = "http://127.0.0.1:4040" }

# First check processes
$psAlive = Get-Process powershell -ErrorAction SilentlyContinue | Measure-Object | Select-Object -ExpandProperty Count
$ngAlive = Get-Process ngrok -ErrorAction SilentlyContinue | Measure-Object | Select-Object -ExpandProperty Count
"Processes: powershell=$psAlive  ngrok=$ngAlive"
""

# Check localhost server directly
$req = curl.exe -sS -m 10 -w "|%{http_code}|%{size_download}" -o D:\Trae\horse\_tmp1.html http://localhost:9000/
$parts = $req -split '\|'
"Localhost Server: HTTP " + $parts[1] + " size=" + $parts[2] + "B"
""

# Check ngrok 4040 API directly
try {
    $r = Invoke-RestMethod "http://127.0.0.1:4040/api/tunnels" -TimeoutSec 8
    if ($r -and $r.tunnels) {
        "Ngrok API OK, tunnels=" + ($r.tunnels.Count)
        foreach ($t in $r.tunnels) {
            "  -> " + $t.proto + ": " + $t.public_url
            if ($t.proto -eq "https") { $newU = $t.public_url }
        }
    }
} catch {
    "Ngrok API FAIL: " + $_.Exception.Message
    ""
    "STARTING NGROK now..."
    $token = [IO.File]::ReadAllText("D:\Trae\horse\_ngrok_token.txt").Trim()
    $env:NGROK_AUTHTOKEN = $token
    Start-Process -FilePath "D:\Trae\horse\ngrok.exe" -ArgumentList 'http 9000 --host-header="localhost:9000"' -WindowStyle Minimized
    Start-Sleep -Seconds 20
    $r2 = Invoke-RestMethod "http://127.0.0.1:4040/api/tunnels" -TimeoutSec 10
    foreach ($t in $r2.tunnels) {
        "  -> " + $t.proto + ": " + $t.public_url
        if ($t.proto -eq "https") { $newU = $t.public_url }
    }
}

""
if ($newU) {
    Set-Content -Path "D:\Trae\horse\ngrok_url.txt" -Value $newU -Encoding UTF8
    "FINAL HTTPS URL FOR IPHONE: " + $newU
    ""
    "VERIFY endpoints via this ngrok URL:"
    curl.exe -sS -m 18 -w "index    code=%{http_code} size=%{size_download}B`n" -o NUL $newU
    curl.exe -sS -m 18 -w "manifest code=%{http_code} size=%{size_download}B`n" -o NUL ($newU + "/manifest.webmanifest")
    curl.exe -sS -m 18 -w "sw.js    code=%{http_code} size=%{size_download}B`n" -o NUL ($newU + "/sw.js")
    curl.exe -sS -m 18 -w "icon192  code=%{http_code} size=%{size_download}B`n" -o NUL ($newU + "/data/icons/icon-192.png")
}
