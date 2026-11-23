#!/usr/bin/env python3
"""Build care.js: funded care for survivors of sexual violence (from sift's drc-sgbv-funding project) and the dated
funding events for the timeline. Stdlib only; sift's database is only read.

A project is shown when its funding record (OCHA FTS, IATI, World Bank) has at least one claim the checker kept, and
its text (not its donor's or recipient's name) names a place in North or South Kivu that this map knows: a place on
the map, else a territory (drawn at the territory's centre). A project naming several places has a ring at each.
Records with the same title are one project with several funding flows. Records naming only a province or the country are left out: they are
not where the care is."""
import json, os, re, sqlite3, unicodedata

HERE = os.path.dirname(os.path.abspath(__file__))
SIFT = os.path.expanduser('~/Documents/serper test/sift/projects/drc-sgbv-funding')
KIVU_TERR = {'Beni', 'Butembo', 'Oïcha', 'Goma', 'Lubero', 'Masisi', 'Nyiragongo', 'Rutshuru', 'Walikale', 'Bukavu', 'Fizi',
             'Baraka', 'Idjwi', 'Kabare', 'Kalehe', 'Kamituga', 'Mwenga', 'Shabunda', 'Uvira', 'Walungu'}

# The four funding events on the timeline: each date and wording is a claim the checker kept, with its page.
EVENTS = [
    {'date': '2025-02-12', 'label': 'US aid freeze halts care for survivors',
     'text': 'PHR: the executive order freezing US foreign aid for 90 days has halted the supply of lifesaving medical care in eastern DRC.',
     'url': 'https://phr.org/news/u-s-foreign-aid-freeze-disrupts-lifesaving-health-care-services-for-survivors-of-sexual-violence-midst-deadly-conflict-in-democratic-republic-of-the-congo-phr/',
     'src': 'Physicians for Human Rights, 12 Feb 2025'},
    {'date': '2025-04-03', 'label': 'FONAREV–UN partnership, US$12 million',
     'text': 'FONAREV and the UN signed a one-year partnership worth 12,034,067 dollars for North and South Kivu; it expired on 3 April 2026.',
     'url': 'https://beto.cd/fonarev-589-victimes-indemnisees-taux-indemnisation-non-calcule/',
     'src': 'beto.cd; Financial Afrik, 7 Apr 2025'},
    {'date': '2025-07-01', 'label': 'US cancels the post-rape kit contract',
     'text': 'Reuters: the Trump administration cancelled a contract to supply emergency kits for rape survivors in Congo; CARE says it supplied around 100,000 kits.',
     'url': 'https://www.youtube.com/watch?v=1o_vtK8laLk',
     'src': 'Reuters video, 1 Jul 2025; CARE'},
    {'date': '2025-12-31', 'label': 'CERF: US$2 million to UNFPA',
     'text': 'CERF approved US$2,000,000 for UNFPA (CERF-COD-25-RR-FPA-38760) for gender-based violence and reproductive health needs in areas hit by the M23 crisis.',
     'url': 'https://cerf.un.org/what-we-do/allocation/2025/agency/6',
     'src': 'UN CERF allocations 2025'},
]


def fold(s):
    s = unicodedata.normalize('NFKD', s or '')
    return ' '.join(re.sub(r'[^\w]+', ' ', ''.join(c for c in s if not unicodedata.combining(c)).lower()).split())


def load(name):
    t = open(os.path.join(HERE, name), encoding='utf-8').read()
    return json.loads(t[t.index('{'):t.rindex('}') + 1])


def centre(geom):
    pts = [p for poly in geom['coordinates'] for p in poly[0]]
    return round(sum(p[1] for p in pts) / len(pts), 4), round(sum(p[0] for p in pts) / len(pts), 4)


def fields(text):
    out = {}
    for line in text.splitlines():
        k, _, v = line.partition(': ')
        if v and k[:1].isupper() and len(k) < 30:
            out.setdefault(k, v)
    return out


def period(f, text):
    """-> (start, end, how). Project dates when the record gives them; else the year(s) the money was for."""
    m = re.search(r'Project Start Date: (\d{4}-\d\d-\d\d) - Project End Date: (\d{4}-\d\d-\d\d)', text)
    if m:
        return m[1], m[2], 'project dates'
    if f.get('Start'):
        return f['Start'], f.get('End') or f['Start'][:4] + '-12-31', 'project dates'
    if f.get('Board approval'):
        c = f.get('Closing', '')
        mc = re.match(r'(\d+)/(\d+)/(\d{4})', c)
        return f['Board approval'], f'{mc[3]}-{int(mc[1]):02}-{int(mc[2]):02}' if mc else f['Board approval'][:4] + '-12-31', 'approval to closing'
    years = re.findall(r'\d{4}', f.get('Usage years', ''))
    if years:
        return min(years) + '-01-01', max(years) + '-12-31', 'year the funding was for'
    d = f.get('Decision date') or f.get('Date')
    return (d, d[:4] + '-12-31', 'year of the decision') if d else (None, None, None)


def main():
    geo, data = load('geo.js'), load('data.js')
    places = []   # (folded name, display name, lat, lon, territory)
    for n in data['nodes']:
        nm = n['name'].split(' (')[0].replace(' centre', '')
        places.append((fold(nm), n['name'], n['lat'], n['lon'], n['tr']))
    for f in geo['territories']['features']:
        if f['properties']['n'] in KIVU_TERR:
            places.append((fold(f['properties']['n']), f['properties']['n'] + ' territory', *centre(f['geometry']), None))
    db = sqlite3.connect(f'file:{SIFT}/sift.db?mode=ro', uri=True)
    rows = db.execute("""SELECT p.nurl, p.url, p.text_sha, p.title FROM pages p WHERE p.method='record'
        AND EXISTS (SELECT 1 FROM claims c WHERE c.nurl=p.nurl AND c.verdict IN ('keep','narrow'))""").fetchall()
    projects, skipped = {}, 0
    for nurl, url, sha, title in rows:
        text = open(f'{SIFT}/pages/text/{sha}.md', encoding='utf-8').read()
        f = fields(text)
        where = fold(' '.join(l for l in text.splitlines()   # not the organisations' names: "Caritas Kasongo" is no place
                              if not re.match(r'(Donor|Recipient|Reporting organisation|Implementing agency|Plan|Reference|Project): ', l)))
        hits = [p for p in places if re.search(rf'\b{re.escape(p[0])}\b', where)]
        hits = [p for p in hits if p[4] or not any(q[4] and fold(q[4].split(' (')[0]) == p[0] for q in hits)]   # a town, not also its territory
        s, e, how = period(f, text)
        if not hits or not s:
            skipped += 1
            continue
        desc = re.sub(r'^Allocation Type:[^\n]*\n', '', text.split('Description: ', 1)[1]).split('\n')[0] if 'Description: ' in text else ''
        name = (f.get('Title') or f.get('Name') or desc or title).strip()
        p = projects.setdefault(fold(name), {'title': name[:220], 's': s, 'e': e, 'how': how, 'flows': [],
                                             'places': [{'n': h[1], 'lat': h[2], 'lon': h[3]} for h in hits]})
        p['s'], p['e'] = min(p['s'], s), max(p['e'], e, s)
        p['flows'].append({'donor': f.get('Donor') or f.get('Reporting organisation') or ('World Bank' if nurl.startswith('worldbank') else ''),
                           'recipient': f.get('Recipient') or f.get('Implementing agency') or '',
                           'amount': f.get('Amount') or f.get('Commitment') or '', 'status': f.get('Status', ''),
                           'url': url, 'src': f.get('Source', '').replace('OCHA Financial Tracking Service', 'OCHA FTS')})
    projects = sorted(projects.values(), key=lambda x: (x['s'], x['title']))
    for i, p in enumerate(projects):
        p['id'] = 'care%d' % i
    s = 'window.CARE=' + json.dumps({'projects': projects, 'events': EVENTS}, ensure_ascii=False, separators=(',', ':')) + ';'
    open(os.path.join(HERE, 'care.js'), 'w', encoding='utf-8').write(s)
    from collections import Counter
    print('records with a kept claim', len(rows), '-> projects on the map', len(projects),
          'from', sum(len(p['flows']) for p in projects), 'records; no Kivu place or no date', skipped)
    print(Counter(x['n'] for p in projects for x in p['places']).most_common(25))
    print('active in 2025-2026:', sum(p['e'] >= '2025-01-01' for p in projects))


if __name__ == '__main__':
    main()
