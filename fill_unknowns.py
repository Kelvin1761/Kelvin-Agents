import csv
import requests
import time
import os

API_KEY = "YOUR_API_KEY_HERE"

desktop_path = os.path.expanduser('~\\Desktop\\Australia_Gun_Shops_Ranges.csv')
workspace_path = 'Australia_Gun_Shops_Ranges.csv'

records = []
try:
    with open(desktop_path, 'r', encoding='utf-8-sig') as f:
        reader = csv.DictReader(f)
        for row in reader:
            records.append(row)
except:
    with open(workspace_path, 'r', encoding='utf-8-sig') as f:
        reader = csv.DictReader(f)
        for row in reader:
            records.append(row)

url = "https://places.googleapis.com/v1/places:searchNearby"
headers = {
    'X-Goog-Api-Key': API_KEY,
    'X-Goog-FieldMask': 'places.displayName.text,places.types',
    'Content-Type': 'application/json'
}

keywords = ['shoot', 'rifle', 'gun', 'pistol', 'club', 'range', 'ssaa', 'target', 'clay', 'archery', 'branch']

updates_made = 0
count_checked = 0

print("Scanning for Unknown names nearby using Google Places API...")

for r in records:
    name = r['Name']
    if name == 'Unknown' or name.startswith('Facility on '):
        count_checked += 1
        try:
            lat = float(r['Latitude (S)'])
            lon = float(r['Longitude (E)'])
            
            payload = {
                "maxResultCount": 5,
                "locationRestriction": {
                    "circle": {
                        "center": {
                            "latitude": lat,
                            "longitude": lon
                        },
                        "radius": 200.0
                    }
                }
            }
            
            resp = requests.post(url, headers=headers, json=payload)
            data = resp.json()
            
            if resp.status_code != 200:
                continue
                
            found_name = None
            
            for place in data.get('places', []):
                p_name = place.get('displayName', {}).get('text', '')
                p_name_lower = p_name.lower()
                if any(k in p_name_lower for k in keywords):
                    found_name = p_name
                    break
            
            if not found_name and data.get('places'):
                first_name = data['places'][0].get('displayName', {}).get('text', '')
                if len(first_name) > 3:
                     found_name = first_name
                     
            if found_name:
                r['Name'] = f"{found_name} (Google)"
                updates_made += 1
                
        except Exception as e:
            pass

print(f"Checked {count_checked} unnamed records.")
print(f"Total Names Discovered & Updated: {updates_made}")

with open(desktop_path, 'w', newline='', encoding='utf-8-sig') as f:
    writer = csv.DictWriter(f, fieldnames=['Name', 'Type', 'Suburb/Area', 'Latitude (S)', 'Longitude (E)'])
    writer.writeheader()
    writer.writerows(records)

with open(workspace_path, 'w', newline='', encoding='utf-8-sig') as f:
    writer = csv.DictWriter(f, fieldnames=['Name', 'Type', 'Suburb/Area', 'Latitude (S)', 'Longitude (E)'])
    writer.writeheader()
    writer.writerows(records)
