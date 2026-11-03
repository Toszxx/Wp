import urllib.request
import re
from datetime import datetime, timezone

URL = 'https://ioe.wat.edu.pl/plany/wat_ioe/IOE24HX1S0.htm'
OUTPUT = 'plan.ics'

TIME_RANGES = {
    '1-2': ('08:00', '09:35'), '3-4': ('09:50', '11:25'),
    '5-6': ('11:40', '13:15'), '7-8': ('13:30', '15:05'),
    '9-10': ('16:00', '17:35'), '11-12': ('17:50', '19:25'),
    '13-14': ('19:40', '21:15'),
}
MONTHS = {'I':1,'II':2,'III':3,'IV':4,'V':5,'VI':6,
          'VII':7,'VIII':8,'IX':9,'X':10,'XI':11,'XII':12}

def fetch_html():
    req = urllib.request.Request(URL, headers={'User-Agent': 'Mozilla/5.0'})
    with urllib.request.urlopen(req, timeout=30) as r:
        raw = r.read()
    try:
        html = raw.decode('utf-8')
        if '\ufffd' in html:
            html = raw.decode('windows-1250')
    except Exception:
        html = raw.decode('windows-1250', errors='replace')
    return html

def find_main_table(soup):
    best, best_score = None, 0
    for t in soup.find_all('table'):
        score = 0
        for tr in t.find_all('tr'):
            cells = tr.find_all(['td','th'])
            if len(cells) < 3: continue
            d  = cells[0].get_text(strip=True).replace(' ', '')
            h  = cells[1].get_text(strip=True).replace(' ', '')
            dt = cells[2].get_text(strip=True)
            if not re.match(r'^(pon|wt|śr|czw|pt|sob|niedz)\.?$', d, re.I): continue
            if re.match(r'^\d+-\d+$', h): score += 20
            elif not h and re.match(r'^\d{1,2}\s+[IVX]+$', dt): score += 10
        if score > best_score:
            best_score, best = score, t
    return best if best_score >= 50 else None

def parse_table(table):
    current, result = [], []
    for tr in table.find_all('tr'):
        cells = tr.find_all(['td','th'])
        if len(cells) < 3: continue
        day   = cells[0].get_text(strip=True)
        sec   = cells[1].get_text(strip=True)
        third = cells[2].get_text(strip=True)

        if not sec and re.match(r'^\d{1,2}\s+[IVX]+$', third):
            current = []
            for c in cells[2:]:
                ds = c.get_text(strip=True)
                parts = ds.split()
                if len(parts) < 2: continue
                mn = MONTHS.get(parts[1].upper())
                if not mn: continue
                year = 2026 if mn >= 9 else 2027
                current.append({'day': day, 'date': (year, mn, int(parts[0])), 'slots': []})
            result.extend(current)
            continue

        tk = sec.replace(' ', '')
        if re.match(r'^\d+-\d+$', tk):
            for i, d in enumerate(current):
                idx = i + 2
                if idx >= len(cells): break
                cell = cells[idx]
                for br in cell.find_all('br'): br.replace_with('\n')
                lines = [l.strip() for l in cell.get_text().split('\n') if l.strip()]
                if not lines: continue
                d['slots'].append({
                    'time': tk, 'title': lines[0],
                    'description': '\n'.join(lines[1:])
                })
    return result

def to_ics(days):
    L = ['BEGIN:VCALENDAR','VERSION:2.0','PRODID:-//Plan WAT//PL',
         'CALSCALE:GREGORIAN','METHOD:PUBLISH','X-WR-CALNAME:Plan zajęć WAT 2026/2027']
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    uid, count = 0, 0
    for d in days:
        y, m, dd = d['date']
        for slot in d['slots']:
            title = slot['title']
            if re.match(r'^(P\.św|Św\.|ŚwA)$', title): continue
            if slot['time'] not in TIME_RANGES: continue
            s, e = TIME_RANGES[slot['time']]
            dtstart = f'{y}{m:02d}{dd:02d}T{s.replace(":","")}00'
            dtend   = f'{y}{m:02d}{dd:02d}T{e.replace(":","")}00'
            desc = slot['description'].replace('\\','\\\\').replace(';','\\;').replace(',','\\,').replace('\n','\\n')
            ttl  = title.replace('\\','\\\\').replace(';','\\;').replace(',','\\,')
            L += ['BEGIN:VEVENT',
                  f'UID:wat-{y}{m:02d}{dd:02d}-{slot["time"].replace("-","")}-{uid}@github',
                  f'DTSTAMP:{stamp}', f'DTSTART:{dtstart}', f'DTEND:{dtend}',
                  f'SUMMARY:{ttl}']
            if desc: L.append(f'DESCRIPTION:{desc}')
            L.append('END:VEVENT')
            uid += 1; count += 1
    L.append('END:VCALENDAR')
    return '\r\n'.join(L) + '\r\n', count

def main():
    from bs4 import BeautifulSoup
    soup  = BeautifulSoup(fetch_html(), 'html.parser')
    table = find_main_table(soup)
    if not table: raise SystemExit('Nie znaleziono tabeli planu')
    days = parse_table(table)
    ics, count = to_ics(days)
    with open(OUTPUT, 'w', encoding='utf-8', newline='') as f:
        f.write(ics)
    print(f'OK: {count} zdarzeń z {len(days)} dni')

if __name__ == '__main__':
    main()
