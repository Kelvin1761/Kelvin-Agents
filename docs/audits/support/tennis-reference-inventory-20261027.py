"""Read cached workbook price coverage; never certify quote capture clocks."""
import argparse
from datetime import datetime,timedelta
import hashlib
import json
from pathlib import Path
from xml.etree import ElementTree as E
from zipfile import ZipFile

NS={'m':'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}
BOOKS={'Pinnacle':('PSW','PSL'),'Bet365':('B365W','B365L'),'Betfair':('BFEW','BFEL')}


def inventory(path):
    with ZipFile(path) as z:
        strings=[''.join(t.itertext()) for t in E.fromstring(z.read('xl/sharedStrings.xml')).findall('m:si',NS)] if 'xl/sharedStrings.xml' in z.namelist() else []
        rows=E.fromstring(z.read('xl/worksheets/sheet1.xml')).findall('m:sheetData/m:row',NS)
        def read(row):
            values={}
            for c in row:
                v=c.find('m:v',NS)
                values[c.get('r').rstrip('0123456789')]=(strings[int(v.text)] if c.get('t')=='s' and v is not None else ''.join(c.find('m:is',NS).itertext()) if c.get('t')=='inlineStr' else v.text if v is not None else None)
            return values
        header=read(rows[0]);columns={v:k for k,v in header.items()};counts={k:0 for k in BOOKS};dates=[]
        book=E.fromstring(z.read('xl/workbook.xml')).find('m:workbookPr',NS)
        epoch=datetime(1904,1,1) if book is not None and book.get('date1904') in ('1','true') else datetime(1899,12,30)
        for row in rows[1:]:
            data=read(row)
            for name,fields in BOOKS.items():
                try:valid=all(float(data.get(columns.get(field)) or 0)>1 for field in fields)
                except ValueError:valid=False
                counts[name]+=int(valid)
            try:dates.append((epoch+timedelta(days=float(data.get(columns.get('Date'))))).date().isoformat())
            except (TypeError,ValueError,OverflowError):pass
    return {'path':str(path),'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'rows':len(rows)-1,
            'paired_prices':counts,'first_match_date':min(dates) if dates else None,'latest_match_date':max(dates) if dates else None,
            'future_or_wrong_year_rows':sum(day[:4]!='2026' or day>'2026-10-27' for day in dates),
            'latest_plausible_2026_date':max((day for day in dates if day[:4]=='2026' and day<='2026-10-27'),default=None),
            'quote_capture_clock_verified':False,'qualification':'Historical workbook; date-only rows cannot establish synchronous, executable pre-match reference prices.'}


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--directory',required=True);p.add_argument('--output',required=True);a=p.parse_args()
    rows=[inventory(path) for path in sorted(Path(a.directory).glob('*2026.xlsx'))]
    Path(a.output).write_text(json.dumps(rows,indent=2)+'\n');print(json.dumps(rows,indent=2))


if __name__=='__main__':main()
