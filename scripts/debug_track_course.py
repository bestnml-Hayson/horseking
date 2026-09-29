#!/usr/bin/env python3
"""Debug: dump HKJC results page to find track_course information."""
import os
from playwright.sync_api import sync_playwright

url = "https://racing.hkjc.com/racing/information/Chinese/Racing/LocalResults.aspx?RaceDate=2026/09/27&Racecourse=ST&RaceNo=1"
out_path = os.path.join(os.path.dirname(__file__), "debug_track_course.txt")

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True, args=['--no-sandbox', '--disable-gpu'])
    page = browser.new_page()
    page.goto(url, wait_until='domcontentloaded', timeout=30000)
    page.wait_for_timeout(3000)

    dump = page.evaluate(r'''() => {
        const text = document.body.innerText;
        const lines = text.split('\n').map(l => l.trim()).filter(l => l);

        // Find race metadata section
        const result = {
            first50Lines: lines.slice(0, 50),
            raceInfoLines: [],
            goingLines: [],
            trackLines: [],
            courseLines: [],
        };

        for (let i = 0; i < lines.length; i++) {
            const line = lines[i];
            if (line.includes('場地') || line.includes('跑道') || line.includes('賽道') ||
                line.includes('Course') || line.includes('Track') || line.includes('Going') ||
                line.includes('配置') || line.includes('表面')) {
                result.raceInfoLines.push(`[${i}] ${line}`);
            }
            if (line.includes('好地') || line.includes('快地') || line.includes('慢地') ||
                line.includes('軟地') || line.includes('黏地') || line.includes('草地') ||
                line.includes('全天候')) {
                result.goingLines.push(`[${i}] ${line}`);
            }
        }

        // Also look for specific patterns in the full text
        const goingMatch = text.match(/場地狀況[：:]\s*(.+)/);
        if (goingMatch) result.goingStatus = goingMatch[1].trim();

        const courseMatch = text.match(/賽道[：:]\s*(.+)/);
        if (courseMatch) result.course = courseMatch[1].trim();

        const trackMatch = text.match(/跑道[：:]\s*(.+)/);
        if (trackMatch) result.track = trackMatch[1].trim();

        return result;
    }''')

    browser.close()

    with open(out_path, 'w', encoding='utf-8') as f:
        f.write("=== First 50 lines ===\n")
        for line in dump.get('first50Lines', []):
            f.write(f"  {line}\n")

        f.write("\n=== Race info lines ===\n")
        for line in dump.get('raceInfoLines', []):
            f.write(f"  {line}\n")

        f.write("\n=== Going/track lines ===\n")
        for line in dump.get('goingLines', []):
            f.write(f"  {line}\n")

        f.write(f"\n=== Extracted fields ===\n")
        f.write(f"  Going status: {dump.get('goingStatus', 'N/A')}\n")
        f.write(f"  Course: {dump.get('course', 'N/A')}\n")
        f.write(f"  Track: {dump.get('track', 'N/A')}\n")

    print(f"Debug output written to {out_path}")
