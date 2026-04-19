os.environ.setdefault('PYTHONUTF8', '1')
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
import requests
import pdfplumber
import sys
import re
from datetime import datetime
import os

def download_pdf(date_str):
    url = f"https://racing.hkjc.com/racing/content/PDF/RaceCard/{date_str}_starter_all_chi.pdf"
    headers = {
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
    }
    
    response = requests.get(url, headers=headers)
    if response.status_code == 200:
        pdf_path = os.path.join(__import__('tempfile').gettempdir(), f"{date_str}_starter.pdf")
        with open(pdf_path, 'wb') as f:
            f.write(response.content)
        return pdf_path
    else:
        print(f"Failed to download PDF from {url}. Status code: {response.status_code}")
        sys.exit(1)

def extract_section(text, start_marker, end_markers):
    """Extracts text between start_marker and the first found end_marker"""
    # Find the start index
    start_match = re.search(start_marker, text)
    if not start_match:
        return ""
    start_idx = start_match.start()
    
    # Find the earliest end index among the provided markers
    end_idx = len(text)
    for marker in end_markers:
        match = re.search(marker, text[start_idx + len(start_match.group(0)):])
        if match:
            found_idx = start_idx + len(start_match.group(0)) + match.start()
            if found_idx < end_idx:
                end_idx = found_idx
                
    return text[start_idx:end_idx].strip()

def extract_pdf_data(pdf_path, date_str):
    print(f"=== HKJC 全日出賽馬匹資料 ({date_str}) ===\n")
    
    try:
        with pdfplumber.open(pdf_path) as pdf:
            text_content = ""
            for page in pdf.pages:
                text_content += page.extract_text() + "\n"
                
        # Define extraction using sequential markers to avoid complex regex lookaheads failing on PDF weirdness
        sections = {
            "騎師榜及出賽場次分佈表": extract_section(
                text_content, 
                r"騎師榜及出賽場次分佈表", 
                [r"練馬師榜及各廄馬匹出賽場次分佈表", r"過去十二個月檔位統計"]
            ),
            "練馬師榜及各廄馬匹出賽場次分佈表": extract_section(
                text_content, 
                r"練馬師榜及各廄馬匹出賽場次分佈表", 
                [r"①\s*場次", r"如何閱讀此馬簿", r"昨日宣佈", r"今日宣佈", r"過去十二個月檔位統計", r"上次出賽後曾置放在從化的出賽馬匹"]
            ),
            "過去十二個月檔位統計": extract_section(
                text_content, 
                r"過去十二個月檔位統計", 
                [r"今日宣佈出賽的", r"昨日宣佈出賽的", r"上次出賽後曾置放在從化的出賽馬匹", r"預計走位圖"]
            ),
            "自購馬匹海外往績": extract_section(
                text_content, 
                r"(今日|昨日)宣佈出賽的.*自購馬匹海外往績", 
                [r"上次出賽後曾置放在從化的出賽馬匹", r"傷患記錄", r"由香港賽馬會"]
            ),
            "上次出賽後曾置放在從化的出賽馬匹": extract_section(
                text_content, 
                r"上次出賽後曾置放在從化的出賽馬匹", 
                [r"傷患記錄", r"由香港賽馬會"]
            ),
            "傷患記錄": extract_section(
                text_content, 
                r"傷患記錄", 
                [r"由香港賽馬會賽事秘書處編制"]
            ) 
        }

        for title, raw_content in sections.items():
            print(f"## {title}")
            print("-" * 50)
            if raw_content:
                # Basic string cleanup
                lines = [line.strip() for line in raw_content.split('\n') if line.strip()]
                
                if title in ["騎師榜及出賽場次分佈表", "練馬師榜及各廄馬匹出賽場次分佈表"]:
                    print("【AI 閱讀指南 / AI Reading Guide】")
                    print("因表格排版，真實欄位順序如下 (Columns in order):")
                    print("姓名 | [今季總計] 冠 亞 季 殿 出賽 勝率 上名率 獎金 | [田草] 冠 亞 季 殿 出賽 | [泥地] 冠 亞 季 殿 出賽 | [谷草] 冠 亞 季 殿 出賽 | [近30日] 冠 出賽 | [歷年] 冠 出賽\n")
                
                # Check for table headers and format with better spacing
                formatted_lines = []
                
                # Filter out junk lines from vertically aligned PDF headers
                vertical_headers = {"過", "本", "去", "會", "30日", "賽", "(", "事", "所", ")", "有 以來", "會 賽", "(所", "有", "本"}
                
                for line in lines:
                    # Ignore the page numbers/footers mixed in, and vertical headers
                    if re.match(r'^[A-Z]\d+$', line) or line.startswith('預計走位圖') or line in vertical_headers:
                        continue
                        
                    formatted_line = re.sub(r'\s{2,}', ' | ', line)
                    formatted_lines.append(formatted_line)
                    
                print('\n'.join(formatted_lines))
            else:
                print("(本賽日無相關資料或未能成功提取)")
            print("\n")

    except Exception as e:
         print(f"Error parsing PDF: {e}")
    finally:
         if os.path.exists(pdf_path):
             os.remove(pdf_path)

if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python extract_starter_pdf.py YYYYMMDD", file=sys.stderr)
        sys.exit(1)
        
    date_input = sys.argv[1]
    
    # Handle potentially bad input like YYYY-MM-DD
    date_str = date_input.replace("-", "").replace("/", "")
    
    if len(date_str) != 8 or not date_str.isdigit():
        print(f"Error: Date must be in YYYYMMDD format. Got: '{date_input}' -> '{date_str}'", file=sys.stderr)
        sys.exit(1)
        
    pdf_file = download_pdf(date_str)
    extract_pdf_data(pdf_file, date_str)
