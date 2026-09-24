import json
import urllib.request

URL = "https://info.cld.hkjc.com/graphql/base/"
HEADERS = {
    "Content-Type": "application/json",
    "Accept": "*/*",
    "Accept-Language": "zh-HK,zh;q=0.9,en;q=0.8",
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
    "Referer": "https://bet.hkjc.com/",
    "Origin": "https://bet.hkjc.com",
    "sec-fetch-dest": "empty",
    "sec-fetch-mode": "cors",
    "sec-fetch-site": "same-site",
}

HORSE_ODDS = """
query racing($date: String, $venueCode: String, $oddsTypes: [OddsType], $raceNo: Int) {
  raceMeetings(date: $date, venueCode: $venueCode) {
    pmPools(oddsTypes: $oddsTypes, raceNo: $raceNo) {
      id
      status
      sellStatus
      oddsType
      lastUpdateTime
      oddsNodes {
        combString
        oddsValue
        hotFavourite
        oddsDropValue
      }
    }
  }
}
"""

MINI = """
query racing {
  activeMeetings: raceMeetings {
    id
    venueCode
    date
    status
    races { no postTime status }
  }
}
"""

WIN_ONLY = """
query raceMeetings($date: String, $venueCode: String) {
  raceMeetings(date: $date, venueCode: $venueCode) {
    id
    venueCode
    date
    races {
      no
      runners { no name_ch winOdds }
    }
  }
}
"""


def post(query, variables=None, operation=None):
    payload = {"query": query, "variables": variables or {}}
    if operation:
        payload["operationName"] = operation
    body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(URL, data=body, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=25) as r:
        raw = r.read().decode("utf-8", errors="ignore")
        data = json.loads(raw)
        errs = data.get("errors")
        print("---", operation or query[:40].replace("\n", " "), "status", r.status, "len", len(raw))
        if errs:
            print("ERR", json.dumps(errs, ensure_ascii=False)[:400])
        else:
            print("OK keys", list((data.get("data") or {}).keys()))
        return data


if __name__ == "__main__":
    post(MINI, {}, "racing")
    post(WIN_ONLY, {"date": "2026-09-23", "venueCode": "HV"}, "raceMeetings")
    post(HORSE_ODDS, {"date": "2026-09-23", "venueCode": "HV", "oddsTypes": ["WIN", "PLA"], "raceNo": 9}, "racing")
