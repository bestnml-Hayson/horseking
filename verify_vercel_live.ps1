$u = "https://ai-live-ten.vercel.app"
Write-Host ("=== VERCEL DEPLOY E2E VERIFY: " + $u + " ===")
""

$tests = @(
    @("Home / HTML",                 "/",                                           "text/html",                    8000),
    @("manifest.webmanifest",        "/manifest.webmanifest",                       "application/manifest+json",    2000),
    @("sw.js (SW allowed)",          "/sw.js",                                       "application/javascript",       2000),
    @("app.js",                      "/app.js",                                      "application/javascript",       30000),
    @("ai.js",                       "/ai.js",                                       "application/javascript",       1000),
    @("style.css",                   "/style.css",                                   "text/css",                     5000),
    @("icon-192.png",                "/data/icons/icon-192.png",                    "image/png",                    4000),
    @("icon-512.png",                "/data/icons/icon-512.png",                    "image/png",                    12000),
    @("apple-touch-icon 180",        "/data/icons/icon-180.png",                    "image/png",                    3000),
    @("api/list.json direct",        "/api/list.json",                              "application/json",             4000),
    @("api/list (rewrite)",          "/api/list",                                    "application/json",             4000),
    @("api/races (rewrite)",         "/api/races",                                   "application/json",             4000),
    @("api/refresh_static",          "/api/refresh",                                 "application/json",             100),
    @("api/history #1 rewrite",      "/api/history/HV-20260610-01_race1_1800m_cls5.json","application/json",       30000),
    @("data/history #1 direct",      "/data/history/HV-20260610-01_race1_1800m_cls5.json","application/json",      30000),
    @("api/stats/jockeys_db",        "/api/stats/jockeys_db.json",                   "application/json",             2000),
    @("api/stats/trainers_db",       "/api/stats/trainers_db.json",                  "application/json",             1000),
    @("api/profiles/horses_db",      "/api/profiles/horses_db.json",                 "application/json",             80000),
    @("CURRENT race (HV 0923 R9)",   "/api/history/HV-20260923-09_race9_1800m_cls3_CURRENT.json","application/json",  3000)
)

$pass = 0
$fail = 0
$swAllowedOk = $false
$manifestStandalone = $false
$manifest192 = $false
$manifest512 = $false
$list134 = $false
$rewriteOk = $false

$wc = New-Object Net.WebClient
foreach ($t in $tests) {
    $name, $path, $expectedType, $minSize = $t[0], $t[1], $t[2], $t[3]
    $url = $u + $path
    try {
        $resp = Invoke-WebRequest -Uri $url -UseBasicParsing -TimeoutSec 25
        $code = [int]$resp.StatusCode
        $ctype = $resp.Headers["Content-Type"]
        if ($ctype -is [Array]) { $ctype = $ctype[0] }
        $size = [int]$resp.RawContentLength
        $ctypeMatch = ($ctype -like "$expectedType*")
        $sizeMatch = ($size -ge $minSize)
        $codeOk = ($code -eq 200)
        if ($name -like "*rewrite*") {
            if ($codeOk -and $sizeMatch) { $rewriteOk = $true }
        }
        $ok = $codeOk -and $sizeMatch -and $ctypeMatch
        if ($ok) { $pass++ } else { $fail++ }
        $mark = if ($ok) { "[PASS]" } else { "[FAIL]" }
        Write-Host ("{0} code={1,-3} size={2,-9} type={3,-45} → {4}" -f $mark, $code, $size, $ctype, $name)

        # Service-Worker-Allowed header
        if ($name -like "*sw*") {
            $swa = $resp.Headers["Service-Worker-Allowed"]
            if ($swa) {
                $swAllowedOk = ($swa -eq "/")
                Write-Host ("         Service-Worker-Allowed: {0} -> {1}" -f $swa, $(if ($swAllowedOk){"PASS"}else{"FAIL"}))
            } else {
                Write-Host "         ⚠️ Service-Worker-Allowed header MISSING (Chrome/Safari PWA install may need it)"
            }
        }

        # manifest validate fields
        if ($name -like "*manifest*") {
            try {
                $m = $resp.Content | ConvertFrom-Json
                $manifestStandalone = ($m.display -eq "standalone")
                $has192 = ($m.icons | Where-Object { $_.sizes -like "*192x192*" } | Measure-Object).Count -ge 1
                $has512 = ($m.icons | Where-Object { $_.sizes -like "*512x512*" } | Measure-Object).Count -ge 1
                $scOk = ($m.start_url -eq "/") -or ($m.start_url -like "/*")
                $nameOk = [bool]$m.name
                $manifest192 = $has192
                $manifest512 = $has512
                Write-Host ("         manifest display={0} start_url={1} icons192={2} icons512={3} nameExists={4}" -f $m.display, $m.start_url, $has192, $has512, $nameOk)
                if (-not $manifestStandalone) { $fail++; Write-Host "         ❌ manifest display not standalone!" }
                if (-not $has192) { $fail++; Write-Host "         ❌ manifest no 192 icon!" }
                if (-not $has512) { $fail++; Write-Host "         ❌ manifest no 512 icon!" }
            } catch {
                Write-Host ("         manifest parse FAIL: " + $_.Exception.Message)
            }
        }

        # list.json: count should be ~134
        if ($name -like "*list.json direct*") {
            try {
                $lst = $resp.Content | ConvertFrom-Json
                $cnt = $lst.total
                if ($cnt -ge 130) { $list134 = $true }
                Write-Host ("         list.json total_races={0} (expect 134)" -f $cnt)
            } catch { Write-Host ("         list.json parse FAIL: " + $_.Exception.Message) }
        }

    } catch {
        $fail++
        Write-Host ("[FAIL] EXCEPTION: " + $_.Exception.Message + " → " + $name)
    }
}

""
Write-Host "================ FINAL RESULT ================"
Write-Host ("  PASS: {0}    FAIL: {1}" -f $pass, $fail)
$criteriaAll = @(
    @($manifestStandalone, "manifest.display=standalone"),
    @($manifest192, "manifest has icon 192x192"),
    @($manifest512, "manifest has icon 512x512"),
    @($swAllowedOk, "sw.js Service-Worker-Allowed=/"),
    @($list134, "api/list.json total >= 130 races"),
    @($rewriteOk, "/api/* rewrites works")
)
$allOk = $true
foreach ($c in $criteriaAll) {
    $ok, $label = $c[0], $c[1]
    $mark = if ($ok) { "[✅ PASS]" } else { "[❌ FAIL]" }
    Write-Host ("  {0} {1}" -f $mark, $label)
    if (-not $ok) { $allOk = $false }
}
""
if ($fail -eq 0 -and $allOk) {
    Write-Host "🎉 200% ALL VERCEL CHECKS PASSED! PWA installable ready!"
    exit 0
} else {
    Write-Host "⚠️  Some checks failed. iPhone may still work but review above."
    exit 1
}
