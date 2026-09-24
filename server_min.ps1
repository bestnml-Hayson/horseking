Add-Type -AssemblyName System.Web
$port = 8080
$utf8NoBom = New-Object System.Text.UTF8Encoding $false
$publicDir = Join-Path $PSScriptRoot "public"
$dataDir = Join-Path $PSScriptRoot "data"
$listener = New-Object System.Net.HttpListener
$listener.Prefixes.Add("http://localhost:$port/")
$listener.Prefixes.Add("http://127.0.0.1:$port/")
$listener.Start()
Write-Host "SERVER RUNNING http://localhost:$port" -ForegroundColor Cyan
while ($listener.IsListening) {
    $ctx = $listener.GetContext()
    $req = $ctx.Request
    $res = $ctx.Response
    $path = [System.Web.HttpUtility]::UrlDecode($req.Url.AbsolutePath)
    if ($path -eq "/") { $path = "/index.html" }
    $file = Join-Path $publicDir $path.TrimStart("/")
    if (Test-Path $file -PathType Leaf) {
        $ext = [System.IO.Path]::GetExtension($file).ToLower()
        $ctype = "application/octet-stream"
        if ($ext -eq ".html") { $ctype = "text/html; charset=utf-8" }
        if ($ext -eq ".js") { $ctype = "application/javascript; charset=utf-8" }
        if ($ext -eq ".css") { $ctype = "text/css; charset=utf-8" }
        if ($ext -eq ".json") { $ctype = "application/json; charset=utf-8" }
        $bytes = [System.IO.File]::ReadAllBytes($file)
        $res.ContentType = $ctype
        $res.ContentLength64 = $bytes.Length
        $res.OutputStream.Write($bytes, 0, $bytes.Length)
        $st = Get-Date -Format HH:mm:ss
        Write-Host "[$st] 200 $path" -ForegroundColor Green
    } else {
        $msg = "404 Not Found"
        $msgBytes = $utf8NoBom.GetBytes($msg)
        $res.StatusCode = 404
        $res.ContentType = "text/plain; charset=utf-8"
        $res.ContentLength64 = $msgBytes.Length
        $res.OutputStream.Write($msgBytes, 0, $msgBytes.Length)
        $st = Get-Date -Format HH:mm:ss
        Write-Host "[$st] 404 $path" -ForegroundColor Red
    }
    $res.OutputStream.Close()
}