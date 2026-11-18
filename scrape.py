"""Builds showtimes.json for showtimes.html. Run by GitHub Actions. Read-only, low volume.
Jarosław: the cinema's own ticket shop (room + seats). Rzeszów: Filmweb's Multikino listing
(multikino.pl blocks automated access, so it is not touched)."""
import json, re, time, datetime as dt
from zoneinfo import ZoneInfo
import requests
from bs4 import BeautifulSoup

S = requests.Session()
S.headers['User-Agent'] = 'Mozilla/5.0 (personal showtimes page; low volume)'
MSI = 'http://jaroslaw.kinonabiegunach.pl/MSI/'
FW = 'https://www.filmweb.pl/showtimes/Rzesz%C3%B3w/Multikino-1507'

def soup(url):
    time.sleep(1)
    r = S.get(url, timeout=30); r.raise_for_status()
    return BeautifulSoup(r.text, 'html.parser')

def clean(t):
    return re.sub(r'\s+(?:(?:2D|3D)\s*)?(?:DUBBING|NAPISY)$', '', t.strip(), flags=re.I)

def jaroslaw():
    dre = re.compile(r'date=(\d{4}-\d\d-\d\d)')
    def links(sp):
        return {m.group(1) for a in sp.find_all('a', href=True) if (m := dre.search(a['href']))}
    days = links(soup(MSI + 'mvc'))
    shows = {}
    def parse_day(d):
        sp = soup(f'{MSI}mvc/pl?sort=Date&date={d}&datestart=0')
        days.update(links(sp))  # the day page may link to later days too
        n = 0
        title = lang = ''; mins = None
        for el in sp.find_all(['h3', 'li', 'a']):
            txt = el.get_text(' ', strip=True)
            if el.name == 'h3':
                title = clean(txt)
            elif el.name == 'li':
                if txt.lower().startswith('wersja:'): lang = txt.split(':', 1)[1].strip()
                elif txt.lower().startswith('czas:'): mins = int(re.sub(r'\D', '', txt) or 0) or None
            else:
                m = re.search(r'event_id=(\d+)', el.get('href', ''))
                if m and re.fullmatch(r'\d{1,2}:\d\d', txt):
                    i = m.group(1); n += 1
                    shows[i] = dict(id=i, date=d, time=txt.zfill(5), title=title, lang=lang, min=mins,
                                    url=f'{MSI}OrderTickets.aspx?event_id={i}&typetran=0')
        return n
    done = set()
    while days - done:
        d = min(days - done); done.add(d)
        parse_day(d)
    # the day strip on the main page can be shorter than the real programme: probe the days after the last one
    last = dt.date.fromisoformat(max(done)); empty = 0
    for n in range(1, 15):
        d = (last + dt.timedelta(days=n)).isoformat()
        try: found = parse_day(d)
        except Exception: found = 0
        empty = 0 if found else empty + 1
        if empty >= 2: break
    for s in shows.values():
        try:
            t = soup(s['url']).get_text(' ', strip=True)
        except Exception:
            continue
        for key, rx in (('room', r'Sala\s*(\d+)'), ('free', r'Dostępnych miejsc:\s*(\d+)'), ('total', r'Miejsc łącznie:\s*(\d+)')):
            m = re.search(rx, t)
            if m: s[key] = int(m.group(1))
    return sorted(shows.values(), key=lambda s: (s['date'], s['time']))

def rzeszow():
    today = dt.datetime.now(ZoneInfo('Europe/Warsaw')).date()
    shows = []
    for n in range(7):
        d = (today + dt.timedelta(days=n)).isoformat()
        film = ''
        for el in soup(FW + (f'?day={n}' if n else '')).find_all(['h2', 'a']):
            if el.name == 'h2':
                film = el.get_text(' ', strip=True); continue
            h = el.get('href', '')
            if 'rezerwacja-biletow' not in h: continue
            bits = [x.strip() for x in el.find_all_next(string=True, limit=8) if x.strip()]
            blob = ' '.join([el.get_text(' ', strip=True)] + bits[:2])
            m = re.search(r'\b(\d{1,2}:\d\d)\b', blob)
            if not (film and m): continue
            lang = 'DUB' if 'dubbing' in blob else 'NAP' if 'napisy' in blob else ''
            shows.append(dict(date=d, time=m.group(1).zfill(5), title=film, lang=lang, url=h.split('?')[0]))
    return shows

def main():
    try: out = json.load(open('showtimes.json')).get('cinemas', {})
    except Exception: out = {}
    for key, name, city, fn in (('jaroslaw', 'Kino na Biegunach', 'Jarosław', jaroslaw),
                                ('rzeszow', 'Multikino Millennium Hall', 'Rzeszów', rzeszow)):
        try:
            shows = fn(); assert shows, 'no showings found'
            out[key] = dict(name=name, city=city, shows=shows)
        except Exception as e:
            print(key, 'failed, keeping old data:', e)
    json.dump(dict(updated=dt.datetime.now(dt.timezone.utc).isoformat(timespec='seconds'), cinemas=out),
              open('showtimes.json', 'w'), ensure_ascii=False, indent=0)

if __name__ == '__main__':
    main()
