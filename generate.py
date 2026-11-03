import urllib.request
import urllib.parse
import urllib.error
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

# Znane skróty typów zajęć (w, ćwiczenia, laboratorium, projekt, egzamin...)
KNOWN_TYPES = {
    'w','W','ć','Ć','c','C','L','l','P','p','E','e','S','s','Z','z',
    'Ep','ep','Zp','zp','Lab','lab','ćw','Ćw','CW','cw','Cw',
}

def is_type_token(tok):
    """Czy token wygląda na typ zajęć (w, ć, L, Ep, Lab…)."""
    if not tok: return False
    if not re.match(r'^[A-Za-ząćęłńóśźżĄĆĘŁŃÓŚŹŻ]+$', tok):
        return False
    if tok in KNOWN_TYPES:
        return True
    if len(tok) <= 2:
        return True
    return False

def format_title_and_desc(lines):
    """
    lines = [tytuł, (typ), sala, prowadzący, ...]
    Zwraca (tytuł_z_typem, opis).
    Np. ['Ed','w','204 136','Hof'] -> ('Ed (w)', '204 136\\nHof')
        ['Ing']                    -> ('Ing', '')
    """
    if not lines:
        return '', ''
    title = lines[0]
    rest = lines[1:]
    if rest and is_type_token(rest[0]):
        title = f'{title} ({rest[0]})'
        rest = rest[1:]
    return title, '\n'.join(rest)

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
                  '(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
    'Accept-Language': 'pl-PL,pl;q=0.9,en;q=0.8',
    'Cache-Control': 'no-cache',
    'Pragma': 'no-cache',
    'Upgrade-Insecure-Requests': '1',
    'Connection': 'keep-alive',
}

PROXIES = [
    ('direct',       lambda u: u),
    ('allorigins',   lambda u: 'https://api.allorigins.win/raw?url=' + urllib.parse.quote(u, safe='')),
    ('corsproxy.io', lambda u: 'https://corsproxy.io/?url=' + urllib.parse.quote(u, safe='')),
    ('codetabs',     lambda u: 'https://api.codetabs.com/v1/proxy?quest=' + urllib.parse.quote(u, safe='')),
]

def try_fetch(url):
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read()

def decode(raw):
    try:
        html = raw.decode('utf-8')
        if '\ufffd' not in html:
            return html
    except Exception:
        pass
    try:
        return raw.decode('windows-1250')
    except Exception:
        return raw.decode('utf-8', errors='replace')

def fetch_html():
    last_err = None
    for name, build in PROXIES:
        try:
            print(f'[fetch] próbuję: {name}…')
            raw  = try_fetch(build(URL))
            html = decode(raw)
            if len(html) > 500 and 'pon.' in html:
                print(f'[fetch] OK {name}: {len(raw)} B, {len(html)} znaków')
                return html
            print(f'[fetch] X {name}: nie wygląda na plan ({len(html)} znaków)')
        except Exception as e:
            print(f'[fetch] X {name}: {e}')
            last_err = e
    raise RuntimeError(f'Wszystkie źródła zawiodły: {last_err}')

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
                try:
                    dd = int(parts[0])
                except ValueError:
                    continue
                current.append({'day': day, 'date': (year, mn, dd), 'slots': []})
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
                d['slots'].append({'time': tk, 'lines': lines})
    return result

def to_ics(days):
    L = ['BEGIN:VCALENDAR','VERSION:2.0','PRODID:-//Plan WAT//PL',
         'CALSCALE:GREGORIAN','METHOD:PUBLISH','X-WR-CALNAME:Plan zajęć WAT 2026/2027']
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    uid, count = 0, 0
    for d in days:
        y, m, dd = d['date']
        for slot in d['slots']:
            lines = slot['lines']
            if not lines: continue
            base_title = lines[0]
            if re.match(r'^(P\.św|Św\.|ŚwA)$', base_title): continue
            if slot['time'] not in TIME_RANGES: continue

            title, description = format_title_and_desc(lines)

            s, e = TIME_RANGES[slot['time']]
            dtstart = f'{y}{m:02d}{dd:02d}T{s.replace(":","")}00'
            dtend   = f'{y}{m:02d}{dd:02d}T{e.replace(":","")}00'
            desc = description.replace('\\','\\\\').replace(';','\\;').replace(',','\\,').replace('\n','\\n')
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
