#!/usr/bin/env python3
import os
os.environ.setdefault('PYTHONUTF8', '1')
import sys
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
"""
generate_meeting_intel.py — AU Meeting Intelligence Package Generator
=====================================================================
Integrated into au_orchestrator.py State 1 to auto-generate
_Meeting_Intelligence_Package.md with real weather data + predictions.

Pipeline:
  1. Claw Code (curl_cffi + Playwright) → extract Racenet weather/track
  2. Open-Meteo API → hourly forecast (rain, wind, humidity, temp)
  3. Track Profiles JSON → drainage/surface analysis
  4. Prediction Engine → early/late race track condition shift
  5. Output → _Meeting_Intelligence_Package.md

Usage:
  python3 generate_meeting_intel.py --url <racenet_overview_url> --target-dir <path>
  python3 generate_meeting_intel.py --url <url> --target-dir <path> --venue Pakenham
"""
import argparse
import json
import os
import re
import sys
import time

# --- Geo coordinates for Open-Meteo ---
COURSE_GEO = {
    # VIC
    'Flemington':       {'lat': -37.7887, 'lon': 144.9126},
    'Caulfield':        {'lat': -37.8812, 'lon': 145.0416},
    'Moonee Valley':    {'lat': -37.7656, 'lon': 144.9287},
    'Sandown':          {'lat': -37.9089, 'lon': 145.1712},
    'Sandown Hillside': {'lat': -37.9089, 'lon': 145.1712},
    'Sandown Lakeside': {'lat': -37.9089, 'lon': 145.1712},
    'Cranbourne':       {'lat': -38.0992, 'lon': 145.2839},
    'Pakenham':         {'lat': -38.1567, 'lon': 145.5711},
    'Mornington':       {'lat': -38.2176, 'lon': 145.0378},
    'Geelong':          {'lat': -38.1685, 'lon': 144.3542},
    'Ballarat':         {'lat': -37.5622, 'lon': 143.8503},
    'Bendigo':          {'lat': -36.7570, 'lon': 144.2794},
    'Sale':             {'lat': -38.1000, 'lon': 147.0667},
    'Kilmore':          {'lat': -37.2973, 'lon': 144.9544},
    'Seymour':          {'lat': -37.0273, 'lon': 145.1392},
    'Yarra Valley':     {'lat': -37.7549, 'lon': 145.4667},
    'Kyneton':          {'lat': -37.2451, 'lon': 144.4536},
    'Werribee':         {'lat': -37.8886, 'lon': 144.6569},
    'Wangaratta':       {'lat': -36.3540, 'lon': 146.3060},
    'Warrnambool':      {'lat': -38.3847, 'lon': 142.4911},
    # NSW
    'Randwick':         {'lat': -33.9114, 'lon': 151.2286},
    'Rosehill':         {'lat': -33.8242, 'lon': 151.0225},
    'Canterbury':       {'lat': -33.9047, 'lon': 151.1081},
    'Warwick Farm':     {'lat': -33.9131, 'lon': 150.9367},
    'Newcastle':        {'lat': -32.9283, 'lon': 151.7817},
    'Gosford':          {'lat': -33.4215, 'lon': 151.3283},
    'Kembla Grange':    {'lat': -34.4573, 'lon': 150.8053},
    # QLD
    'Eagle Farm':       {'lat': -27.4338, 'lon': 153.0678},
    'Doomben':          {'lat': -27.4279, 'lon': 153.0592},
    'Gold Coast':       {'lat': -28.0089, 'lon': 153.4042},
    'Sunshine Coast':   {'lat': -26.7977, 'lon': 153.0610},
}

RATING_LABELS = {
    1: 'Firm 1', 2: 'Firm 2', 3: 'Good 3', 4: 'Good 4',
    5: 'Soft 5', 6: 'Soft 6', 7: 'Soft 7',
    8: 'Heavy 8', 9: 'Heavy 9', 10: 'Heavy 10'
}

def parse_track_rating(condition_str):
    """Parse 'Soft 6' → (6, 'Soft')"""
    m = re.match(r'(\w+)\s+(\d+)', condition_str.strip())
    if m:
        return int(m.group(2)), m.group(1)
    return 4, 'Good'  # default

# ─────────────────────────────────────────────
# Step 1: Extract Racenet weather via Claw Code
# ─────────────────────────────────────────────
def extract_racenet_weather(url):
    """Use curl_cffi + Playwright to get weather/track from Racenet overview page."""
    try:
        from curl_cffi import requests as cffi_requests
        from playwright.sync_api import sync_playwright
    except ImportError as e:
        print(f"  ⚠️ Claw Code dependencies missing ({e}), skipping Racenet extraction")
        return None

    print(f"  📡 [Claw Code] Fetching Racenet overview...")
    headers = {
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36'
    }
    try:
        resp = cffi_requests.get(url, impersonate="chrome120", headers=headers, timeout=30)
        resp.raise_for_status()
    except Exception as e:
        print(f"  ❌ Racenet fetch failed: {e}")
        return None

    temp_html = os.path.abspath(f"_mip_temp_{int(time.time())}.html")
    with open(temp_html, 'w') as f:
        f.write(resp.text)

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            page.goto(f"file://{temp_html}")
            nuxt = page.evaluate("() => window.__NUXT__")
            browser.close()
    except Exception as e:
        print(f"  ❌ Playwright hydration failed: {e}")
        if os.path.exists(temp_html):
            os.remove(temp_html)
        return None

    if os.path.exists(temp_html):
        os.remove(temp_html)

    apollo = nuxt.get('apollo', {}).get('defaultClient', nuxt.get('apollo', {}).get('horseClient', {}))
    result = {'weather': 'Unknown', 'track_condition': 'Unknown', 'detail': {}}

    # Extract weather
    for key, val in apollo.items():
        if key.endswith('.weather') and key.startswith('$Event:') and isinstance(val, dict):
            cond = val.get('condition', '')
            temp = val.get('temperature', '')
            if cond:
                result['weather'] = f"{cond.title()} {temp}°C" if temp else cond.title()
                result['detail'] = {
                    'condition': cond,
                    'temperature': temp,
                    'feelsLike': val.get('feelsLike', ''),
                    'wind': val.get('wind', ''),
                    'humidity': val.get('humidity', ''),
                    'icon': val.get('conditionIcon', ''),
                }
                print(f"  ✅ Weather: {result['weather']} | {val.get('wind','')} | {val.get('humidity','')}")
            break

    # Extract track condition
    for key, val in apollo.items():
        if key.endswith('.trackCondition') and key.startswith('$Event:') and isinstance(val, dict):
            overall = val.get('overall', '')
            rating = val.get('rating', '')
            surface = val.get('surface', '')
            if overall:
                result['track_condition'] = f"{overall} {rating}".strip()
                result['track_rating'] = rating
                result['track_surface'] = surface
                print(f"  ✅ Track: {overall} {rating} ({surface})")
            break

    # Extract rail from Meeting
    for key, val in apollo.items():
        if key.startswith('Meeting:') and isinstance(val, dict):
            rail = val.get('railPosition', '')
            if rail:
                result['rail'] = rail
                break

    return result

# ─────────────────────────────────────────
# Step 2: Fetch Open-Meteo hourly forecast
# ─────────────────────────────────────────
def fetch_open_meteo(venue):
    """Fetch hourly forecast from Open-Meteo for the venue."""
    geo = COURSE_GEO.get(venue)
    if not geo:
        # Try partial match
        for k, v in COURSE_GEO.items():
            if venue.lower() in k.lower() or k.lower() in venue.lower():
                geo = v
                venue = k
                break
    if not geo:
        print(f"  ⚠️ No geo coordinates for '{venue}', using Melbourne default")
        geo = {'lat': -37.8136, 'lon': 144.9631}

    url = (
        f"https://api.open-meteo.com/v1/forecast?"
        f"latitude={geo['lat']}&longitude={geo['lon']}"
        f"&hourly=temperature_2m,precipitation,wind_speed_10m,relative_humidity_2m"
        f"&timezone=Australia/Melbourne&forecast_days=2"
    )

    try:
        import urllib.request
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode())
    except Exception as e:
        print(f"  ⚠️ Open-Meteo fetch failed: {e}")
        return None

    hourly = data.get('hourly', {})
    times = hourly.get('time', [])
    precip = hourly.get('precipitation', [])
    temp = hourly.get('temperature_2m', [])
    wind = hourly.get('wind_speed_10m', [])
    humidity = hourly.get('relative_humidity_2m', [])

    forecast = []
    for i, t in enumerate(times):
        forecast.append({
            'time': t,
            'precipitation_mm': precip[i] if i < len(precip) else 0,
            'temperature': temp[i] if i < len(temp) else 0,
            'wind_speed': wind[i] if i < len(wind) else 0,
            'humidity': humidity[i] if i < len(humidity) else 0,
        })

    print(f"  ✅ Open-Meteo: {len(forecast)} hourly data points fetched for {venue}")
    return forecast

# ─────────────────────────────────────────
# Step 3: Load track profile
# ─────────────────────────────────────────
def load_track_profile(venue):
    """Load track profile from track_profiles.json."""
    profile_path = os.path.join(
        os.path.dirname(os.path.abspath(__file__)),
        '../../au_racecourse_weather_prediction/resources/track_profiles.json'
    )
    if not os.path.exists(profile_path):
        print(f"  ⚠️ track_profiles.json not found at {profile_path}")
        return None

    with open(profile_path, 'r', encoding='utf-8') as f:
        profiles = json.load(f)

    # Search all states for the venue
    for state, state_data in profiles.items():
        courses = state_data.get('courses', {})
        for course_name, profile in courses.items():
            if venue.lower() == course_name.lower():
                print(f"  ✅ Track profile: {course_name} — {profile.get('tier', 'N/A')} ({profile.get('profile','')})")
                return profile
            # partial match
            if venue.lower() in course_name.lower() or course_name.lower() in venue.lower():
                print(f"  ✅ Track profile: {course_name} — {profile.get('tier', 'N/A')} ({profile.get('profile','')})")
                return profile

    print(f"  ⚠️ No track profile found for '{venue}', using generic")
    return {'tier': 'Unknown', 'profile': 'Unknown', 'drainage': 'Unknown'}

# ─────────────────────────────────────────
# Step 4: Predict track condition changes
# ─────────────────────────────────────────
def predict_track_shift(current_rating_num, forecast, track_profile, race_times=None):
    """
    Apply prediction rules from SKILL.md:
    1. Rainfall x Track Profile
    2. Wind & Humidity cross
    3. Intra-day degradation/upgrading
    """
    if not forecast:
        return {
            'early': current_rating_num,
            'late': current_rating_num,
            'reasoning': '無天氣預報數據，維持現有掛牌'
        }

    # Compute race-window stats (assume R1-R4 is hours 14-17, R5+ is hours 17-21)
    # Filter to today's afternoon/evening hours
    today_hours = [h for h in forecast if 'T' in h['time']]
    early_hours = [h for h in today_hours if any(f"T{hr:02d}" in h['time'] for hr in range(14, 18))]
    late_hours = [h for h in today_hours if any(f"T{hr:02d}" in h['time'] for hr in range(18, 22))]

    def avg_stat(hours, key):
        vals = [h.get(key, 0) for h in hours]
        return sum(vals) / len(vals) if vals else 0

    def total_rain(hours):
        return sum(h.get('precipitation_mm', 0) for h in hours)

    early_rain = total_rain(early_hours)
    late_rain = total_rain(late_hours)
    early_wind = avg_stat(early_hours, 'wind_speed')
    late_wind = avg_stat(late_hours, 'wind_speed')
    early_humidity = avg_stat(early_hours, 'humidity')
    late_humidity = avg_stat(late_hours, 'humidity')
    early_temp = avg_stat(early_hours, 'temperature')

    # Track drainage factor
    tier = (track_profile or {}).get('tier', 'Unknown').lower()
    if 'top' in tier:
        drainage_factor = 0.7  # drains fast
    elif 'moderate' in tier:
        drainage_factor = 0.5
    elif 'bottom' in tier:
        drainage_factor = 0.3  # holds water
    else:
        drainage_factor = 0.5

    reasoning_parts = []

    # --- Rule 1: Rainfall x Profile ---
    rain_downgrade = 0
    total_forecast_rain = early_rain + late_rain
    if total_forecast_rain > 0:
        rain_downgrade = round(total_forecast_rain * (1.0 - drainage_factor) * 0.5)
        reasoning_parts.append(f"預計降雨 {total_forecast_rain:.1f}mm, 排水系數 {drainage_factor} → 場地可能降級 {rain_downgrade} 格")

    # --- Rule 2: Wind & Humidity ---
    upgrade_pts = 0
    if early_wind > 20:
        upgrade_pts += 1
        reasoning_parts.append(f"早場強風 {early_wind:.0f}kph → 可能升級 1 格")
    if early_humidity > 75:
        upgrade_pts = max(0, upgrade_pts - 1)
        reasoning_parts.append(f"濕度偏高 {early_humidity:.0f}% → 風乾速度減半")

    # --- Rule 3: Intra-day shift ---
    intraday_shift = 0
    if current_rating_num >= 6:
        intraday_shift = 1  # degrade further due to hooves
        reasoning_parts.append(f"場地已達 {current_rating_num}，賽事踐踏預期中晚場惡化 +1")
    elif current_rating_num <= 5 and early_wind > 15 and early_humidity < 60:
        intraday_shift = -1  # dry out
        reasoning_parts.append(f"場地狀態尚可，風速 {early_wind:.0f}kph 配合低濕度 → 晚場可能風乾 -1")

    # Calculate predictions
    early_predicted = max(1, min(10, current_rating_num + rain_downgrade - upgrade_pts))
    late_predicted = max(1, min(10, early_predicted + intraday_shift + (1 if late_rain > 2 else 0)))

    if late_rain > 2:
        reasoning_parts.append(f"晚間預計再落 {late_rain:.1f}mm → 場地繼續惡化")

    if not reasoning_parts:
        reasoning_parts.append("天氣條件穩定，場地預期維持不變")

    return {
        'early': early_predicted,
        'late': late_predicted,
        'early_rain_mm': round(early_rain, 1),
        'late_rain_mm': round(late_rain, 1),
        'early_wind': round(early_wind, 1),
        'early_humidity': round(early_humidity, 1),
        'early_temp': round(early_temp, 1),
        'reasoning': '；'.join(reasoning_parts)
    }

# ─────────────────────────────────────────
# Step 5: Generate MIP file
# ─────────────────────────────────────────
def generate_mip(target_dir, venue, date_str, racenet_data, forecast, track_profile, prediction):
    """Write _Meeting_Intelligence_Package.md with all data."""
    mip_path = os.path.join(target_dir, '_Meeting_Intelligence_Package.md')

    current_track = racenet_data.get('track_condition', 'Unknown') if racenet_data else 'Unknown'
    weather_str = racenet_data.get('weather', 'Unknown') if racenet_data else 'Unknown'
    rail = racenet_data.get('rail', 'Unknown') if racenet_data else 'Unknown'
    detail = racenet_data.get('detail', {}) if racenet_data else {}
    surface = racenet_data.get('track_surface', '') if racenet_data else ''

    profile_str = (track_profile or {}).get('profile', 'Unknown')
    drainage_str = (track_profile or {}).get('drainage', 'Unknown')
    tier = (track_profile or {}).get('tier', 'Unknown')

    early_label = RATING_LABELS.get(prediction['early'], f"Rating {prediction['early']}")
    late_label = RATING_LABELS.get(prediction['late'], f"Rating {prediction['late']}")

    # Determine bias
    current_num, _ = parse_track_rating(current_track)
    if current_num >= 6:
        bias_conclusion = "輕微偏向前置 (Slight On-Pace Bias) — 軟地加大後追難度，前領/守好位馬匹佔優"
    elif current_num <= 3:
        bias_conclusion = "公平至輕微偏向後追 (Fair to Slight Closer Bias) — 硬地利好速度型馬匹"
    else:
        bias_conclusion = "公平 (Fair) — 略為偏向守好位 (On-pace)"

    content = f"""# 🏟️ 賽事天氣與場地情報 (Meeting Intelligence Package)
> 🤖 由 `generate_meeting_intel.py` 自動生成 | 數據源: Racenet + Open-Meteo

## 📍 賽場基本資訊
- **賽場**: {venue}
- **日期**: {date_str}
- **移欄 (Rail)**: {rail}
- **天氣 (Weather)**: {weather_str}
- **場地狀況 (Track Condition)**: {current_track}
- **場地表面 (Surface)**: {surface if surface else 'Turf (草地)'}
- **風向風速 (Wind)**: {detail.get('wind', 'N/A')}
- **相對濕度 (Humidity)**: {detail.get('humidity', 'N/A')}
- **體感溫度 (Feels Like)**: {detail.get('feelsLike', 'N/A')}°C

## 🏗️ 馬場底層結構 (Track Profile)
- **排水等級**: {tier}
- **底層材質**: {profile_str}
- **排水特性**: {drainage_str}

## 🌦️ 天氣預測與賽日推演 (Weather Prediction & Track Deduction)

📡 **Open-Meteo 預報摘要**:
- **早場 (R1-R4) 預計降雨**: {prediction.get('early_rain_mm', 'N/A')}mm
- **晚場 (R5+) 預計降雨**: {prediction.get('late_rain_mm', 'N/A')}mm
- **早場平均風速**: {prediction.get('early_wind', 'N/A')} kph
- **早場平均濕度**: {prediction.get('early_humidity', 'N/A')}%
- **早場平均溫度**: {prediction.get('early_temp', 'N/A')}°C

🔬 **運算推理**:
{prediction.get('reasoning', 'N/A')}

🎯 **最終預測掛牌 (Predicted Dynamic Rating)**:
- **早場 (R1-R4)**: **{early_label}**
- **中晚場 (R5+)**: **{late_label}**

## 🔍 賽道偏差預測 (Track Bias Analysis)
- **結論**: `{bias_conclusion}`
- **檔位影響**: `中內檔優勢 (Inside-to-middle barrier advantage)` — 移欄設定下有輕微內檔優勢
"""

    # Add soft-ground specific notes if applicable
    if current_num >= 5:
        content += f"""
### ⚠️ 軟地影響分析 ({current_track})
- 軟地會增加後追馬的難度，因為濕軟場地加大阻力，令後段追視需要更多體力
- 前領/守好位嘅馬匹佔優，因為跑外疊的體力消耗在軟地上更為明顯
- 具備軟地 (Soft) 實績嘅馬匹應獲加分
- 純沙底/高效排水馬場在軟地下仍可能利好後追馬，需視乎底層結構評估
"""

    content += f"\n`[PREDICTED_TRACK_CONDITION] {early_label}`\n"

    with open(mip_path, 'w', encoding='utf-8') as f:
        f.write(content)

    print(f"\n✅ Meeting Intelligence Package 已生成 → {mip_path}")
    return mip_path

# ─────────────────────────────────────────
# Main entry point
# ─────────────────────────────────────────
def run(url, target_dir, venue=None, date_str=None):
    """Main pipeline entry: extract → forecast → predict → generate MIP."""
    print("=" * 60)
    print("🌦️ AU Meeting Intelligence Package Generator")
    print("=" * 60)

    # Parse venue/date from URL if not provided
    if not venue or not date_str:
        m = re.search(r'form-guide/horse-racing/([^/]+)-(\d{8})/', url)
        if m:
            if not venue:
                venue = m.group(1).replace('-', ' ').title()
            if not date_str:
                d = m.group(2)
                date_str = f"{d[:4]}-{d[4:6]}-{d[6:]}"

    if not venue:
        venue = "Unknown"
    if not date_str:
        from datetime import datetime
        date_str = datetime.now().strftime("%Y-%m-%d")

    print(f"  📍 Venue: {venue}")
    print(f"  📅 Date: {date_str}")
    print(f"  📂 Target: {target_dir}\n")

    # Step 1: Racenet extraction
    print("─── Step 1: Racenet Weather Extraction (Claw Code) ───")
    racenet_data = extract_racenet_weather(url)
    if not racenet_data or racenet_data.get('track_condition') == 'Unknown':
        print("  ⚠️ Racenet data unavailable, will use Open-Meteo only")

    # Step 2: Open-Meteo forecast
    print("\n─── Step 2: Open-Meteo Hourly Forecast ───")
    forecast = fetch_open_meteo(venue)

    # Step 3: Track profile
    print("\n─── Step 3: Track Profile Lookup ───")
    track_profile = load_track_profile(venue)

    # Step 4: Prediction
    print("\n─── Step 4: Track Condition Prediction Engine ───")
    current_num = 4  # default Good 4
    if racenet_data and racenet_data.get('track_condition') != 'Unknown':
        current_num, _ = parse_track_rating(racenet_data['track_condition'])
    prediction = predict_track_shift(current_num, forecast, track_profile)
    early_label = RATING_LABELS.get(prediction['early'], f"Rating {prediction['early']}")
    late_label = RATING_LABELS.get(prediction['late'], f"Rating {prediction['late']}")
    print(f"  📊 Current: {RATING_LABELS.get(current_num, '?')}")
    print(f"  📊 Early (R1-R4): {early_label}")
    print(f"  📊 Late (R5+): {late_label}")
    print(f"  📊 Reasoning: {prediction['reasoning']}")

    # Step 5: Generate MIP
    print("\n─── Step 5: Generate _Meeting_Intelligence_Package.md ───")
    mip_path = generate_mip(target_dir, venue, date_str, racenet_data, forecast, track_profile, prediction)

    return mip_path


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description="Generate Meeting Intelligence Package")
    parser.add_argument('--url', required=True, help='Racenet overview URL')
    parser.add_argument('--target-dir', required=True, help='Output directory')
    parser.add_argument('--venue', default=None, help='Venue name (auto-detected from URL)')
    parser.add_argument('--date', default=None, help='Date string YYYY-MM-DD')
    args = parser.parse_args()

    run(args.url, args.target_dir, venue=args.venue, date_str=args.date)
