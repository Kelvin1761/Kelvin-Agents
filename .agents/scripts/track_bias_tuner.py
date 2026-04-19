os.environ.setdefault('PYTHONUTF8', '1')
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
import os
import sys
import sqlite3
import argparse

DB_PATH = r'g:\我的雲端硬碟\Antigravity Shared\Antigravity\.agents\skills\au_racing\shared_resources\wong_choi_racing.db'

RATING_MAP = {
    'Firm 1': 1, 'Firm 2': 2, 'Good 3': 3, 'Good 4': 4,
    'Soft 5': 5, 'Soft 6': 6, 'Soft 7': 7, 
    'Heavy 8': 8, 'Heavy 9': 9, 'Heavy 10': 10
}

def tune_drainage(course, predicted_rating, actual_rating):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    cursor.execute('SELECT drainage_coefficient FROM track_drainage_coefficients WHERE course = ?', (course,))
    row = cursor.fetchone()
    
    if not row:
        current_coeff = 0.5
        cursor.execute('INSERT INTO track_drainage_coefficients (course, drainage_coefficient) VALUES (?, ?)', (course, current_coeff))
    else:
        current_coeff = row[0]
        
    pred_val = RATING_MAP.get(predicted_rating, 4)
    act_val = RATING_MAP.get(actual_rating, 4)
    
    error = pred_val - act_val
    
    LEARNING_RATE = 0.05
    new_coeff = current_coeff + (error * LEARNING_RATE)
    new_coeff = max(0.0, min(1.0, new_coeff)) 
    
    cursor.execute('UPDATE track_drainage_coefficients SET drainage_coefficient = ?, last_updated=CURRENT_TIMESTAMP WHERE course = ?', (new_coeff, course))
    conn.commit()
    conn.close()
    
    return current_coeff, new_coeff, error

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--course', required=True)
    parser.add_argument('--date', required=True)
    parser.add_argument('--actual', required=True, help="E.g. 'Soft 5'")
    args = parser.parse_args()

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('SELECT id, predicted_rating FROM track_predictions WHERE course = ? AND date = ? ORDER BY timestamp DESC LIMIT 1', (args.course, args.date))
    row = cursor.fetchone()
    
    if not row:
        print(f"No prediction logged for {args.course} on {args.date}. Skipping tuner.")
        sys.exit(0)
        
    prediction_id, predicted_rating = row
    
    pred_val = RATING_MAP.get(predicted_rating, 4)
    act_val = RATING_MAP.get(args.actual, 4)
    error_margin = pred_val - act_val
    
    cursor.execute('UPDATE track_predictions SET actual_rating = ?, error_margin = ? WHERE id = ?', (args.actual, error_margin, prediction_id))
    conn.commit()
    conn.close()
    
    old_c, new_c, err = tune_drainage(args.course, predicted_rating, args.actual)
    
    print(f"Track: {args.course} | Date: {args.date}")
    print(f"Predicted: {predicted_rating} | Actual: {args.actual} | Error: {err} levels")
    print(f"Tuning Drainage Coefficient: {old_c:.3f} -> {new_c:.3f}")

if __name__ == '__main__':
    main()
