#!/usr/bin/env python3
"""Debug: explore HKJC horse profile page structure."""
import os
from playwright.sync_api import sync_playwright

# Test with a known horse from 2026-09-27 race
url = "https://racing.hkjc.com/racing/information/Chinese/Horse/Horse.aspx?HorseNo=K209"
out_path = os.path.join(os.path.dirname(__file__), "debug_horse_profile.txt")

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True, args=['--no-sandbox', '--disable-gpu'])
    page = browser.new_page()
    page.goto(url, wait_until='domcontentloaded', timeout=30000)
    page.wait_for_timeout(3000)

    dump = page.evaluate(r'''() => {
        const text = document.body.innerText;
        const lines = text.split('\n').map(l => l.trim()).filter(l => l);

        const result = {
            first100Lines: lines.slice(0, 100),
            horseInfoLines: [],
            careerLines: [],
            prizeLines: [],
        };

        // Find lines with horse info keywords
        for (let i = 0; i < lines.length; i++) {
            const line = lines[i];
            if (line.includes('歲') || line.includes('Age') || 
                line.includes('出賽') || line.includes('Career') ||
                line.includes('獎金') || line.includes('Prize') ||
                line.includes('冠') || line.includes('Win') ||
                line.includes('總獎金')) {
                result.horseInfoLines.push(`[${i}] ${line}`);
            }
        }

        // Look for specific patterns
        const ageMatch = text.match(/(\d+)\s*歲/);
        if (ageMatch) result.age = ageMatch[1];

        const careerMatch = text.match(/出賽[:：]?\s*(\d+)/);
        if (careerMatch) result.career_starts = careerMatch[1];

        const prizeMatch = text.match(/總獎金[:：]?\s*[$]?\s*([\d,]+)/);
        if (prizeMatch) result.total_prize = prizeMatch[1];

        return result;
    }''')

    browser.close()

    with open(out_path, 'w', encoding='utf-8') as f:
        f.write("=== First 100 lines ===\n")
        for line in dump.get('first100Lines', []):
            f.write(f"  {line}\n")

        f.write("\n=== Horse info lines ===\n")
        for line in dump.get('horseInfoLines', []):
            f.write(f"  {line}\n")

        f.write(f"\n=== Extracted fields ===\n")
        f.write(f"  Age: {dump.get('age', 'N/A')}\n")
        f.write(f"  Career starts: {dump.get('career_starts', 'N/A')}\n")
        f.write(f"  Total prize: {dump.get('total_prize', 'N/A')}\n")

    print(f"Debug output written to {out_path}")
