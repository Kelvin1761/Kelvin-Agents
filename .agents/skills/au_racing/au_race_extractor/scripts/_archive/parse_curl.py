from bs4 import BeautifulSoup

with open('./racenet_curl.html', 'r') as f:
    soup = BeautifulSoup(f.read(), 'html.parser')
    
for i, script in enumerate(soup.find_all('script')):
    s = script.string or ''
    if 'apolloState' in s or 'Briga Fliedner' in s or 'PRELOADED' in s:
        id = script.get('id', '')
        print(f"Script {i} (id={id}) matched. Length: {len(s)}")
        print(s[:200])
