#!/usr/bin/env python3
"""Debug: test if 2026-09-29 has races."""
import os
from playwright.sync_api import sync_playwright

test_dates = [
    ("2026/09/29", "ST"),  # Today - Tuesday
    ("2026/09/27", "ST"),  # Sunday - should have races
    ("2026/09/26", "ST"),  # Saturday - should have races
]

out_path = os.path.join(os.path.dirname(__file__), "debug_date_check.txt")

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True, args=['--no-sandbox', '--disable-gpu'])
    page = browser.new_page()
    
    with open(out_path, 'w', encoding='utf-8') as f:
        for date_str, venue in test_dates:
            url = f"https://racing.hkjc.com/racing/information/Chinese/Racing/LocalResults.aspx?RaceDate={date_str}&Racecourse={venue}&RaceNo=1"
            f.write(f"\n{'='*60}\n")
            f.write(f"Testing: {date_str} {venue}\n")
            f.write(f"URL: {url}\n")
            f.write(f"{'='*60}\n")
            
            page.goto(url, wait_until='domcontentloaded', timeout=20000)
            page.wait_for_timeout(2000)
            
            result = page.evaluate(r'''() => {
                const text = document.body.innerText;
                const has_場地狀況 = text.includes('場地狀況');
                const has_名次 = text.includes('名次');
                const has_第場 = /第\s*\d+\s*場/.test(text);
                
                // Find the date shown on page
                const dateMatch = text.match(/賽事日期[:：]\s*(\d{2}\/\d{2}\/\d{4})/);
                
                return {
                    has_場地狀況,
                    has_名次,
                    has_第場,
                    pageDate: dateMatch ? dateMatch[1] : 'N/A',
                    textLength: text.length,
                    hasContent: has_場地狀況 || has_名次
                };
            }''')
            
            f.write(f"  Page date shown: {result['pageDate']}\n")
            f.write(f"  has '場地狀況': {result['has_場地狀況']}\n")
            f.write(f"  has '名次': {result['has_名次']}\n")
            f.write(f"  has '第X場': {result['has_第場']}\n")
            f.write(f"  hasContent (場地狀況 OR 名次): {result['hasContent']}\n")
            f.write(f"  text length: {result['textLength']}\n")
    
    browser.close()
    
    print(f"Debug output written to {out_path}")
