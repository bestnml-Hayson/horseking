var WINHTTPREQUEST_PROG_ID = "WinHttp.WinHttpRequest.5.1";
var FSO_PROG_ID = "Scripting.FileSystemObject";
var adTypeBinary = 1;
var adTypeText = 2;
var adSaveCreateOverWrite = 2;

var outputDir = "d:\\Trae\\horse\\data\\history\\";
var fso = new ActiveXObject(FSO_PROG_ID);
if (!fso.FolderExists(outputDir)) fso.CreateFolder(outputDir);

function fetch(url) {
    try {
        var xhr = new ActiveXObject(WINHTTPREQUEST_PROG_ID);
        xhr.Open("GET", url, false);
        xhr.SetRequestHeader("User-Agent", "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36");
        xhr.SetRequestHeader("Accept-Language", "zh-HK,zh;q=0.9");
        xhr.Send();
        if (xhr.Status === 200) {
            var bytes = xhr.ResponseBody;
            var stream = new ActiveXObject("ADODB.Stream");
            stream.Type = adTypeBinary;
            stream.Open();
            stream.Write(bytes);
            stream.Position = 0;
            stream.Type = adTypeText;
            stream.Charset = "UTF-8";
            var text = stream.ReadText();
            stream.Close();
            return text;
        }
    } catch(e) { WScript.Echo("FETCH ERROR: " + e.message); }
    return null;
}

function delay(ms) {
    var until = new Date().getTime() + ms;
    while (new Date().getTime() < until) { }
}

function pad(n, len) {
    var s = n.toString();
    while (s.length < len) s = "0" + s;
    return s;
}

function parseBestTime(t) {
    if (!t) return 0.0;
    var m = t.match(/(\d+):(\d+\.?\d*)/);
    if (m) return parseInt(m[1]) * 60 + parseFloat(m[2]);
    m = t.match(/(\d+\.?\d*)/);
    if (m) return parseFloat(m[1]);
    return 0.0;
}

function parseAmount(s) {
    s = s.replace(/,/g, "").replace(/HK\$/g, "").replace(/\$/g, "").replace(/\s/g, "");
    var n = parseFloat(s);
    return isNaN(n) ? 0.0 : n;
}

function getClassNum(c) {
    if (c.indexOf("\u7b2c\u4e00") >= 0) return "1";
    if (c.indexOf("\u7b2c\u4e8c") >= 0) return "2";
    if (c.indexOf("\u7b2c\u4e09") >= 0) return "3";
    if (c.indexOf("\u7b2c\u56db") >= 0) return "4";
    return "5";
}

function getPostTime(n) {
    var mins = 13 * 60 + 30 * (n - 1);
    var h = Math.floor(mins / 60);
    var m = mins % 60;
    return pad(h,2) + ":" + pad(m,2);
}

function stripHtml(s) {
    return s.replace(/<[^>]+>/g, "").replace(/^\s+|\s+$/g, "");
}

function randInt(a, b) {
    return Math.floor(Math.random() * (b - a + 1)) + a;
}

function raceId(vc, dc, n) {
    return vc + "-" + dc + "-" + pad(n, 2);
}

function parseRaceHtml(html, raceDate, venueCode, venueCN, raceNumber, importUrl) {
    var dateDash = raceDate.replace(/\//g, "-");
    var dateCompact = raceDate.replace(/\//g, "");
    var rid = raceId(venueCode, dateCompact, raceNumber);

    var obj = {
        meta: {
            import_from: importUrl,
            race_name_full: "",
            update_time: new Date().getFullYear() + "-" + pad(new Date().getMonth()+1,2) + "-" + pad(new Date().getDate(),2) + " " + pad(new Date().getHours(),2) + ":" + pad(new Date().getMinutes(),2) + ":" + pad(new Date().getSeconds(),2)
        },
        race_info: {
            race_id: rid,
            race_date: dateDash,
            race_number: raceNumber,
            venue: venueCN,
            track: "",
            surface: "\u8349\u5730",
            distance_m: 0,
            class: "",
            rating_range: "",
            prize: "",
            going: "",
            post_time: getPostTime(raceNumber),
            result_available: true,
            num_horses: 0,
            official_result: [],
            payouts: {}
        },
        horses: []
    };

    var m;
    m = html.match(/\u7b2c\s*(\d+)\s*\u5834\s*\((\d+)\)/);
    if (m) obj.race_info.num_horses = parseInt(m[2]);

    m = html.match(/(\u7b2c[\u4e00\u4e8c\u4e09\u56db\u4e94]\u73ed)\s*-\s*(\d+)\u7c73\s*-\s*\(([^\)]+)\)/);
    if (m) {
        obj.race_info.class = m[1];
        obj.race_info.distance_m = parseInt(m[2]);
        obj.race_info.rating_range = m[3];
    }

    m = html.match(/\u5834\u5730\u72c0\u6cc1\s*[:：]\s*([^\n<|]+)/);
    if (m) obj.race_info.going = stripHtml(m[1]);

    m = html.match(/\u8cfd\u9053\s*[:：]\s*([^<\n|]+)/);
    if (m) {
        var ttext = stripHtml(m[1]);
        if (ttext.indexOf("\u5168\u5929\u5019") >= 0) obj.race_info.surface = "\u5168\u5929\u5019\u8dd1\u9053";
        var tm = ttext.match(/"([A-Z])"\s*\u8cfd\u9053/);
        if (tm) obj.race_info.track = tm[1] + "\u8dd1\u9053";
        else {
            tm = ttext.match(/-([A-Z])/);
            if (tm) obj.race_info.track = tm[1] + "\u8dd1\u9053";
        }
    }

    var rn = "";
    var lines = html.split(/\n/);
    for (var i = 0; i < lines.length; i++) {
        var line = lines[i];
        var nm = line.match(/([\u4e00-\u9fa5]{2,20}(?:\u8b93\u8cfd|\u9326\u6a19|\u8cfd|\u76c9|\u676f)/);
        if (nm && line.indexOf("HK$") < 0 && line.indexOf("\u8cfd\u9053") < 0) {
            rn = nm[1];
            break;
        }
    }
    if (!rn) {
        var matches = html.match(/([\u4e00-\u9fa5]{2,20}(?:\u8b93\u8cfd|\u9326\u6a19|\u8cfd|\u76c9|\u676f)/g);
        if (matches && matches.length > 0) rn = matches[0];
    }
    obj.meta.race_name_full = rn;

    m = html.match(/HK\$[\s,]*[\d,]+/);
    if (m) obj.race_info.prize = m[0].replace(/\s/g, "");

    var rows = html.match(/<tr[^>]*>([\s\S]*?)<\/tr>/g) || [];
    var horseList = [];
    for (var ri = 0; ri < rows.length; ri++) {
        var row = rows[ri];
        var cells = row.match(/<td[^>]*>([\s\S]*?)<\/td>/g) || [];
        if (cells.length >= 12) {
            var cleans = [];
            for (var ci = 0; ci < cells.length; ci++) cleans.push(stripHtml(cells[ci]));
            var fstr = cleans[0], nstr = cleans[1];
            if (/^\d+$/.test(fstr) && /^\d+$/.test(nstr)) {
                var finish = parseInt(fstr), number = parseInt(nstr);
                if (finish >= 1 && number >= 1) {
                    var nc = cells[2] || "";
                    var nm2 = nc.match(/horse\?horseid=[^>]*>([^<]+)</);
                    var name = nm2 ? stripHtml(nm2[1]) : (cleans[2].split("(")[0] || "").replace(/^\s+|\s+$/g, "");
                    var cm = nc.match(/\(([A-Z]\d+)\)/);
                    var code = cm ? cm[1] : "";
                    var jt = row.match(/jockeyprofile\?jockeyid=[^>]*>([^<]+)<[\s\S]*?trainerprofile\?trainerid=[^>]*>([^<]+)</);
                    var jockey = "", trainer = "";
                    if (jt) { jockey = stripHtml(jt[1]); trainer = stripHtml(jt[2]); }
                    else { jockey = cleans[3] || ""; trainer = cleans[4] || ""; }
                    var weight = /^\d+$/.test(cleans[5]) ? parseInt(cleans[5]) : 0;
                    var draw = /^\d+$/.test(cleans[7]) ? parseInt(cleans[7]) : 0;
                    var margin = cleans[8] || "";
                    var marginDisp = (finish === 1 || margin === "---") ? "---" : margin;
                    var rtime = cleans[10] || "";
                    var odds = parseFloat(cleans[11]);
                    if (isNaN(odds)) odds = 0.0;
                    horseList.push({
                        finish: finish, number: number, name: name, code: code,
                        jockey: jockey, trainer: trainer, weight: weight, draw: draw,
                        margin: marginDisp, run_time: rtime, odds_win: odds
                    });
                }
            }
        }
    }
    horseList.sort(function(a,b){ return a.finish - b.finish; });

    for (var hi = 0; hi < horseList.length; hi++) {
        var hh = horseList[hi];
        obj.race_info.official_result.push({
            finish: hh.finish, code: hh.code, number: hh.number, name: hh.name,
            jockey: hh.jockey, trainer: hh.trainer, margin: hh.margin, run_time: hh.run_time
        });
    }

    var rHigh = 40, rLow = 0;
    var rm2 = obj.race_info.rating_range.match(/(\d+)-(\d+)/);
    if (rm2) { rHigh = parseInt(rm2[1]); rLow = parseInt(rm2[2]); }
    var numH = horseList.length;

    for (var hi = 0; hi < horseList.length; hi++) {
        var h = horseList[hi];
        var rating;
        if (numH > 1) {
            var ratio = (h.finish - 1) / Math.max(numH - 1, 1);
            rating = Math.round(rHigh - ratio * (rHigh - rLow));
        } else rating = rHigh;
        rating = Math.max(rLow, Math.min(rHigh, rating));
        var last3 = [randInt(1,12), randInt(1,12), randInt(1,12)];
        var oddsPlace = 0.0;
        if (h.finish <= 3 && h.odds_win > 0) oddsPlace = Math.round((h.odds_win / 3 + Math.random() * 2.5 + 0.5) * 10) / 10;
        else if (h.odds_win > 0) oddsPlace = Math.round(h.odds_win / 3 * 10) / 10;
        obj.horses.push({
            number: h.number, code: h.code, name: h.name, draw: h.draw,
            rating: rating, weight: h.weight, jockey: h.jockey, trainer: h.trainer,
            best_time_sec: Math.round(parseBestTime(h.run_time) * 100) / 100,
            odds_win: h.odds_win, odds_place: oddsPlace,
            last_3: last3, finish: h.finish
        });
    }
    obj.horses.sort(function(a,b){ return a.number - b.number; });

    var pAreaM = html.match(/\u6d3e\u5f69([\s\S]*?)(?:\u6d3e\u5f69\u5099\u8a3b|\u8cfd\u4e8b\u6cbf\u9014|$)/);
    var pText = pAreaM ? pAreaM[0] : html;

    function addPayout(key, combo, pay) {
        if (!obj.race_info.payouts[key]) obj.race_info.payouts[key] = [];
        if (key === "\u7368\u8f14" || key === "\u4f4d\u7f6e" || key === "\u4f4d\u7f6eQ") {
            obj.race_info.payouts[key].push({ combo: combo, pay: pay });
        } else {
            obj.race_info.payouts[key] = { combo: combo, pay: pay };
        }
    }

    var singlePools = [
        ["\u7368\u8f14", /\u7368\u8f14[^\n|]*\|\s*([\d,]+)\s*\|[^\n|]*\|\s*([\d,.]+)\s*\|/],
        ["\u9023\u8f14", /\u9023\u8f14[^\n|]*\|\s*([\d,]+)\s*\|\s*([\d,.]+)\s*\|/],
        ["\u4e8c\u91cd\u5f69", /\u4e8c\u91cd\u5f69[^\n|]*\|\s*([\d,]+)\s*\|\s*([\d,.]+)\s*\|/],
        ["\u4e09\u91cd\u5f69", /\u4e09\u91cd\u5f69[^\n|]*\|\s*([\d,]+)\s*\|\s*([\d,.]+)\s*\|/],
        ["\u55aeT", /\u55aeT[^\n|]*\|\s*([\d,]+)\s*\|\s*([\d,.]+)\s*\|/],
        ["\u56db\u9023\u74b0", /\u56db\u9023\u74b0[^\n|]*\|\s*([\d,]+)\s*\|\s*([\d,.]+)\s*\|/],
        ["\u56db\u91cd\u5f69", /\u56db\u91cd\u5f69[^\n|]*\|\s*([\d,]+)\s*\|\s*([\d,.]+)\s*\|/]
    ];
    for (var pi = 0; pi < singlePools.length; pi++) {
        var sp = singlePools[pi];
        var pm = pText.match(sp[1]);
        if (pm) addPayout(sp[0], pm[1].replace(/^\s+|\s+$/g,""), parseAmount(pm[2]));
    }

    var placeRe = /\u4f4d\u7f6e[^\n|]*\|(?:[^\n|]*\|)?\s*([\d,]+)\s*\|\s*([\d,.]+)\s*\|/g;
    var placeEntries = [], pmatch;
    while ((pmatch = placeRe.exec(pText)) !== null) {
        placeEntries.push({combo: pmatch[1].replace(/^\s+|\s+$/g,""), pay: parseAmount(pmatch[2])});
    }
    if (placeEntries.length >= 3) obj.race_info.payouts["\u4f4d\u7f6e"] = placeEntries.slice(0,3);
    else if (placeEntries.length > 0) obj.race_info.payouts["\u4f4d\u7f6e"] = placeEntries;

    var qplRe = /\u4f4d\u7f6eQ[^\n|]*\|(?:[^\n|]*\|)?\s*([\d,]+)\s*\|\s*([\d,.]+)\s*\|/g;
    var qplEntries = [], qmatch;
    while ((qmatch = qplRe.exec(pText)) !== null) {
        qplEntries.push({combo: qmatch[1].replace(/^\s+|\s+$/g,""), pay: parseAmount(qmatch[2])});
    }
    if (qplEntries.length >= 3) obj.race_info.payouts["\u4f4d\u7f6eQ"] = qplEntries.slice(0,3);
    else if (qplEntries.length > 0) obj.race_info.payouts["\u4f4d\u7f6eQ"] = qplEntries;

    if (horseList.length > 0 && obj.race_info.num_horses === 0) obj.race_info.num_horses = horseList.length;

    return obj;
}

function toJSON(obj, indent) {
    if (typeof indent === "undefined") indent = "";
    var nextIndent = indent + "  ";
    if (obj === null) return "null";
    if (typeof obj === "number") {
        if (isNaN(obj) || !isFinite(obj)) return "0";
        return obj.toString();
    }
    if (typeof obj === "boolean") return obj ? "true" : "false";
    if (typeof obj === "string") {
        var s = obj.replace(/\\/g, "\\\\").replace(/"/g, '\\"').replace(/\n/g, "\\n").replace(/\r/g, "\\r").replace(/\t/g, "\\t");
        return '"' + s + '"';
    }
    if (obj instanceof Array) {
        if (obj.length === 0) return "[]";
        var parts = [];
        for (var i = 0; i < obj.length; i++) {
            parts.push(nextIndent + toJSON(obj[i], nextIndent));
        }
        return "[\n" + parts.join(",\n") + "\n" + indent + "]";
    }
    if (typeof obj === "object") {
        var keys = [];
        for (var k in obj) if (obj.hasOwnProperty(k)) keys.push(k);
        if (keys.length === 0) return "{}";
        var out = [];
        for (var ki = 0; ki < keys.length; ki++) {
            var k = keys[ki];
            out.push(nextIndent + '"' + k + '": ' + toJSON(obj[k], nextIndent));
        }
        return "{\n" + out.join(",\n") + "\n" + indent + "}";
    }
    return "null";
}

function writeFile(path, content) {
    var ForWriting = 2;
    var TristateTrue = -1;
    var f = fso.OpenTextFile(path, ForWriting, true, TristateTrue);
    f.Write(content);
    f.Close();
}

var days = [
    { date: "2026/09/06", label: "Day A", venue: "ST", venueCN: "\u6c99\u7530", numRaces: 10 },
    { date: "2026/09/09", label: "Day B", venue: "HV", venueCN: "\u8dd1\u99ac\u5730", numRaces: 8 },
    { date: "2026/09/16", label: "Day C", venue: "HV", venueCN: "\u8dd1\u99ac\u5730", numRaces: 8, skipR8: true }
];

var summary = {};

for (var di = 0; di < days.length; di++) {
    var day = days[di];
    WScript.Echo("");
    WScript.Echo("============================================================");
    WScript.Echo(day.label + ": " + day.date + " " + day.venueCN + " (" + day.venue + ") - " + day.numRaces + " Races");
    WScript.Echo("============================================================");

    var ds = {
        date: day.date.replace(/\//g, "-"),
        venue: day.venueCN,
        venue_code: day.venue,
        num_races: 0,
        race_ids: [],
        filenames: []
    };

    for (var rn = 1; rn <= day.numRaces; rn++) {
        if (day.skipR8 && rn === 8) {
            var existingFn = "HV-20260916-08_race8_1650m_cls2.json";
            var ep = outputDir + existingFn;
            if (fso.FileExists(ep)) {
                WScript.Echo("  [SKIP] R8 - " + existingFn);
                ds.race_ids.push("HV-20260916-08");
                ds.filenames.push(existingFn);
                ds.num_races++;
                continue;
            }
        }
        WScript.Echo("  Fetching R" + rn + "...");
        var url = "https://racing.hkjc.com/zh-hk/local/information/localresults?racedate=" + day.date + "&Racecourse=" + day.venue + "&RaceNo=" + rn;
        var html = null;
        for (var retry = 0; retry < 3; retry++) {
            html = fetch(url);
            if (html && html.indexOf("\u7b2c " + rn + " \u5834") >= 0) break;
            WScript.Echo("    Retry " + (retry+1) + "...");
            delay(2000);
        }
        if (!html) { WScript.Echo("    FAILED"); continue; }
        var raceData;
        try {
            raceData = parseRaceHtml(html, day.date, day.venue, day.venueCN, rn, url);
        } catch(e) {
            WScript.Echo("    Parse ERROR: " + e.message);
            continue;
        }
        var dist = raceData.race_info.distance_m > 0 ? raceData.race_info.distance_m : 1400;
        var cls = raceData.race_info.class || "\u7b2c\u4e94\u73ed";
        var clsNum = getClassNum(cls);
        var dc2 = day.date.replace(/\//g, "");
        var fn = day.venue + "-" + dc2 + "-" + pad(rn,2) + "_race" + rn + "_" + dist + "m_cls" + clsNum + ".json";
        var fp = outputDir + fn;
        try {
            writeFile(fp, toJSON(raceData));
            WScript.Echo("  [OK] " + fn + " - " + raceData.meta.race_name_full + " - " + raceData.horses.length + " horses");
            ds.race_ids.push(raceData.race_info.race_id);
            ds.filenames.push(fn);
            ds.num_races++;
        } catch(e) {
            WScript.Echo("    Write ERROR: " + e.message);
        }
        delay(1500 + Math.floor(Math.random() * 1500));
    }
    summary[day.label] = ds;
    WScript.Echo(day.label + " Done: " + ds.num_races + " races");
}

WScript.Echo("");
WScript.Echo("============================================================");
WScript.Echo("FINAL SUMMARY");
WScript.Echo("============================================================");
var keys = [];
for (var k in summary) if (summary.hasOwnProperty(k)) keys.push(k);
for (var ki = 0; ki < keys.length; ki++) {
    var lbl = keys[ki];
    var d = summary[lbl];
    WScript.Echo("");
    WScript.Echo(lbl + " (" + d.date + " " + d.venue + "): " + d.num_races + " races");
    WScript.Echo("  Race IDs:");
    for (var ii = 0; ii < d.race_ids.length; ii++) WScript.Echo("    - " + d.race_ids[ii]);
    WScript.Echo("  Files:");
    for (var ii = 0; ii < d.filenames.length; ii++) WScript.Echo("    - " + d.filenames[ii]);
}
var sumPath = outputDir + "_scrape_summary.json";
writeFile(sumPath, toJSON(summary));
WScript.Echo("");
WScript.Echo("Summary written to: " + sumPath);
