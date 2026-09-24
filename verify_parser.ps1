$ErrorActionPreference = 'Stop'
$path = 'd:\Trae\horse\scraper.ps1'
$tokens = $null
$errors = $null
[System.Management.Automation.Language.Parser]::ParseFile($path, [ref]$tokens, [ref]$errors) | Out-Null
Write-Host ('Parser errors: ' + $errors.Count)
if ($errors.Count -gt 0) {
    foreach ($e in $errors) {
        $ln = $e.Extent.StartLineNumber
        Write-Host ('  L' + $ln + ': ' + $e.Message) -ForegroundColor Red
    }
    exit 1
} else {
    Write-Host 'PARSER ZERO ERROR - OK' -ForegroundColor Green
    exit 0
}
