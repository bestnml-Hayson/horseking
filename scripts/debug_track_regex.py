#!/usr/bin/env python3
"""Debug: test track_course regex extraction."""
import os
from playwright.sync_api import sync_playwright

url = "https://racing.hkjc.com/racing/information/Chinese/Racing/LocalResults.aspx?RaceDate=2026/09/27&Racecourse=ST&RaceNo=1"

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True, args=['--no-sandbox', '--disable-gpu'])
    page = browser.new_page()
    page.goto(url, wait_until='domcontentloaded', timeout=30000)
    page.wait_for_timeout(3000)

    result = page.evaluate(r'''() => {
        const text = document.body.innerText;
        const lines = text.split('\n');

        let startIdx = -1;
        for (let i = 0; i < lines.length; i++) {
            if (/第\s*\d+\s*場/.test(lines[i])) { startIdx = i; break; }
        }

        let endIdx = lines.length;
        if (startIdx >= 0) {
            for (let i = startIdx + 1; i < lines.length; i++) {
                if (lines[i].includes('馬匹編號') || lines[i].includes('排位表')) {
                    endIdx = i; break;
                }
            }
        } else {
            startIdx = 0;
        }

        const block = lines.slice(startIdx, endIdx).join(' ');

        // Test different patterns
        const patterns = [
            /賽道\s*[:：]\s*(草地|全天候跑道)/,
            /賽道\s*[:：]\s*(草地|全天候跑道| turf |all-weather)/i,
            /賽道[:：]\s*(草地|全天候跑道)/,
            /賽道.*?(草地|全天候跑道)/,
        ];

        const results = {
            startIdx,
            endIdx,
            blockLength: block.length,
            blockSample: block.substring(0, 500),
            matches: []
        };

        for (let i = 0; i < patterns.length; i++) {
            const match = block.match(patterns[i]);
            results.matches.push({
                pattern: patterns[i].toString(),
                matched: match ? match[0] : null,
                captured: match ? match[1] : null
            });
        }

        // Also search in full text
        const fullTextMatch = text.match(/賽道\s*[:：]\s*(草地|全天候跑道)/);
        results.fullTextMatch = fullTextMatch ? fullTextMatch[0] : null;

        return results;
    }''')

    browser.close()

    out_path = os.path.join(os.path.dirname(__file__), "debug_track_regex.txt")
    with open(out_path, 'w', encoding='utf-8') as f:
        f.write(f"startIdx: {result['startIdx']}\n")
        f.write(f"endIdx: {result['endIdx']}\n")
        f.write(f"blockLength: {result['blockLength']}\n")
        f.write(f"\nBlock sample (first 500 chars):\n")
        f.write(result['blockSample'])
        f.write(f"\n\nPattern matches:\n")
        for m in result['matches']:
            f.write(f"  {m['pattern']}: {m['matched']} → {m['captured']}\n")
        f.write(f"\nFull text match: {result['fullTextMatch']}\n")

    print(f"Debug output written to {out_path}")
