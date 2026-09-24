Add-Type -AssemblyName System.Web
$port = 9000
$logFile = Join-Path $PSScriptRoot "server.log"
$utf8NoBom = New-Object System.Text.UTF8Encoding $false
$nl = [Environment]::NewLine
$banner = "[" + (Get-Date) + "] Starting server on port " + $port + " (NO AUTH)" + $nl
[IO.File]::WriteAllText($logFile, $banner, $utf8NoBom)
$publicDir = Join-Path $PSScriptRoot "public"
$dataDir = Join-Path $PSScriptRoot "data"
$wildcardOk = $false
$prefix1 = "http://localhost:" + $port + "/"
$prefix2 = "http://127.0.0.1:" + $port + "/"
$prefix3 = "http://+:" + $port + "/"
$listener = New-Object System.Net.HttpListener
try {
    $listener.Prefixes.Add($prefix3)
    try {
        $listener.Start()
        $wildcardOk = $true
        [IO.File]::AppendAllText($logFile, ("Added prefix: " + $prefix3 + " (ALL INTERFACES / WILDCARD + LAN / WAN ACCESS - STARTED OK)" + $nl), $utf8NoBom)
        [IO.File]::AppendAllText($logFile, ("SERVER STARTED OK (NO AUTH, wildcard +)" + $nl), $utf8NoBom)
    } catch {
        $line = "FAIL START wildcard (need Admin URL ACL): " + $_.Exception.Message + " --> fallback localhost only" + $nl
        [IO.File]::AppendAllText($logFile, $line, $utf8NoBom)
        try { $listener.Stop() } catch {}
        try { $listener.Close() } catch {}
        $listener = New-Object System.Net.HttpListener
        try {
            $listener.Prefixes.Add($prefix1)
            [IO.File]::AppendAllText($logFile, ("Added prefix: " + $prefix1 + " (fallback localhost only)" + $nl), $utf8NoBom)
        } catch {
            $line = "FAIL prefix " + $prefix1 + " : " + $_.Exception.Message + $nl
            [IO.File]::AppendAllText($logFile, $line, $utf8NoBom)
        }
        try {
            $listener.Prefixes.Add($prefix2)
            [IO.File]::AppendAllText($logFile, ("Added prefix: " + $prefix2 + $nl), $utf8NoBom)
        } catch {
            $line = "FAIL prefix " + $prefix2 + " : " + $_.Exception.Message + $nl
            [IO.File]::AppendAllText($logFile, $line, $utf8NoBom)
        }
        try {
            $listener.Start()
            [IO.File]::AppendAllText($logFile, ("SERVER STARTED OK (NO AUTH, localhost only)" + $nl), $utf8NoBom)
        } catch {
            $line = "FATAL START FAIL: " + $_.Exception.Message + $nl
            [IO.File]::AppendAllText($logFile, $line, $utf8NoBom)
            exit 1
        }
    }
} catch {
    $line = "FAIL prefix + wildcard add (non-admin normal): " + $_.Exception.Message + " --> fallback localhost only" + $nl
    [IO.File]::AppendAllText($logFile, $line, $utf8NoBom)
    try { $listener.Stop() } catch {}
    try { $listener.Close() } catch {}
    $listener = New-Object System.Net.HttpListener
    try {
        $listener.Prefixes.Add($prefix1)
        [IO.File]::AppendAllText($logFile, ("Added prefix: " + $prefix1 + " (fallback localhost only)" + $nl), $utf8NoBom)
    } catch {
        $line = "FAIL prefix " + $prefix1 + " : " + $_.Exception.Message + $nl
        [IO.File]::AppendAllText($logFile, $line, $utf8NoBom)
    }
    try {
        $listener.Prefixes.Add($prefix2)
        [IO.File]::AppendAllText($logFile, ("Added prefix: " + $prefix2 + $nl), $utf8NoBom)
    } catch {
        $line = "FAIL prefix " + $prefix2 + " : " + $_.Exception.Message + $nl
        [IO.File]::AppendAllText($logFile, $line, $utf8NoBom)
    }
    try {
        $listener.Start()
        [IO.File]::AppendAllText($logFile, ("SERVER STARTED OK (NO AUTH, localhost only)" + $nl), $utf8NoBom)
    } catch {
        $line = "FATAL START FAIL: " + $_.Exception.Message + $nl
        [IO.File]::AppendAllText($logFile, $line, $utf8NoBom)
        exit 1
    }
}
function WriteBanner() {
    Write-Host "=============================================================" -ForegroundColor Cyan
    $baLine = "= SERVER RUNNING http://localhost:" + $port + " (NO AUTH REQUIRED) ="
    Write-Host $baLine -ForegroundColor Cyan
    Write-Host ("  Local:    http://localhost:" + $port)
    $myIPs = @(Get-NetIPAddress -AddressFamily IPv4 -ErrorAction SilentlyContinue | Where-Object { $_.IPAddress -notlike "127.*" -and $_.IPAddress -notlike "169.254.*" } | Select-Object -ExpandProperty IPAddress)
    if (-not $myIPs) { $myIPs = @() }
    if ($wildcardOk -and $myIPs.Count -gt 0) {
        foreach ($ip in $myIPs) { Write-Host ("  LAN:      http://" + $ip + ":" + $port) -ForegroundColor Yellow }
        Write-Host "  PWA LAN:  Open the above LAN URL on mobile WiFi -> Share -> Add to Home Screen" -ForegroundColor Yellow
    } else {
        Write-Host ("  LAN/WAN:  Disabled (run PowerShell as ADMIN once, then execute:")
        Write-Host ("             netsh http add urlacl url=http://+:" + $port + "/ user=Everyone")
        Write-Host "             After restarting server, LAN access becomes available" -ForegroundColor DarkYellow
        Write-Host "  Ngrok:    ngrok http 9000 --basic-auth=`"user:pass`"   (WAN PWA access for mobile)"
        Write-Host "  PWA WAN:  Use Ngrok HTTPS URL on mobile to Install App"
    }
    Write-Host "  Endpoint: GET /api/refresh to trigger data sync"
    Write-Host "============================================================="
}
WriteBanner
$script:refreshRunning = $false
$script:lastRefreshResult = $null
$handlerPath = Join-Path $PSScriptRoot "api_refresh_handler.ps1"
$mimeHtml = "text/html; charset=utf-8"
$mimeJs = "application/javascript; charset=utf-8"
$mimeCss = "text/css; charset=utf-8"
$mimeJson = "application/json; charset=utf-8"
$mimePng = "image/png"
$mimeJpg = "image/jpeg"
$mimeSvg = "image/svg+xml"
$mimeCsv = "text/csv; charset=utf-8"
$mimeIco = "image/x-icon"
$mimeOct = "application/octet-stream"
function GetCType([string]$ext) {
    if ($ext -eq ".html") { return $mimeHtml }
    if ($ext -eq ".js") { return $mimeJs }
    if ($ext -eq ".css") { return $mimeCss }
    if ($ext -eq ".json") { return $mimeJson }
    if ($ext -eq ".png") { return $mimePng }
    if ($ext -eq ".jpg") { return $mimeJpg }
    if ($ext -eq ".svg") { return $mimeSvg }
    if ($ext -eq ".csv") { return $mimeCsv }
    if ($ext -eq ".ico") { return $mimeIco }
    return $mimeOct
}
function ResolveApiPath([string]$path) {
    $hp = "/api/history/"
    $pp = "/api/profiles/"
    $sp = "/api/stats/"
    $rp = "/api/references/"
    $tp = "/api/trackwork/"
    if ($path.StartsWith($hp)) {
        $fn = $path.Substring($hp.Length)
        $p1 = Join-Path $dataDir ("history\" + $fn)
        if (Test-Path $p1 -PathType Leaf) { return $p1 }
        $p2 = Join-Path $publicDir ("data\history\" + $fn)
        if (Test-Path $p2 -PathType Leaf) { return $p2 }
        return $null
    }
    if ($path -eq "/api/profiles/horses" -or $path -eq "/api/profiles/horses/") {
        $p1 = Join-Path $dataDir "profiles\horses_db.json"
        if (Test-Path $p1 -PathType Leaf) { return $p1 }
        $p2 = Join-Path $publicDir "data\profiles\horses_db.json"
        if (Test-Path $p2 -PathType Leaf) { return $p2 }
        return $null
    }
    if ($path.StartsWith($pp)) {
        $fn = $path.Substring($pp.Length)
        if ([string]::IsNullOrWhiteSpace($fn)) { $fn = "horses_db.json" }
        $p1 = Join-Path $dataDir ("profiles\" + $fn)
        if (Test-Path $p1 -PathType Leaf) { return $p1 }
        $p2 = Join-Path $publicDir ("data\profiles\" + $fn)
        if (Test-Path $p2 -PathType Leaf) { return $p2 }
        return $null
    }
    if ($path.StartsWith($sp)) {
        $fn = $path.Substring($sp.Length)
        $p1 = Join-Path $dataDir ("stats\" + $fn)
        if (Test-Path $p1 -PathType Leaf) { return $p1 }
        $p2 = Join-Path $publicDir ("data\stats\" + $fn)
        if (Test-Path $p2 -PathType Leaf) { return $p2 }
        return $null
    }
    if ($path.StartsWith($rp)) {
        $fn = $path.Substring($rp.Length)
        $p1 = Join-Path $dataDir ("references\" + $fn)
        if (Test-Path $p1 -PathType Leaf) { return $p1 }
        $p2 = Join-Path $publicDir ("data\references\" + $fn)
        if (Test-Path $p2 -PathType Leaf) { return $p2 }
        return $null
    }
    if ($path.StartsWith($tp)) {
        $fn = $path.Substring($tp.Length)
        $p1 = Join-Path $dataDir ("trackwork\" + $fn)
        if (Test-Path $p1 -PathType Leaf) { return $p1 }
        $p2 = Join-Path $publicDir ("data\trackwork\" + $fn)
        if (Test-Path $p2 -PathType Leaf) { return $p2 }
        return $null
    }
    if ($path -eq "/api/races" -or $path -eq "/api/races/" -or $path -eq "/api/list") {
        $hist = Join-Path $publicDir "data\history"
        if (Test-Path $hist) {
            $files = Get-ChildItem $hist -Filter "*.json" | Sort-Object Name
            $list = @()
            foreach ($f in $files) { $list += $f.Name }
            return ,@($list,$true)
        }
        return $null
    }
    return $null
}
function SendJson($Response, $Object, [int]$Depth) {
    $jsonBody = ConvertTo-Json $Object -Depth $Depth -Compress
    $bytes = $utf8NoBom.GetBytes($jsonBody)
    $Response.ContentType = $mimeJson
    $Response.ContentLength64 = $bytes.Length
    $Response.AddHeader("Cache-Control", "no-cache")
    $Response.AddHeader("Access-Control-Allow-Origin", "*")
    $Response.OutputStream.Write($bytes, 0, $bytes.Length)
    return $bytes.Length
}
while ($listener.IsListening) {
    try {
        $ctx = $listener.GetContext()
        $req = $ctx.Request
        $res = $ctx.Response
        $path = [System.Web.HttpUtility]::UrlDecode($req.Url.AbsolutePath)
        if ($path -eq "/") { $path = "/index.html" }
        $clientIP = $req.RemoteEndPoint.Address.ToString()
        $stamp = Get-Date -Format HH:mm:ss
        if ($path -eq "/api/refresh" -or $path -eq "/api/refresh/") {
            try {
                if ($script:refreshRunning) {
                    $busyObj = New-Object PSObject
                    $busyObj | Add-Member NoteProperty ok $false
                    $busyObj | Add-Member NoteProperty status "running"
                    $busyObj | Add-Member NoteProperty message "Data sync in progress"
                    $busyObj | Add-Member NoteProperty last_result $script:lastRefreshResult
                    [void](SendJson -Response $res -Object $busyObj -Depth 6)
                    $busyLine = "[" + $stamp + "] " + $clientIP + "  202 BUSY   /api/refresh"
                    Write-Host $busyLine -ForegroundColor Yellow
                    $res.OutputStream.Close()
                    continue
                }
                $script:refreshRunning = $true
                $startLine = "[" + $stamp + "] " + $clientIP + "  START   /api/refresh"
                Write-Host $startLine -ForegroundColor Cyan
                $handlerOut = & powershell.exe -NoProfile -NonInteractive -ExecutionPolicy Bypass -File $handlerPath
                $handlerJson = ($handlerOut | Out-String).Trim()
                $parseOk = $false
                $outObj = $null
                try {
                    $outObj = $handlerJson | ConvertFrom-Json -ErrorAction Stop
                    if ($outObj) { $parseOk = $true }
                } catch { $parseOk = $false }
                if (-not $parseOk) {
                    $outObj = New-Object PSObject
                    $outObj | Add-Member NoteProperty ok $false
                    $outObj | Add-Member NoteProperty message "handler parse failed"
                    if ($handlerJson) {
                        $mx = [Math]::Min(400, $handlerJson.Length)
                        $snippet = $handlerJson.Substring(0, $mx)
                        $outObj | Add-Member NoteProperty raw $snippet
                    }
                }
                $script:lastRefreshResult = $outObj
                $script:refreshRunning = $false
                [void](SendJson -Response $res -Object $outObj -Depth 10)
                $isOk = $false
                try {
                    $okProp = $outObj | Select-Object -ExpandProperty ok -ErrorAction Stop
                    if ($okProp -eq $true) { $isOk = $true }
                } catch { $isOk = $false }
                if ($isOk) { $logColor = [ConsoleColor]::Green } else { $logColor = [ConsoleColor]::Red }
                $durDisp = "n/a"
                try {
                    $durProp = $outObj | Select-Object -ExpandProperty duration_sec -ErrorAction Stop
                    $durDisp = $durProp.ToString() + " sec"
                } catch {}
                $st2 = Get-Date -Format HH:mm:ss
                $doneLine = "[" + $st2 + "] " + $clientIP + "  DONE    /api/refresh [" + $durDisp + "]"
                Write-Host $doneLine -ForegroundColor $logColor
                $res.OutputStream.Close()
                continue
            } catch {
                $script:refreshRunning = $false
                $errTxt = $_.Exception.Message
                $errObj = New-Object PSObject
                $errObj | Add-Member NoteProperty ok $false
                $errObj | Add-Member NoteProperty error $errTxt
                [void](SendJson -Response $res -Object $errObj -Depth 5)
                $st3 = Get-Date -Format HH:mm:ss
                $failLine = "[" + $st3 + "] " + $clientIP + "  500 FAIL  /api/refresh : " + $errTxt
                Write-Host $failLine -ForegroundColor Red
                $res.OutputStream.Close()
                continue
            }
        }
        $resolved = ResolveApiPath $path
        $file = $null
        $isApiList = $false
        if ($resolved -is [array] -and $resolved.Count -ge 2 -and $resolved[1] -eq $true) {
            $isApiList = $true
            $blen = SendJson -Response $res -Object $resolved[0] -Depth 3
            $szStr = $blen.ToString() + " bytes"
            $apiLine = "[" + $stamp + "] " + $clientIP + "  200 API  " + $path + " [" + $szStr + "]"
            Write-Host $apiLine -ForegroundColor Green
            $res.OutputStream.Close()
            continue
        } elseif ($resolved) {
            $file = $resolved
        } else {
            $file = Join-Path $publicDir $path.TrimStart("/")
        }
        if ($file -and (Test-Path $file -PathType Leaf)) {
            $ext = [System.IO.Path]::GetExtension($file).ToLower()
            $ctype = GetCType $ext
            $bytes = [System.IO.File]::ReadAllBytes($file)
            $res.ContentType = $ctype
            $res.ContentLength64 = $bytes.Length
            $res.AddHeader("Cache-Control", "no-cache")
            $res.AddHeader("Access-Control-Allow-Origin", "*")
            $res.OutputStream.Write($bytes, 0, $bytes.Length)
            $isJson = $false
            if ($ext -eq ".json") { $isJson = $true }
            if ($resolved) { $isJson = $true }
            $okLine = "[" + $stamp + "] " + $clientIP + "  200 OK   " + $path
            if ($isJson) { Write-Host $okLine -ForegroundColor Green } else { Write-Host $okLine }
        } else {
            $msgText = "404 Not Found: " + $path
            $msgBytes = $utf8NoBom.GetBytes($msgText)
            $res.StatusCode = 404
            $res.ContentType = "text/plain; charset=utf-8"
            $res.ContentLength64 = $msgBytes.Length
            $res.OutputStream.Write($msgBytes, 0, $msgBytes.Length)
            $nfLine = "[" + $stamp + "] " + $clientIP + "  404      " + $path
            Write-Host $nfLine -ForegroundColor Red
        }
        $res.OutputStream.Close()
    } catch {
        $errTxt = $_.Exception.Message
        $errMsg = "ERROR: " + $errTxt
        Write-Host $errMsg -ForegroundColor Red
        try {
            $dtm = Get-Date
            $sb = New-Object System.Text.StringBuilder
            [void]$sb.Append("LOG [")
            [void]$sb.Append($dtm)
            [void]$sb.Append("] EXCEPTION: ")
            [void]$sb.Append($errTxt)
            [void]$sb.Append($nl)
            $logLine = $sb.ToString()
            [IO.File]::AppendAllText($logFile, $logLine, $utf8NoBom)
        } catch {}
    }
}