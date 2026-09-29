#!/usr/bin/env python3
"""Horse profile scraper: extract age, career stats, prize money, and form history."""
import os
import sys
import json
import re
from typing import Dict, List, Optional
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from playwright.sync_api import sync_playwright

# Load env
env_path = Path(__file__).parent.parent / '.env.local'
with open(env_path, 'r', encoding='utf-8') as f:
    for line in f:
        line = line.strip()
        if line and not line.startswith('#') and '=' in line:
            key, value = line.split('=', 1)
            os.environ[key] = value

from supabase import create_client

def scrape_horse_profile(horse_code: str) -> Optional[Dict]:
    """Scrape horse profile data from HKJC."""
    url = f"https://racing.hkjc.com/racing/information/Chinese/Horse/Horse.aspx?HorseNo={horse_code}"
    
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=['--no-sandbox', '--disable-gpu'])
        page = browser.new_page()
        
        try:
            page.goto(url, wait_until='domcontentloaded', timeout=30000)
            page.wait_for_timeout(2000)
            
            # Extract horse profile data
            profile = page.evaluate(r'''() => {
                const text = document.body.innerText;
                
                // Extract age (馬齡) - format: 出生地 / 馬齡 : 紐西蘭 / 6
                const ageMatch = text.match(/馬齡\s*[:：]\s*.*?\/\s*(\d+)/);
                const age = ageMatch ? parseInt(ageMatch[1]) : null;
                
                // Extract career stats (冠-亞-季-總出賽次數) - format: 1-0-0-15
                const careerMatch = text.match(/冠-亞-季-總出賽次數\*?\s*[:：]\s*(\d+)-(\d+)-(\d+)-(\d+)/);
                let career_wins = null, career_places = null, career_starts = null;
                if (careerMatch) {
                    career_wins = parseInt(careerMatch[1]);
                    const seconds = parseInt(careerMatch[2]);
                    const thirds = parseInt(careerMatch[3]);
                    career_places = seconds + thirds;
                    career_starts = parseInt(careerMatch[4]);
                }
                
                // Extract total prize money (總獎金) - format: $527,200
                const prizeMatch = text.match(/總獎金\*?\s*[:：]\s*\$?([\d,]+)/);
                const total_prize = prizeMatch ? prizeMatch[1].replace(/,/g, '') : null;
                
                return {
                    age,
                    career_starts,
                    career_wins,
                    career_places,
                    total_prize_money: total_prize ? parseInt(total_prize) : null
                };
            }''')
            
            # Extract form history (往績紀錄)
            form_history = page.evaluate(r'''() => {
                const text = document.body.innerText;
                const lines = text.split('\n').map(l => l.trim()).filter(l => l);
                
                // Find the form history table
                const records = [];
                let inFormSection = false;
                
                for (let i = 0; i < lines.length; i++) {
                    const line = lines[i];
                    
                    // Detect start of form history section
                    if (line.includes('馬匹近三季往績紀錄')) {
                        inFormSection = true;
                        continue;
                    }
                    
                    if (!inFormSection) continue;
                    
                    // Stop at next section
                    if (line.includes('未滿十八歲') || line.includes('免責聲明')) {
                        break;
                    }
                    
                    // Parse form record line
                    // Format: 場次 名次 日期 馬場/跑道/賽道 途程 場地狀況 賽事班次 檔位 評分 練馬師 騎師 頭馬距離 獨贏賠率 實際負磅 沿途走位 完成時間 排位體重 配備
                    const match = line.match(/^(\d+)\s+(\d+)\s+(\d{2}\/\d{2}\/\d{2})\s+(.+?)\s+(\d+)\s+(.+?)\s+(\d+)\s+(\d+)\s+(\d+)\s+(.+?)\s+(.+?)\s+([\d\-\/]+)\s+(\d+)\s+(\d+)\s+([\d\s]+)\s+([\d:]+)\s+(\d+)\s+(.+)$/);
                    
                    if (match) {
                        records.push({
                            race_no: match[1],
                            finish_position: parseInt(match[2]),
                            race_date: match[3],
                            venue_track: match[4],
                            distance: parseInt(match[5]),
                            going: match[6],
                            class: parseInt(match[7]),
                            draw: parseInt(match[8]),
                            rating: parseInt(match[9]),
                            trainer: match[10],
                            jockey: match[11],
                            margin: match[12],
                            odds: parseInt(match[13]),
                            weight: parseInt(match[14]),
                            sectional: match[15].trim(),
                            finish_time: match[16],
                            declared_weight: parseInt(match[17]),
                            equipment: match[18]
                        });
                    }
                }
                
                return records.slice(0, 10); // Return last 10 races
            }''')
            
            browser.close()
            
            return {
                'horse_code': horse_code,
                **profile,
                'form_history': form_history
            }
            
        except Exception as e:
            print(f"Error scraping {horse_code}: {e}")
            browser.close()
            return None

def update_horse_data(horse_code: str, profile_data: Dict):
    """Update horse data in Supabase."""
    url = os.getenv('NEXT_PUBLIC_SUPABASE_URL')
    key = os.getenv('SUPABASE_SERVICE_KEY')
    supabase = create_client(url, key)
    
    # Update race_runners table with career stats and form_history
    try:
        # Find all runners for this horse
        runners = supabase.table('race_runners').select('runner_id').eq('horse_id', horse_code).execute()
        
        update_data = {}
        if profile_data.get('age') is not None:
            update_data['age'] = profile_data['age']
        if profile_data.get('career_starts') is not None:
            update_data['career_starts'] = profile_data['career_starts']
        if profile_data.get('career_wins') is not None:
            update_data['career_wins'] = profile_data['career_wins']
        if profile_data.get('career_places') is not None:
            update_data['career_places'] = profile_data['career_places']
        if profile_data.get('total_prize_money') is not None:
            update_data['total_prize_money'] = profile_data['total_prize_money']
        
        if update_data:
            for runner in runners.data:
                supabase.table('race_runners').update(update_data).eq('runner_id', runner['runner_id']).execute()
            print(f"  [OK] Updated career stats for {len(runners.data)} runners of {horse_code}")

        if profile_data.get('form_history'):
            positions = []
            for rec in profile_data['form_history']:
                pos = rec.get('finish_position')
                if pos is not None:
                    positions.append(str(pos))
            form_str = '-'.join(positions) if positions else ''

            if form_str:
                for runner in runners.data:
                    supabase.table('race_runners').update({
                        'form_history': form_str
                    }).eq('runner_id', runner['runner_id']).execute()
                print(f"  [OK] Updated form_history for {len(runners.data)} runners of {horse_code}: {form_str}")
            
    except Exception as e:
        print(f"  [WARN] Failed to update race_runners: {e}")

if __name__ == '__main__':
    # Test with K209 (大浪園田)
    test_horse = 'K209'
    print(f"Scraping horse profile: {test_horse}")
    
    result = scrape_horse_profile(test_horse)
    
    if result:
        print(f"\nProfile data:")
        print(f"  Age: {result.get('age')}")
        print(f"  Career starts: {result.get('career_starts')}")
        print(f"  Career wins: {result.get('career_wins')}")
        print(f"  Career places: {result.get('career_places')}")
        prize = result.get('total_prize_money')
        print(f"  Total prize: ${prize:,}" if prize else "  Total prize: N/A")
        print(f"  Form history: {len(result.get('form_history', []))} records")
        
        if result.get('form_history'):
            print(f"\nFirst 3 form records:")
            for i, rec in enumerate(result['form_history'][:3]):
                print(f"  {i+1}. {rec['race_date']} - Position {rec['finish_position']}, {rec['distance']}m, Jockey: {rec['jockey']}")
        
        # Update database
        print(f"\nUpdating database...")
        update_horse_data(test_horse, result)
    else:
        print("Failed to scrape horse profile")
