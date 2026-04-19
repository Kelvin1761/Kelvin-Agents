os.environ.setdefault('PYTHONUTF8', '1')
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
import os
import sys
import json
import sqlite3
import argparse
import requests
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

DB_PATH = r'g:\我的雲端硬碟\Antigravity Shared\Antigravity\.agents\skills\au_racing\shared_resources\wong_choi_racing.db'

COURSE_GEO = {
    'Randwick': {'lat': -33.9114, 'lon': 151.2286},
    'Rosehill': {'lat': -33.8242, 'lon': 151.0225},
    'Flemington': {'lat': -37.7887, 'lon': 144.9126},
    'Caulfield': {'lat': -37.8812, 'lon': 145.0416},
    'Moonee Valley': {'lat': -37.7656, 'lon': 144.9287},
    'Gosford': {'lat': -33.4215, 'lon': 151.3283}
}

RATING_MAP = {
    'Firm 1': 1, 'Firm 2': 2, 'Good 3': 3, 'Good 4': 4,
    'Soft 5': 5, 'Soft 6': 6, 'Soft 7': 7, 
    'Heavy 8': 8, 'Heavy 9': 9, 'Heavy 10': 10
}
REVERSE_RATING_MAP = {v: k for k, v in RATING_MAP.items()}

def get_drainage_coefficient(course):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('SELECT drainage_coefficient FROM track_drainage_coefficients WHERE course = ?', (course,))
    row = cursor.fetchone()
    conn.close()
    if row:
        return row[0]
    return 0.5 

def log_prediction(date, course, rain, temp, wind, original, predicted):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""INSERT INTO track_predictions 
                      (date, course, predicted_rainfall, predicted_temp, predicted_wind, original_rating, predicted_rating) 
                      VALUES (?, ?, ?, ?, ?, ?, ?)""",
                   (date, course, rain, temp, wind, original, predicted))
    conn.commit()
    conn.close()

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--course', required=True)
    parser.add_argument('--date', required=True)
    parser.add_argument('--current', default='Good 4')
    args = parser.parse_args()

    course = args.course
    if course not in COURSE_GEO:
        print(json.dumps({'error': f'Course {course} not supported in coordinates yet.'}))
        sys.exit(1)

    geo = COURSE_GEO[course]
    url = f"https://api.open-meteo.com/v1/forecast?latitude={geo['lat']}&longitude={geo['lon']}&daily=temperature_2m_max,wind_speed_10m_max,precipitation_sum&timezone=Australia%2FSydney"
    
    try:
        response = requests.get(url)
        data = response.json()
        if 'daily' not in data:
            print(json.dumps({'error': 'Failed to fetch Open-Meteo data.'}))
            sys.exit(1)
            
        rain = data['daily']['precipitation_sum'][0]
        temp = data['daily']['temperature_2m_max'][0]
        wind = data['daily']['wind_speed_10m_max'][0]
    except Exception as e:
        print(json.dumps({'error': str(e)}))
        sys.exit(1)

    drainage_coeff = get_drainage_coefficient(course)
    current_val = RATING_MAP.get(args.current, 4)
    
    downgrade_pts = (rain * (1.0 - drainage_coeff)) * 0.5
    
    upgrade_pts = 0
    if temp > 25 and wind > 15:
        upgrade_pts = 1  
        
    net_shift = round(downgrade_pts - upgrade_pts)
    predicted_val = max(1, min(10, current_val + net_shift))
    predicted_rating = REVERSE_RATING_MAP.get(predicted_val, 'Unknown')
    
    log_prediction(args.date, course, rain, temp, wind, args.current, predicted_rating)
    
    res = {
        'Course': course,
        'Predicted Rainfall (mm)': float(f"{rain:.2f}"),
        'Max Temp (C)': float(f"{temp:.2f}"),
        'Wind Speed (km/h)': float(f"{wind:.2f}"),
        'Drainage Coefficient': drainage_coeff,
        'Original Rating': args.current,
        'Predicted Rating': predicted_rating,
        'Logic': f'Init: {current_val}, Downgrade Pts: {downgrade_pts:.2f}, ET Upgrade Pts: {upgrade_pts}'
    }
    print(json.dumps(res, indent=2))

if __name__ == '__main__':
    main()
