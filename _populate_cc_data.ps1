$ErrorActionPreference = "Stop"
$rootDir = "d:\Trae\horse"
$dataDir = Join-Path $rootDir "data"
$statsDir = Join-Path $dataDir "stats"
$utf8NoBom = [Text.UTF8Encoding]::new($false)

function Write-JsonFile {
    param([string]$Path, [object]$Data)
    $json = $Data | ConvertTo-Json -Depth 20 -Compress:$false
    [IO.File]::WriteAllText($Path, $json, $utf8NoBom)
}
function Read-JsonFile {
    param([string]$Path)
    $text = [IO.File]::ReadAllText($Path, $utf8NoBom)
    return $text | ConvertFrom-Json -Depth 20
}

$jkcstatPath = Join-Path $statsDir "jkcstat_20260923.json"
$jkc = Read-JsonFile $jkcstatPath

$tipsByRace = @{}
1..9 | ForEach-Object { $tipsByRace["race_$_"] = @{} }
$detailByRace = @{}
1..9 | ForEach-Object { $detailByRace["race_$_"] = @() }

$expertData = [ordered]@{
    "卡洛斯" = @(
        @{race=7;h=1;n="東來欣賞";r=1},@{race=7;h=8;n="首飾悟空";r=2},@{race=7;h=12;n="丞匡掠影";r=3},@{race=7;h=4;n="競駿皇者";r=4},
        @{race=8;h=8;n="繼往開來";r=1},@{race=8;h=1;n="人和家興";r=2},@{race=8;h=4;n="久久為昇";r=3},@{race=8;h=11;n="驕陽雄心";r=4}
    )
    "匡公" = @(
        @{race=7;h=12;n="丞匡掠影";r=1},@{race=7;h=1;n="東來欣賞";r=2},@{race=7;h=8;n="首飾悟空";r=3},@{race=7;h=11;n="盈妍威楓";r=4},
        @{race=8;h=8;n="繼往開來";r=1},@{race=8;h=11;n="驕陽雄心";r=2},@{race=8;h=6;n="富國兄弟";r=3},@{race=8;h=4;n="久久為昇";r=4}
    )
    "金駒" = @(
        @{race=4;h=9;n="將傲";r=1},@{race=4;h=6;n="快樂神駒";r=2},@{race=4;h=11;n="焦點";r=3},@{race=4;h=4;n="星辰千帥";r=4},
        @{race=7;h=3;n="天星";r=1},@{race=7;h=11;n="盈妍威楓";r=2},@{race=7;h=10;n="正極";r=3},@{race=7;h=8;n="首飾悟空";r=4}
    )
    "西門獨" = @(
        @{race=5;h=6;n="越駿聯歡";r=1},@{race=5;h=5;n="創科群英";r=2},@{race=5;h=3;n="大學生";r=3},@{race=5;h=1;n="本領非凡";r=4},
        @{race=8;h=9;n="蓮冠皇";r=1},@{race=8;h=4;n="久久為昇";r=2},@{race=8;h=8;n="繼往開來";r=3},@{race=8;h=2;n="團結勇士";r=4}
    )
    "諸葛數" = @(
        @{race=2;h=4;n="馬馳登";r=1},@{race=2;h=1;n="紅愛舍";r=2},@{race=2;h=3;n="路路勁";r=3},@{race=2;h=5;n="飛輪霸";r=4},
        @{race=6;h=1;n="福進";r=1},@{race=6;h=4;n="巴閉王";r=2},@{race=6;h=3;n="藍地球";r=3},@{race=6;h=5;n="佐治傳奇";r=4}
    )
    "長風" = @(
        @{race=4;h=6;n="快樂神駒";r=1},@{race=4;h=4;n="星辰千帥";r=2},@{race=4;h=9;n="將傲";r=3},@{race=4;h=3;n="應龍飛影";r=4},
        @{race=7;h=1;n="東來欣賞";r=1},@{race=7;h=8;n="首飾悟空";r=2},@{race=7;h=3;n="天星";r=3},@{race=7;h=11;n="盈妍威楓";r=4}
    )
    "陳志懷" = @(
        @{race=4;h=3;n="應龍飛影";r=1},@{race=4;h=6;n="快樂神駒";r=2},@{race=4;h=9;n="將傲";r=3},@{race=4;h=2;n="智勝一籌";r=4},
        @{race=7;h=3;n="天星";r=1},@{race=7;h=2;n="乘數表";r=2},@{race=7;h=1;n="東來欣賞";r=3},@{race=7;h=8;n="首飾悟空";r=4}
    )
    "明治朗" = @(
        @{race=1;h=11;n="東方魅影";r=1},@{race=1;h=8;n="電訊驕陽";r=2},@{race=1;h=3;n="神駒馬靈";r=3},@{race=1;h=6;n="開心三多";r=4},
        @{race=3;h=12;n="得意佳作";r=1},@{race=3;h=2;n="贏玥";r=2},@{race=3;h=5;n="凝妙星";r=3},@{race=3;h=7;n="有情有義";r=4}
    )
    "內幕料" = @(
        @{race=1;h=3;n="神駒馬靈";r=1},@{race=1;h=6;n="開心三多";r=2},@{race=1;h=8;n="電訊驕陽";r=3},@{race=1;h=11;n="東方魅影";r=4},
        @{race=8;h=2;n="團結勇士";r=1},@{race=8;h=3;n="富心星";r=2},@{race=8;h=8;n="繼往開來";r=3},@{race=8;h=9;n="蓮冠皇";r=4}
    )
    "網中神" = @(
        @{race=3;h=2;n="贏玥";r=1},@{race=3;h=5;n="凝妙星";r=2},@{race=3;h=6;n="領航天子";r=3},@{race=3;h=7;n="有情有義";r=4},
        @{race=7;h=1;n="東來欣賞";r=1},@{race=7;h=3;n="天星";r=2},@{race=7;h=8;n="首飾悟空";r=3},@{race=7;h=11;n="盈妍威楓";r=4}
    )
    "洛飛" = @(
        @{race=4;h=1;n="沙井之友";r=1},@{race=4;h=3;n="應龍飛影";r=2},@{race=4;h=4;n="星辰千帥";r=3},@{race=4;h=6;n="快樂神駒";r=4},
        @{race=9;h=2;n="紫荊傳令";r=1},@{race=9;h=6;n="將義";r=2},@{race=9;h=8;n="豐辰";r=3},@{race=9;h=9;n="中國心";r=4}
    )
}

$totalTips = 0
foreach ($expert in $expertData.Keys) {
    foreach ($t in $expertData[$expert]) {
        $rk = "race_$($t.race)"
        $hno = [int]$t.h
        $detailByRace[$rk] += [ordered]@{
            expert = $expert
            horse_no = $hno
            name = $t.n
            rank = [int]$t.r
        }
        if (-not $tipsByRace[$rk].ContainsKey($hno)) {
            $tipsByRace[$rk][$hno] = [ordered]@{
                horse_no = $hno
                name = $t.n
                count = 0
                experts = @()
            }
        }
        $tipsByRace[$rk][$hno].count = [int]$tipsByRace[$rk][$hno].count + 1
        $tipsByRace[$rk][$hno].experts += $expert
        $totalTips++
    }
}

$cc_expert_tips = [ordered]@{}
$cc_hot_horses = [ordered]@{}
$allHot = @()
foreach ($rk in $tipsByRace.Keys) {
    $cc_expert_tips[$rk] = @()
    foreach ($hno in $tipsByRace[$rk].Keys | Sort-Object { [int]$_ }) {
        $entry = $tipsByRace[$rk][$hno]
        $sortedExperts = @($entry.experts)
        $cc_expert_tips[$rk] += [ordered]@{
            horse_no = [int]$entry.horse_no
            name = $entry.name
            count = [int]$entry.count
            experts = $sortedExperts
        }
        $allHot += [ordered]@{
            race_no = [int]($rk -replace 'race_','')
            horse_no = [int]$entry.horse_no
            name = $entry.name
            count = [int]$entry.count
            experts = $sortedExperts
        }
    }
    $sortedRace = @($cc_expert_tips[$rk] | Sort-Object count -Descending)
    $cc_hot_horses[$rk] = $sortedRace
}
$cc_hot_horses["top_global"] = @($allHot | Sort-Object count,race_no -Descending | Select-Object -First 30)
$cc_expert_tips_detail = [ordered]@{}
foreach ($rk in $detailByRace.Keys) { $cc_expert_tips_detail[$rk] = $detailByRace[$rk] }

$barrierR1 = @(
    @{horse_no=1;name="堅多福";name_oncc="堅多福";gear_symbols="▼＋";equipment="—";draw=12;jockey="何澤堯";weight_lbs=135;weight_change=19;trainer_surname="柏";rating_cc=40;rating_change=-1;age=5;body_weight_lbs=1225;body_weight_change=16},
    @{horse_no=2;name="一風雲";name_oncc="一風雲";gear_symbols="▼＋";equipment="BT";draw=5;jockey="金誠剛";weight_lbs=134;weight_change=15;trainer_surname="丁";rating_cc=39;rating_change=-2;age=5;body_weight_lbs=1264;body_weight_change=-1},
    @{horse_no=3;name="神駒馬靈";name_oncc="神駒馬靈";gear_symbols="＊";equipment="SW-B1";draw=4;jockey="霍宏聲";weight_lbs=132;weight_change=-1;trainer_surname="廖";rating_cc=37;rating_change=-1;age=6;body_weight_lbs=1121;body_weight_change=6},
    @{horse_no=4;name="紅磚戰士";name_oncc="紅磚戰士";gear_symbols="＋";equipment="N1";draw=1;jockey="周俊樂";weight_lbs=129;weight_change=-6;trainer_surname="游";rating_cc=36;rating_change=-4;age=5;body_weight_lbs=1110;body_weight_change=-7},
    @{horse_no=5;name="極速滿貫";name_oncc="極速滿貫";gear_symbols="＋";equipment="—";draw=10;jockey="奧爾民";weight_lbs=130;weight_change=-3;trainer_surname="黎";rating_cc=35;rating_change=-3;age=8;body_weight_lbs=1039;body_weight_change=-10},
    @{horse_no=6;name="開心三多";name_oncc="開心三多";gear_symbols="＋";equipment="HX";draw=11;jockey="希威森";weight_lbs=128;weight_change=0;trainer_surname="桂";rating_cc=33;rating_change=0;age=7;body_weight_lbs=1029;body_weight_change=-5},
    @{horse_no=7;name="綫路達飛";name_oncc="?路達飛";gear_symbols="#＋";equipment="V-C1";draw=6;jockey="楊明綸";weight_lbs=127;weight_change=-6;trainer_surname="賢";rating_cc=32;rating_change=-6;age=6;body_weight_lbs=1105;body_weight_change=-11},
    @{horse_no=8;name="電訊驕陽";name_oncc="電訊驕陽";gear_symbols="＊";equipment="V";draw=8;jockey="袁幸堯";weight_lbs=115;weight_change=-10;trainer_surname="徐";rating_cc=30;rating_change=0;age=6;body_weight_lbs=1063;body_weight_change=15},
    @{horse_no=9;name="至高心得";name_oncc="至高心得";gear_symbols="＋";equipment="NT";draw=2;jockey="梁家俊";weight_lbs=123;weight_change=-8;trainer_surname="韋";rating_cc=28;rating_change=-7;age=5;body_weight_lbs=1019;body_weight_change=-4},
    @{horse_no=10;name="威威父子";name_oncc="威威父子";gear_symbols="＋";equipment="V-";draw=7;jockey="田泰安";weight_lbs=120;weight_change=-6;trainer_surname="巫";rating_cc=25;rating_change=-4;age=7;body_weight_lbs=1012;body_weight_change=23},
    @{horse_no=11;name="東方魅影";name_oncc="東方魅影";gear_symbols="＋";equipment="BT";draw=3;jockey="潘頓";weight_lbs=119;weight_change=0;trainer_surname="希";rating_cc=24;rating_change=0;age=6;body_weight_lbs=1064;body_weight_change=-12},
    @{horse_no=12;name="幸運同行";name_oncc="幸運同行";gear_symbols="★＊";equipment="B";draw=9;jockey="艾兆禮";weight_lbs=118;weight_change=-2;trainer_surname="蔡";rating_cc=23;rating_change=-2;age=7;body_weight_lbs=1012;body_weight_change=-4}
)

$cc_barrier = [ordered]@{ "race_1" = $barrierR1 }

$trackworkR1 = @(
    @{horse_no=1;name="堅多福";trainer_surname="柏";weight_lbs=135;trackwork_summary="距上賽17日，賽後2日(9月8日)復課，踱步13課，快跳1課，泥閘0課，草閘0課，彈閘0課，游水5次。";trackwork_daily=[ordered]@{"7-9"="助HX（飛機場踱步）";"10-13"="助PH（內快踱兩圈）（從化）";"14-16"="助PH（內快踱兩圈）游2（從化）";"17-20"="助50.5PH草地 27.0 23.5游3（從化）";"21-21"="助PH（內倒快兩圈）（從化）";"22-22"="—"}},
    @{horse_no=2;name="一風雲";trainer_surname="丁";weight_lbs=134;trackwork_summary="距上賽7日，賽後4日(9月20日)復課，踱步3課，快跳0課，泥閘0課，草閘0課，彈閘0課，游水3次。";trackwork_daily=[ordered]@{"7-9"="助58.7SWH";"10-13"="助50.1玄宇宙游4 26.3 23.8B草閘";"14-16"="出賽谷B好地1800剛 12駒第11-10 3/4BT";"17-20"="助H（飛機場踱步）游2";"21-21"="助H（彭福公園踱）游1";"22-22"="助H（內快踱一圈）"}},
    @{horse_no=3;name="神駒馬靈";trainer_surname="廖";weight_lbs=132;trackwork_summary="距上賽17日，賽後2日(9月8日)復課，踱步13課，快跳2課，泥閘0課，草閘0課，彈閘0課，游水12次。";trackwork_daily=[ordered]@{"7-9"="跑步機踱步（上斜）";"10-13"="助H（內快踱一圈）游2（從化）";"14-16"="助1.21.7高高至高游3 29.8 27.9 24.0草地（從化）";"17-20"="助1.24.2康昌之星 32.7 27.9 23.6H游4";"21-21"="助H（內倒快一圈）游1";"22-22"="助H（內快踱一圈）"}},
    @{horse_no=4;name="紅磚戰士";trainer_surname="游";weight_lbs=129;trackwork_summary="7月23日從化開操，踱步51課，快跳4課，泥閘0課，草閘2課，彈閘1課，游水36次。";trackwork_daily=[ordered]@{"7-9"="副1200從草1.10.89";"10-13"="助HN（內倒快兩圈）游3（從化）";"14-16"="助HN（內快踱一圈）";"17-20"="助53.0N 29.3 23.7";"21-21"="助（千八教閘）N";"22-22"="助HN（內快踱一圈）"}},
    @{horse_no=5;name="極速滿貫";trainer_surname="黎";weight_lbs=130;trackwork_summary="7月27日開操，踱步42課，快跳9課，泥閘1課，草閘1課，彈閘0課，游水43次。";trackwork_daily=[ordered]@{"7-9"="跑步機慢跑（上斜）";"10-13"="助59.8游4 33.3 26.5";"14-16"="民1200泥閘1.12.09 7駒7 5 5-8 1/4游2";"17-20"="助26.2 26.2游4";"21-21"="助（內倒快一圈）游1";"22-22"="助（內快踱一圈）"}},
    @{horse_no=6;name="開心三多";trainer_surname="桂";weight_lbs=128;trackwork_summary="距上賽17日，賽後1日(9月7日)復課，踱步13課，快跳3課，泥閘0課，草閘0課，彈閘0課，游水13次。";trackwork_daily=[ordered]@{"7-9"="助HX（內快踱一圈）";"10-13"="助54.2HX游4 27.8 26.4";"14-16"="森53.4HX游3 29.0 24.4";"17-20"="森1.22.7HX游3 30.5 28.4 23.8";"21-21"="助HX（內倒快兩圈）游1";"22-22"="助HX（內快踱一圈）"}},
    @{horse_no=7;name="綫路達飛";trainer_surname="賢";weight_lbs=127;trackwork_summary="7月24日從化開操，踱步45課，快跳10課，泥閘1課，草閘1課，彈閘0課，游水32次。";trackwork_daily=[ordered]@{"7-9"="助H（內倒快兩圈）";"10-13"="助57.9H游4 31.1 26.8（從化）";"14-16"="助1.26.4H游3 33.4 27.7 25.3（從化）";"17-20"="助53.1H游4 28.5 24.6（從化）";"21-21"="助H（內倒快兩圈）游1（從化）";"22-22"="助（內快踱一圈）"}},
    @{horse_no=8;name="電訊驕陽";trainer_surname="徐";weight_lbs=115;trackwork_summary="距上賽14日，賽後3日(9月12日)復課，踱步8課，快跳1課，泥閘0課，草閘0課，彈閘0課，游水7次。";trackwork_daily=[ordered]@{"7-9"="出賽谷A好地1200班";"10-13"="助H（內快踱一圈）游2";"14-16"="助H（內快踱兩圈）游2";"17-20"="助1.01.1H 33.8 27.3游3";"21-21"="助H（飛機場踱步）";"22-22"="助H（內快踱一圈）"}},
    @{horse_no=9;name="至高心得";trainer_surname="韋";weight_lbs=123;trackwork_summary="7月29日從化開操，踱步41課，快跳7課，泥閘0課，草閘1課，彈閘0課，游水51次。";trackwork_daily=[ordered]@{"7-9"="紹1600從草1.39.02";"10-13"="助57.1HNX 32.2 24.9游4（從化）";"14-16"="助HN（內快踱一圈）游3（從化）";"17-20"="助52.0NX游4 28.7 23.3（從化）";"21-21"="助PHNX（內倒快一圈）游1";"22-22"="助PHNX（內快踱一圈）"}},
    @{horse_no=10;name="威威父子";trainer_surname="巫";weight_lbs=120;trackwork_summary="8月1日開操，踱步39課，快跳7課，泥閘1課，草閘0課，彈閘0課，游水45次。";trackwork_daily=[ordered]@{"7-9"="班1050泥閘1.02.28";"10-13"="助H（內快踱一圈）游4";"14-16"="助29.4H 29.4游3";"17-20"="助27.1加州本事 27.1H游4";"21-21"="助H（內倒快一圈）游1";"22-22"="助H（內快踱一圈）"}},
    @{horse_no=11;name="東方魅影";trainer_surname="希";weight_lbs=119;trackwork_summary="距上賽14日，賽後4日(9月13日)從化復課，踱步7課，快跳2課，泥閘0課，草閘0課，彈閘0課，游水10次。";trackwork_daily=[ordered]@{"7-9"="出賽谷A好地1200班";"10-13"="助H（內快踱一圈）游2（從化）";"14-16"="助1.23.1H游3 29.0 28.5 25.6（從化）";"17-20"="助24.8天外富天 24.8H游4（從化）";"21-21"="助H（外快踱一圈）游1";"22-22"="助BH（內快踱一圈）"}},
    @{horse_no=12;name="幸運同行";trainer_surname="蔡";weight_lbs=118;trackwork_summary="距上賽17日，賽後4日(9月10日)復課，踱步10課，快跳3課，泥閘0課，草閘0課，彈閘0課，游水14次。";trackwork_daily=[ordered]@{"7-9"="游2";"10-13"="助CH（內快踱一圈）游4";"14-16"="助55.6CH游3 29.7 25.9";"17-20"="助56.3綠色最威 30.7 25.6CH游4";"21-21"="助CH（內倒快一圈）游1";"22-22"="助CH（內快踱一圈）"}}
)

$cc_trackwork = [ordered]@{ "race_1" = $trackworkR1 }

$jkc | Add-Member -NotePropertyName "cc_expert_tips" -NotePropertyValue $cc_expert_tips -Force
$jkc | Add-Member -NotePropertyName "cc_expert_tips_detail" -NotePropertyValue $cc_expert_tips_detail -Force
$jkc | Add-Member -NotePropertyName "cc_hot_horses" -NotePropertyValue $cc_hot_horses -Force
$jkc | Add-Member -NotePropertyName "cc_barrier" -NotePropertyValue $cc_barrier -Force
$jkc | Add-Member -NotePropertyName "cc_trackwork" -NotePropertyValue $cc_trackwork -Force
$jkc | Add-Member -NotePropertyName "cc_sources" -NotePropertyValue ([ordered]@{
    expert_fav_page = "https://racing.on.cc/racing/fav/current/rjfavg0001x0.html"
    barrier_race_1_page = "https://racing.on.cc/racing/ifo/current/rjifoa0001x0.html"
    trackwork_morning_page = "https://racing.on.cc/racing/mor/current/rjmorc0001x0.html"
    expert_count = 11
    expert_names = @("卡洛斯","匡公","金駒","西門獨","諸葛數","長風","陳志懷","明治朗","內幕料","網中神","洛飛")
    total_tips_analyzed = $totalTips
    merge_key_rule = "Primary: (race_no + horse_no); Secondary: name cross-validate only"
}) -Force
$jkc.meta.note = "JKC 騎師/練馬師榜 + racing.on.cc 3大核心：最後來料(11名家88 tips) + R1排位表(12匹) + R1晨操摘要(12匹)；merge cc_* 欄位入 CURRENT race JSON"
$jkc.meta.cc_fetch_time = (Get-Date -Format "yyyy-MM-dd HH:mm:ss")

Write-JsonFile $jkcstatPath $jkc
Write-Host "[POPULATE JKCSTAT] Success!" -ForegroundColor Green
Write-Host "[POPULATE JKCSTAT]   Expert tips: $totalTips total, Races covered: $(($cc_expert_tips.Keys|?{$cc_expert_tips[$_].Count -gt 0}).Count)"
Write-Host "[POPULATE JKCSTAT]   Barrier: R1=$($cc_barrier.race_1.Count) horses"
Write-Host "[POPULATE JKCSTAT]   Trackwork: R1=$($cc_trackwork.race_1.Count) horses"
Write-Host ""
Write-Host "[POPULATE JKCSTAT] Running _merge_cc_stats.ps1..."
& "$rootDir\_merge_cc_stats.ps1"
