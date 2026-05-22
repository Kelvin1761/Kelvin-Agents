import os
os.environ.setdefault('PYTHONUTF8', '1')
import sys
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
import requests
import pdfplumber
import re
from datetime import datetime

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

def extract_pdf_data(pdf_path, date_str):
    print(f"=== HKJC 全日出賽馬匹資料 ({date_str}) ===\n")
    print("【AI 閱讀指南 / AI Reading Guide】")
    print("This document contains the FULL text extraction of the PDF, including foreign horse (外隊馬) form records, sectional speeds, race ranks, etc.")
    print("對於騎師榜及練馬師榜，因表格排版，真實欄位順序如下 (Columns in order):")
    print("姓名 | [今季總計] 冠 亞 季 殿 出賽 勝率 上名率 獎金 | [田草] 冠 亞 季 殿 出賽 | [泥地] 冠 亞 季 殿 出賽 | [谷草] 冠 亞 季 殿 出賽 | [近30日] 冠 出賽 | [歷年] 冠 出賽\n")
    
    vertical_headers = {"過", "本", "去", "會", "30日", "賽", "(", "事", "所", ")", "有 以來", "會 賽", "(所", "有", "本"}
    
    try:
        with pdfplumber.open(pdf_path) as pdf:
            for i, page in enumerate(pdf.pages):
                print(f"## --- PAGE {i+1} ---")
                text = page.extract_text()
                if text:
                    lines = [line.strip() for line in text.split('\n') if line.strip()]
                    formatted_lines = []
                    for line in lines:
                        if re.match(r'^[A-Z]\d+$', line) or line.startswith('預計走位圖') or line in vertical_headers:
                            continue
                        formatted_line = re.sub(r'\s{2,}', ' | ', line)
                        formatted_lines.append(formatted_line)
                    print('\n'.join(formatted_lines))
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
