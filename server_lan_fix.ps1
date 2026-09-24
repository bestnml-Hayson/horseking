Add-Type -AssemblyName System.Web
$port = 8081
$logFile = "d:\Trae\horse\server_8081.log"
[IO.File]::WriteAllText($logFile, ("[" + (Get-Date) + "] Starting server on port " + $port + "`r`n"), [Text.UTF8Encoding]::new($false))
$baPath = "d:\Trae\horse\_ngrok_basicauth.txt"
$baRaw = [IO.File]::ReadAllText($baPath).Trim()
$baPair = $baRaw.Split(':')
$basicUser = $baPair[0]
$basicPass = $baPair[1]
$basicExpectedB64 = [Convert]::ToBase64String([Text.Encoding]::ASCII.GetBytes(($basicUser + ":" + $basicPass)))
[IO.File]::AppendAllText($logFile, ("BasicAuth: " + $basicUser + " / pw_len=" + $basicPass.Length + " b64_len=" + $basicExpectedB64.Length + "`r`n"), [Text.UTF8Encoding]::new($false))
$publicDir = "d:\Trae\horse\public"
$listener = New-Object System.Net.HttpListener
$prefixesToTry = @(
    "http://localhost:$port/",
    "http://127.0.0.1:$port/"
)
foreach ($px in $prefixesToTry) {
    try {
        $listener.Prefixes.Add($px)
        [IO.File]::AppendAllText($logFile, ("Added prefix: " + $px + "`r`n"), [Text.UTF8Encoding]::new($false))
    } catch {
        [IO.File]::AppendAllText($logFile, ("FAIL add prefix " + $px + " : " + $_.Exception.Message + "`r`n"), [Text.UTF8Encoding]::new($false))
    }
}
try {
    $listener.Start()
    [IO.File]::AppendAllText($logFile, "SERVER STARTED OK`r`n", [Text.UTF8Encoding]::new($false))
} catch {
    [IO.File]::AppendAllText($logFile, ("FATAL START FAIL: " + $_.Exception.Message + "`r`n"), [Text.UTF8Encoding]::new($false))
    exit 1
}
Write-Host ("= SERVER RUNNING http://localhost:$port with HTTP Basic Auth =")
Write-Host ("  User: " + $basicUser)
Write-Host ("  (Auth applied at HttpListener level, ngrok-independent)")
Write-Host "======================================================"
$mime = @{
    ".html"="text/html; charset=utf-8";
    ".js"="application/javascript; charset=utf-8";
    ".css"="text/css; charset=utf-8";
    ".json"="application/json; charset=utf-8";
    ".png"="image/png"; ".jpg"="image/jpeg"; ".svg"="image/svg+xml";
    ".csv"="text/csv; charset=utf-8"; ".ico"="image/x-icon"
}
$utf8NoBom = [Text.UTF8Encoding]::new($false)
while ($listener.IsListening) {
    try {
        $ctx = $listener.GetContext()
        $req = $ctx.Request; $res = $ctx.Response
        $authOk = $false
        $authHeader = $req.Headers["Authorization"]
        if ($authHeader -and $authHeader.StartsWith("Basic ")) {
            $got = $authHeader.Substring(6).Trim()
            if ($got -ceq $basicExpectedB64) { $authOk = $true }
        }
        if (-not $authOk) {
            $res.StatusCode = 401
            $res.AddHeader("WWW-Authenticate", 'Basic realm="HorseAI"')
            $msg401 = $utf8NoBom.GetBytes("401 Unauthorized: login required (approved access only)")
            $res.ContentType = "text/plain; charset=utf-8"
            $res.ContentLength64 = $msg401.Length
            $res.OutputStream.Write($msg401, 0, $msg401.Length)
            $res.OutputStream.Close()
            Write-Host ("[" + (Get-Date -Format HH:mm:ss) + "] " + $req.RemoteEndPoint.Address + "  401 UNAUTH  " + $req.Url.AbsolutePath) -ForegroundColor Yellow
            continue
        }
        $path = [System.Web.HttpUtility]::UrlDecode($req.Url.AbsolutePath)
        if ($path -eq "/") { $path = "/index.html" }
        $file = Join-Path $publicDir $path.TrimStart("/")
        if (Test-Path $file -PathType Leaf) {
            $ext = [System.IO.Path]::GetExtension($file).ToLower()
            $ctype = if ($mime[$ext]) { $mime[$ext] } else { "application/octet-stream" }
            $bytes = [System.IO.File]::ReadAllBytes($file)
            $res.ContentType = $ctype
            $res.ContentLength64 = $bytes.Length
            $res.AddHeader("Cache-Control", "no-cache, no-store")
            $res.AddHeader("Access-Control-Allow-Origin", "*")
            $res.OutputStream.Write($bytes, 0, $bytes.Length)
            Write-Host ("[" + (Get-Date -Format HH:mm:ss) + "] " + $req.RemoteEndPoint.Address + "  200 OK   " + $path)
        } else {
            $msg = $utf8NoBom.GetBytes(("404 Not Found: " + $path))
            $res.StatusCode = 404
            $res.ContentType = "text/plain; charset=utf-8"
            $res.ContentLength64 = $msg.Length
            $res.OutputStream.Write($msg, 0, $msg.Length)
            Write-Host ("[" + (Get-Date -Format HH:mm:ss) + "] " + $req.RemoteEndPoint.Address + "  404      " + $path) -ForegroundColor Red
        }
        $res.OutputStream.Close()
    } catch {
        Write-Host ("ERROR: " + $_.Exception.Message) -ForegroundColor Red
    }
}
