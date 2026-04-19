os.environ.setdefault('PYTHONUTF8', '1')
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
import sys
import os
import json
import re

with open('nuxt_overview.json', 'r') as f:
    nuxt_data = json.load(f)

apollo = nuxt_data.get('apollo', {}).get('horseClient', {})

# Find all RaceMeetings
meetings = []
for k, v in apollo.items():
    if k.startswith("RaceMeeting:"):
         meetings.append((v.get('slug'), v.get('name')))
         
for m in meetings:
    print(m)
    
print("----")
# Check events individually to see what their meeting is
for k, v in apollo.items():
    if k.startswith("Event:"):
         if 'lady-of-racing' in v.get('eventSlug', ''):
             print(f"Event {v.get('eventSlug')} has meeting ref: {v.get('meeting', {}).get('__ref')}")
