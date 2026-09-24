$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Drawing

$Sizes = 72,96,120,128,144,152,167,180,192,384,512

foreach ($Size in $Sizes) {
    Write-Host "Generating $Size..."
    $Bmp = New-Object System.Drawing.Bitmap $Size, $Size
    $G = [System.Drawing.Graphics]::FromImage($Bmp)
    $G.SmoothingMode = 'AntiAlias'
    $G.Clear([System.Drawing.Color]::FromArgb(10,10,10))

    $Pad = [int]([Math]::Floor($Size * 0.08))
    $Diam = $Size - (2 * $Pad)
    $Rect = New-Object System.Drawing.Rectangle $Pad, $Pad, $Diam, $Diam

    $GoldBrush = New-Object System.Drawing.SolidBrush ([System.Drawing.Color]::FromArgb(212,175,55))
    $G.FillEllipse($GoldBrush, $Rect)

    $PenW = [Math]::Max(2, [int]([Math]::Floor($Size * 0.04)))
    $Pen = New-Object System.Drawing.Pen ([System.Drawing.Color]::FromArgb(120,80,10)), $PenW
    $G.DrawEllipse($Pen, $Rect)

    $FontEm = [int]([Math]::Floor($Size * 0.55))
    $Font = New-Object System.Drawing.Font ('Arial Black', $FontEm, 'Bold', 'Pixel')
    $SFmt = New-Object System.Drawing.StringFormat
    $SFmt.Alignment = 'Center'
    $SFmt.LineAlignment = 'Center'

    $TextBrush = New-Object System.Drawing.SolidBrush ([System.Drawing.Color]::FromArgb(20,10,0))
    $G.DrawString('H', $Font, $TextBrush, [int]($Rect.X + $Rect.Width/2), [int]($Rect.Y + $Rect.Height/2), $SFmt)

    $G.Dispose()
    $p1 = Join-Path $PSScriptRoot "data\icons\icon-$Size.png"
    $p2 = Join-Path $PSScriptRoot "public\data\icons\icon-$Size.png"
    $Bmp.Save($p1, 'Png')
    $Bmp.Save($p2, 'Png')
    $Bmp.Dispose()
    Write-Host "  $p1 -> $((Get-Item $p1).Length) bytes"
}

foreach ($M in @(192,512)) {
    $src1 = Join-Path $PSScriptRoot "data\icons\icon-$M.png"
    $dst1 = Join-Path $PSScriptRoot "data\icons\icon-$M-maskable.png"
    Copy-Item $src1 $dst1 -Force
    $src2 = Join-Path $PSScriptRoot "public\data\icons\icon-$M.png"
    $dst2 = Join-Path $PSScriptRoot "public\data\icons\icon-$M-maskable.png"
    Copy-Item $src2 $dst2 -Force
    Write-Host "  maskable copy: $dst1"
}
Write-Host 'DONE.'
