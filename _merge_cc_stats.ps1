$ErrorActionPreference = "Continue"
$rootDir = "d:\Trae\horse"
$dataDir = Join-Path $rootDir "data"
$statsDir = Join-Path $dataDir "stats"
$historyDir = Join-Path $dataDir "history"
$publicDataDir = Join-Path $rootDir "public\data"
$utf8NoBom = [Text.UTF8Encoding]::new($false)

function Write-JsonFile {
    param([string]$Path, [object]$Data)
    $json = $Data | ConvertTo-Json -Depth 20 -Compress:$false
    [IO.File]::WriteAllText($Path, $json, $utf8NoBom)
}

function Read-JsonFile {
    param([string]$Path)
    if (-not (Test-Path $Path)) { return $null }
    $text = [IO.File]::ReadAllText($Path, $utf8NoBom)
    return $text | ConvertFrom-Json -Depth 20
}

$raceDate = "20260923"
$venue = "HV"
$jkcstatPath = Join-Path $statsDir "jkcstat_$raceDate.json"

Write-Host "[MERGE CC STATS] Date: $raceDate, Venue: $venue"
Write-Host "[MERGE CC STATS] Reading jkcstat file: $jkcstatPath"

$jkcstat = Read-JsonFile $jkcstatPath
if (-not $jkcstat) {
    Write-Host "[MERGE CC STATS][ERROR] jkcstat file missing, exit" -ForegroundColor Red
    exit 1
}

$trainerSurnameMap = @{
    "柏" = "方嘉柏"; "丁" = "丁冠豪"; "廖" = "廖康銘"; "游" = "游達榮"; "黎" = "黎昭昇"
    "桂" = "桂福特"; "賢" = "蘇偉賢"; "徐" = "徐雨石"; "韋" = "韋達"; "巫" = "巫偉傑"
    "希" = "大衛希斯"; "蔡" = "蔡約翰"; "葉" = "葉楚航"; "伍" = "伍鵬志"; "呂" = "呂健威"
    "沈" = "沈集成"; "賀" = "賀賢"; "羅" = "羅富全"; "告" = "告東尼"; "鄭" = "鄭俊偉"
    "文" = "文家良"; "丁" = "丁冠豪"; "霍" = "霍利時"; "鮑" = "鮑敘維"; "呂" = "呂健威"
    "蘇" = "蘇保羅"; "姚" = "姚本輝"; "徐" = "徐雨石"
}

function Get-TrainerFullName {
    param([string]$Surname)
    if ([string]::IsNullOrWhiteSpace($Surname)) { return $Surname }
    if ($trainerSurnameMap.ContainsKey($Surname)) { return $trainerSurnameMap[$Surname] }
    return $Surname
}

$expertTips = $jkcstat.cc_expert_tips
$raceBarrier = $jkcstat.cc_barrier
$raceTrackwork = $jkcstat.cc_trackwork
$hotHorses = $jkcstat.cc_hot_horses

$mergedCount = 0
$totalHorses = 0

for ($raceNo = 1; $raceNo -le 9; $raceNo++) {
    $pattern = "$venue-$raceDate-{0:D2}_race$raceNo`_*_CURRENT.json" -f $raceNo
    $raceFiles = Get-ChildItem $historyDir -Filter $pattern -File -ErrorAction SilentlyContinue
    if (-not $raceFiles -or $raceFiles.Count -eq 0) {
        Write-Host "[MERGE CC STATS][WARN] R$raceNo CURRENT file not found: $pattern" -ForegroundColor Yellow
        continue
    }
    $raceFile = $raceFiles[0]
    Write-Host "[MERGE CC STATS] Processing R$raceNo : $($raceFile.Name)"
    
    $race = Read-JsonFile $raceFile.FullName
    if (-not $race) { continue }
    
    $raceHorses = $race.horses
    $fieldName = "race_$raceNo"
    
    foreach ($h in $raceHorses) {
        $totalHorses++
        $hno = [int]$h.number
        $hname = $h.name
        
        $ccFields = [ordered]@{}
        
        if ($expertTips -and $expertTips.$fieldName) {
            $expertHorse = $expertTips.$fieldName | Where-Object { $_.horse_no -eq $hno }
            if ($expertHorse) {
                $ccFields["cc_expert_count"] = [int]$expertHorse.count
                $ccFields["cc_experts"] = @($expertHorse.experts)
                $tipList = @()
                foreach ($ex in $expertHorse.experts) {
                    $tipRank = @($jkcstat.cc_expert_tips_detail.$fieldName | Where-Object { $_.horse_no -eq $hno -and $_.expert -eq $ex } | Select-Object -First 1).rank
                    if ($tipRank) { $tipList += [ordered]@{expert=$ex; rank=[int]$tipRank} }
                    else { $tipList += [ordered]@{expert=$ex} }
                }
                $ccFields["cc_expert_tips"] = $tipList
            } else {
                $ccFields["cc_expert_count"] = 0
                $ccFields["cc_experts"] = @()
                $ccFields["cc_expert_tips"] = @()
            }
        }
        
        if ($raceBarrier -and $raceBarrier.$fieldName) {
            $barrierHorse = $raceBarrier.$fieldName | Where-Object { $_.horse_no -eq $hno }
            if ($barrierHorse) {
                $ccFields["cc_gear_symbols"] = $barrierHorse.gear_symbols
                $ccFields["cc_equipment"] = $barrierHorse.equipment
                if ($barrierHorse.PSObject.Properties.Name -contains "draw" -and $barrierHorse.draw) {
                    $ccFields["cc_draw_oncc"] = [int]$barrierHorse.draw
                }
                if ($barrierHorse.PSObject.Properties.Name -contains "jockey" -and $barrierHorse.jockey) {
                    $ccFields["cc_jockey_oncc"] = $barrierHorse.jockey
                }
                $ccFields["cc_weight_lbs_oncc"] = [int]$barrierHorse.weight_lbs
                if ($barrierHorse.PSObject.Properties.Name -contains "weight_change") {
                    $ccFields["cc_weight_change"] = [int]$barrierHorse.weight_change
                }
                if ($barrierHorse.PSObject.Properties.Name -contains "trainer_surname" -and $barrierHorse.trainer_surname) {
                    $ccFields["cc_trainer_surname"] = $barrierHorse.trainer_surname
                    $ccFields["cc_trainer_oncc"] = Get-TrainerFullName $barrierHorse.trainer_surname
                }
                if ($barrierHorse.PSObject.Properties.Name -contains "rating_cc" -and $barrierHorse.rating_cc) {
                    $ccFields["cc_rating_oncc"] = [int]$barrierHorse.rating_cc
                }
                if ($barrierHorse.PSObject.Properties.Name -contains "rating_change") {
                    $ccFields["cc_rating_change"] = [int]$barrierHorse.rating_change
                }
                if ($barrierHorse.PSObject.Properties.Name -contains "age" -and $barrierHorse.age) {
                    $ccFields["cc_age_oncc"] = [int]$barrierHorse.age
                }
                if ($barrierHorse.PSObject.Properties.Name -contains "body_weight_lbs" -and $barrierHorse.body_weight_lbs) {
                    $ccFields["cc_body_weight_lbs"] = [int]$barrierHorse.body_weight_lbs
                }
                if ($barrierHorse.PSObject.Properties.Name -contains "body_weight_change") {
                    $ccFields["cc_body_weight_change"] = [int]$barrierHorse.body_weight_change
                }
                if ($barrierHorse.PSObject.Properties.Name -contains "name_oncc") {
                    $ccFields["cc_name_oncc"] = $barrierHorse.name_oncc
                }
            }
        }
        
        if ($raceTrackwork -and $raceTrackwork.$fieldName) {
            $twHorse = $raceTrackwork.$fieldName | Where-Object { $_.horse_no -eq $hno }
            if ($twHorse) {
                $ccFields["cc_trackwork_summary"] = $twHorse.trackwork_summary
                if ($twHorse.PSObject.Properties.Name -contains "trackwork_daily" -and $twHorse.trackwork_daily) {
                    $daily = [ordered]@{}
                    foreach ($prop in $twHorse.trackwork_daily.PSObject.Properties) {
                        $daily[$prop.Name] = $prop.Value
                    }
                    $ccFields["cc_trackwork_daily"] = $daily
                }
                if ($twHorse.PSObject.Properties.Name -contains "trainer_surname" -and $twHorse.trainer_surname) {
                    if (-not $ccFields.Contains("cc_trainer_surname")) {
                        $ccFields["cc_trainer_surname"] = $twHorse.trainer_surname
                        $ccFields["cc_trainer_oncc"] = Get-TrainerFullName $twHorse.trainer_surname
                    }
                }
            }
        }
        
        foreach ($key in $ccFields.Keys) {
            $h | Add-Member -NotePropertyName $key -NotePropertyValue $ccFields[$key] -Force
        }
        $mergedCount++
    }
    
    $jkcstat.meta = $jkcstat.meta ?? [ordered]@{}
    $jkcstat.meta.merge_time = (Get-Date -Format "yyyy-MM-dd HH:mm:ss")
    $jkcstat.meta.trainer_surname_map_used = $true
    
    Write-JsonFile $raceFile.FullName $race
    Write-Host "[MERGE CC STATS]   -> R$raceNo done ($($raceHorses.Count) horses)"
    
    $pubDir = Join-Path $publicDataDir "history"
    if (Test-Path $pubDir) {
        Copy-Item $raceFile.FullName (Join-Path $pubDir $raceFile.Name) -Force
        Write-Host "[MERGE CC STATS]   -> synced to public/data/history"
    }
}

$jkcstat.meta.total_horses = $totalHorses
$jkcstat.meta.merged_horses = $mergedCount
Write-JsonFile $jkcstatPath $jkcstat

$pubStats = Join-Path $publicDataDir "stats"
if (Test-Path $pubStats) {
    Copy-Item $jkcstatPath (Join-Path $pubStats "jkcstat_$raceDate.json") -Force
    Write-Host "[MERGE CC STATS] jkcstat synced to public/data/stats"
}

Write-Host ""
Write-Host "[MERGE CC STATS] DONE: $mergedCount/$totalHorses horses merged with cc_* fields" -ForegroundColor Green
