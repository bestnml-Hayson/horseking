#!/usr/bin/env python3
"""Debug: test has_content check with different wait times."""
import os
from playwright.sync_api import sync_playwright

test_url = "https://racing.hkjc.com/racing/information/Chinese/Racing/LocalResults.aspx?RaceDate=2026/09/27&Racecourse=ST&RaceNo=1"
out_path = os.path.join(os.path.dirname(__file__), "debug_has_content.txt")

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True, args=['--no-sandbox', '--disable-gpu'])
    page = browser.new_page()
    
    with open(out_path, 'w', encoding='utf-8') as f:
        f.write(f"Testing URL: {test_url}\n\n")
        
        # Test with 1.5s wait (current backfill logic)
        page.goto(test_url, wait_until='domcontentloaded', timeout=20000)
        page.wait_for_timeout(1500)
        
        has_content_1500 = page.evaluate(r'''() => {
            const text = document.body.innerText;
            return text.includes('場地狀況') || text.includes('名次');
        }''')
        
        f.write(f"has_content with 1.5s wait: {has_content_1500}\n")
        
        # Check what text is actually present
        text_check = page.evaluate(r'''() => {
            const text = document.body.innerText;
            return {
                has_場地狀況: text.includes('場地狀況'),
                has_名次: text.includes('名次'),
                has_賽道: text.includes('賽道'),
                has_跑道: text.includes('跑道'),
                textLength: text.length,
                first500chars: text.substring(0, 500)
            };
        }''')
        
        f.write(f"\nText checks with 1.5s wait:\n")
        f.write(f"  has '場地狀況': {text_check['has_場地狀況']}\n")
        f.write(f"  has '名次': {text_check['has_名次']}\n")
        f.write(f"  has '賽道': {text_check['has_賽道']}\n")
        f.write(f"  has '跑道': {text_check['has_跑道']}\n")
        f.write(f"  text length: {text_check['textLength']}\n")
        f.write(f"\nFirst 500 chars:\n{text_check['first500chars']}\n")
        
        # Now wait longer and check again
        page.wait_for_timeout(2000)  # Total 3.5s
        
        has_content_3500 = page.evaluate(r'''() => {
            const text = document.body.innerText;
            return text.includes('場地狀況') || text.includes('名次');
        }''')
        
        f.write(f"\n\nhas_content with 3.5s wait: {has_content_3500}\n")
        
        text_check_3500 = page.evaluate(r'''() => {
            const text = document.body.innerText;
            return {
                has_場地狀況: text.includes('場地狀況'),
                has_名次: text.includes('名次'),
                textLength: text.length
            };
        }''')
        
        f.write(f"\nText checks with 3.5s wait:\n")
        f.write(f"  has '場地狀況': {text_check_3500['has_場地狀況']}\n")
        f.write(f"  has '名次': {text_check_3500['has_名次']}\n")
        f.write(f"  text length: {text_check_3500['textLength']}\n")
    
    browser.close()
    
    print(f"Debug output written to {out_path}")
