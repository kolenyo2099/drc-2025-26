#!/usr/bin/env python3
"""Build geo.js, data.js, faction_review.csv from ../*.json. stdlib only. Source files are only read."""
import json, csv, re, os, collections, datetime as dt
HERE = os.path.dirname(os.path.abspath(__file__)); SRC = os.path.dirname(HERE)
J = lambda f: json.load(open(os.path.join(SRC, f), encoding='utf-8'))
dump = lambda o: json.dumps(o, ensure_ascii=False, separators=(',', ':'))

# ---------------- geo ----------------
BB = (25.5, -6.5, 31.5, 2.0)
def coords_iter(g):
    def walk(c):
        if c and isinstance(c[0], (int, float)): yield c
        else:
            for x in c: yield from walk(x)
    yield from walk(g['coordinates'])
def hits(f):
    pts = list(coords_iter(f['geometry']))
    x0, x1 = min(p[0] for p in pts), max(p[0] for p in pts); y0, y1 = min(p[1] for p in pts), max(p[1] for p in pts)
    return x0 <= BB[2] and x1 >= BB[0] and y0 <= BB[3] and y1 >= BB[1]
def simp(ring, tol):
    out = [[round(ring[0][0], 4), round(ring[0][1], 4)]]
    for p in ring[1:-1]:
        q = [round(p[0], 4), round(p[1], 4)]
        if abs(q[0]-out[-1][0]) >= tol or abs(q[1]-out[-1][1]) >= tol: out.append(q)
    out.append([round(ring[-1][0], 4), round(ring[-1][1], 4)])
    return out if len(out) >= 4 else None
def geom(g, tol):
    polys = [g['coordinates']] if g['type'] == 'Polygon' else g['coordinates']
    res = []
    for poly in polys:
        rings = [r for r in (simp(r, tol) for r in poly) if r]
        for i, r in enumerate(rings):  # d3 wants exterior rings clockwise (planar area < 0), holes counter-clockwise
            a = sum(p[0]*q[1] - q[0]*p[1] for p, q in zip(r, r[1:]))
            if (a < 0) != (i == 0): r.reverse()
        if rings: res.append(rings)
    return {'type': 'MultiPolygon', 'coordinates': res}
def load_geo():
    R = lambda f: json.load(open(os.path.join(HERE, 'geo_raw', f), encoding='utf-8'))['features']
    def pick(feats, namef, keep=lambda n: True, tol=0.004, extra=lambda n: {}):
        out = []
        for f in feats:
            n = namef(f['properties'])
            if f['geometry'] and keep(n) and hits(f):
                out.append({'type': 'Feature', 'properties': dict(n=n, **extra(n)), 'geometry': geom(f['geometry'], tol)})
        return {'type': 'FeatureCollection', 'features': out}
    kivu = lambda n: n in ('North Kivu', 'South Kivu')
    return {
        'provinces': pick(R('adm1.geojson'), lambda p: p['shapeName'], tol=0.006, extra=lambda n: {'kivu': 1} if kivu(n) else {}),
        'territories': pick(R('adm2.geojson'), lambda p: p['shapeName'], tol=0.006),
        'countries': pick(R('countries.geojson'), lambda p: p['NAME'], lambda n: n in ('Rwanda', 'Burundi', 'Uganda', 'Tanzania'), tol=0.006),
        'lakes': pick(R('lakes.geojson'), lambda p: p['name'], lambda n: n in ('Lake Kivu', 'Lake Tanganyika', 'Lake Edward', 'Lake Albert'), tol=0.004),
    }

# ---------------- dates ----------------
skips = collections.Counter()
def pdate(s, end=False, what='?'):
    """YYYY | YYYY-MM | YYYY-MM-DD (suffixes / 'A/B' ranges tolerated: first token for start, last for end) -> ISO date or None"""
    if not s: return None
    toks = re.findall(r'\d{4}(?:-\d{1,2}(?:-\d{1,2})?)?', str(s))
    if not toks: skips[what] += 1; return None
    m = re.match(r'(\d{4})(?:-(\d{1,2}))?(?:-(\d{1,2}))?', toks[-1] if end else toks[0])
    y, mo, d = int(m[1]), m[2] and int(m[2]), m[3] and int(m[3])
    try:
        if mo is None: return dt.date(y, 12, 31).isoformat() if end else dt.date(y, 1, 1).isoformat()
        if d is None:
            if end: return (dt.date(y + (mo == 12), mo % 12 + 1, 1) - dt.timedelta(1)).isoformat()
            return dt.date(y, mo, 1).isoformat()
        return dt.date(y, mo, d).isoformat()
    except ValueError: skips[what] += 1; return None

# ---------------- factions ----------------
M23 = r'm23|afc|frn|rdf|rwand|twirwaneho|mrdp|red tabara|red-tabara|rebel'
KIN = r'fardc|wazalendo|fdnb|burundi|fdlr|vdp|volontaires|pareco|updf|ugandan|congolese|government|drc army|drc provincial|ma[iï]-ma[iï]|mdlc|fdcc|regular forces|soldiers'
def who(h):
    h = h.lower(); best = (10**9, None)
    for name, rx in (('m23', M23), ('kin', KIN)):
        m = re.search(rx, h)
        if m and m.start() < best[0]: best = (m.start(), name)
    return best[1]
# Exact-held-string overrides (state[, left]) and per-id overrides. Reviewed by hand against faction_review.csv.
HELD_OV = {
 'M23 (contested by FARDC/Wazalendo attacks)': ('m23',), 'M23/AFC (contested by Wazalendo)': ('m23',),
 'AFC/M23 area contested by Wazalendo': ('m23',),
 'AFC/M23 to the north, FARDC to the south': ('contested',),
 'FARDC and Wazalendo (centre); AFC/M23 (surrounding hills)': ('contested',),
 'FARDC and wazalendo in the centre; AFC/M23 on the surrounding hills': ('contested',),
 'FARDC and allied Wazalendo (per Actualite.cd, conditional); AFC/M23 held two positions on the Kashebere axis': ('contested',),
 'FARDC, FDNB and Wazalendo (south of Kamanyola); AFC/M23 up to Kamanyola': ('contested',),
 'FARDC and Wazalendo (Ruzizi plain beyond Uvira); rebels M23 (Nyangezi–Kamanyola axis)': ('contested',),
 'MRDP/Twirwaneho (per residents); FARDC (per army claim)': ('contested',),
 'Malimba and Rubarati: AFC/M23-Twirwaneho; Masango-centre: Wazalendo and the Congolese army, per the civil-society source': ('contested',),
 'M23 says it holds; Governor Purusi says FARDC and allies hold': ('contested',),
 'lower part Wazalendo; upper part AFC/M23, according to local sources cited by Actualite.cd': ('contested',),
 'divided: FARDC south, AFC-M23 north (per Radio Okapi local sources)': ('contested',),
 'disputed: shared, or FARDC-Wazalendo and Burundian army, per different sources': ('contested',),
 'frontline of M23/AFC; Uvira under government control; Kamanyola under M23/AFC control (MSF)': ('contested',),
 'M23 and RDF (offensive launched against FARDC)': ('m23',),
 'AFC/M23 (FARDC at Kipupu, Mulima, Mukera, Fizi-Centre)': ('m23',),
 'AFC/M23 (last position at Bangwi); Wazalendo at the Pemba escarpments; FARDC at Kasekezi and Ngalula, per M\'massa Etùba': ('m23',),
 'DRC army (80%) per Muhindo Nzangi; M23 only some peripheral areas per Nzangi': ('kin',),
 'FARDC (soldiers fleeing through the Grande Barrière crossing)': ('vacated', 'kin'),
 'FARDC/Wazalendo/Burundian forces (fleeing)': ('vacated', 'kin'),
 'government coalition, reportedly abandoned': ('vacated', 'kin'),
 'Wazalendo (retreated outside Uvira town or to their bases)': ('vacated', 'kin'),
 'AFC/M23 (troops partly withdrawing; police arriving, per anonymous source)': ('m23',),
 'AFC/M23 (announced intent to withdraw)': ('m23',),
 'FARDC announced withdrawal': ('kin',),
 'not held by AFC-M23 per Kivutimes (threatened)': ('kin',),
 'positions of the parties reportedly unchanged': ('contested',),
 'Wazalendo (per Paluku Kuliumbwa); UPDF presence disputed (per civil society)': ('kin',),
 'Wazalendo temporarily, then AFC/M23': ('m23',), 'Wazalendo, then FARDC (per BBC Gahuza)': ('kin',),
 'Wazalendo, then FARDC (returning to the city)': ('kin',), 'Twirwaneho, then lost to DRC forces (per Igihe)': ('kin',),
 'AFC-M23 (Nov 2025); FARDC and PARECO-Wazalendo (Dec 2025); AFC-M23 (Feb-Mar 2026), per KT Press': ('m23',),
 'M23-AFC (returned after temporary Wazalendo advance)': ('m23',),
 'half of village briefly occupied by M23 then pushed back by Wazalendo MDLC, per Radio Okapi': ('kin',),
 'FARDC and Wazalendo after AFC/M23 seized it on 10 July': ('m23',),
 'FRN rebels (as Actualite.cd names them); FARDC and Wazalendo seek to retake': ('contested',),
 'AFC/M23 (per AFC/M23 and UMUSEKE sources)': ('m23',),
}
ID_OV = {}   # id -> (state[, left]); none needed beyond HELD_OV after review
def classify(o):
    h, ch = o['held'], o['change']
    if o['id'] in ID_OV: r, how = ID_OV[o['id']], 'override:id'
    elif h in HELD_OV: r, how = HELD_OV[h], 'override:held'
    else:
        r = None
        if ch == 'contested' or re.search(r'contested|shared|half of village|frontline|divided|disputed', h, re.I): r, how = ('contested',), 'rule1'
        elif ch == 'withdrew' or re.search(r'no armed presence|vacated|\(withdrew\)', h, re.I): r, how = ('vacated', who(h)), 'rule2'
        else:
            w = who(h); r, how = ((w,), 'rule3') if w else (('unknown',), 'rule3')
    return (r[0], r[1] if len(r) > 1 else None, how)


# ---------------- UCDP GED (external, ungraded) ----------------
UCDP_CSV = os.path.join(SRC, 'ucdp', 'gedevents_490_2025-2026.csv')
UBOX = (27.0, -5.0, 30.0, 0.9)  # lon0, lat0, lon1, lat1: the map frame
SIDE = {'Government of DR Congo (Zaire)': 'DRC government', 'Government of Rwanda': 'Rwanda', 'Government of Uganda': 'Uganda', 'Government of Burundi': 'Burundi'}
def uside(x): return SIDE.get(x, x)
def uactors(a, b):
    t = a + ' ' + b; out = []
    if re.search(r'AFC|M23|Rwanda', t): out.append('AFC/M23 and Rwanda')
    if re.search(r'Government of DR Congo|Military Forces of the Democratic Republic|VDP|Wazalendo|FDLR', t): out.append('FARDC and allies')
    if re.search(r'IS\b|ADF|URDPC|CODECO|Mobondo|self-defense|CRP|Mai-Mai|Twirwaneho', t) and not out == ['AFC/M23 and Rwanda']: out.append('Other armed groups')
    return out or ['Not attributed']
def hav(a, b, c, d):
    import math; r = math.pi / 180; x = math.sin((c - a) * r / 2) ** 2 + math.cos(a * r) * math.cos(c * r) * math.sin((d - b) * r / 2) ** 2
    return 12742 * math.asin(math.sqrt(x))
def ucdp(events):
    """Return (ucdp events, review rows). Drops: imprecise/outside frame, exact repeats, matches with a curated event (+-3 d, <=10 km, same family).
    Same day + place + dyad rows are merged and their deaths summed. Curated events are never altered."""
    rows = list(csv.DictReader(open(UCDP_CSV, encoding='utf-8'))); review = []; st = collections.Counter(); seen = set(); groups = {}
    P = lambda s: dt.date.fromisoformat(s[:10]).toordinal()
    fam = {'military_operation', 'attack_on_civilians'}
    for x in rows:
        lat, lon = float(x['latitude']), float(x['longitude']); why = None
        if int(x['where_prec']) > 3: why = 'imprecise location (UCDP where_prec>3)'
        elif not (UBOX[0] <= lon <= UBOX[2] and UBOX[1] <= lat <= UBOX[3]): why = 'outside map frame'
        else:
            key = (x['date_start'], x['date_end'], lat, lon, x['dyad_new_id'], x['best'], x['source_article'])
            if key in seen: why = 'exact repeat within UCDP'
            seen.add(key)
        if not why:
            s, e = P(x['date_start']), P(x['date_end'])
            m = next((c for c in events if c['cat'] in fam and hav(lat, lon, c['lat'], c['lon']) <= 10 and P(c['s']) - 3 <= e and P(c['e']) + 3 >= s and P(c['e']) - P(c['s']) <= 31), None)
            if m: why = 'already in curated records: ' + m['id']
        review.append([x['id'], x['date_start'], x['where_description'], x['dyad_name'], x['best'], 'dropped' if why else 'kept', why or ''])
        if why: st[why.split(':')[0]] += 1; continue
        groups.setdefault((x['date_start'], x['date_end'], lat, lon, x['dyad_new_id'], x['type_of_violence']), []).append(x)
    out = []
    for g in groups.values():
        x = g[0]; t = x['type_of_violence']; A, B = uside(x['side_a']), uside(x['side_b'])
        n = lambda k: sum(int(r[k] or 0) for r in g)
        best, low, high, civ = n('best'), n('low'), n('high'), n('deaths_civilians')
        where = ', '.join(dict.fromkeys(r['where_description'] for r in g if r['where_description'])) or x['adm_2'] or x['adm_1']
        ds, de = x['date_start'], x['date_end']
        if t == '3': title = f"{A} violence against civilians, {where}"; cats = ['attack_on_civilians']; actor_line = f"{A} against civilians"
        else: title = f"Clashes: {A} vs {B}, {where}"; cats = ['armed_clash', 'military_operation']; actor_line = f"{A} vs {B}"
        if best: title += f" ({best} killed)"
        srcs = []
        for r in g:
            for o, d, h in zip(r['source_office'].split(';'), r['source_date'].split(';'), r['source_headline'].split(';')):
                if (o, d, h) not in srcs: srcs.append((o.strip(), d.strip(), h.strip()))
        when = ds if ds == de else ds + ' to ' + de
        out.append({'id': 'UCDP-' + x['id'], 'title': title, 's': ds, 'e': de, 'lat': round(float(x['latitude']), 4), 'lon': round(float(x['longitude']), 4),
                    'cat': cats[0], 'cats': cats, 'actor': 'Not attributed', 'acts': uactors(x['side_a'], x['side_b']), 'attr': 'ucdp', 'grade': 'U',
                    'place_text': where + (', ' + x['adm_1'].replace(' province', '') if x['adm_1'] else ''), 'when': when, 'actor_line': actor_line, 'claims': [], 'counter': [],
                    'geo': 'UCDP location precision ' + x['where_prec'] + ' (1 = exact site, 2 = within 25 km, 3 = district)', 'catlabels': [],
                    'u': {'name': 'UCDP', 'best': best, 'low': low, 'high': high, 'civ': civ, 'clarity': x['event_clarity'], 'src': srcs[:6], 'n': len(g)}})
    return out, review, st

ACLED_CSV = os.path.join(SRC, 'acled', 'acled_events_2025-09-13_to_2025-09-19.csv')
def acled(events):
    """Event-level ACLED export (one week only; the other ACLED file is weekly province totals and cannot be mapped).
    Keeps Battles, Explosions/Remote violence, Violence against civilians at precision<=2; drops matches (+-3 d, <=10 km) with any event already present."""
    rows = list(csv.DictReader(open(ACLED_CSV, encoding='utf-8-sig'))); out = []; review = []; st = collections.Counter(); P = lambda s: dt.date.fromisoformat(s[:10]).toordinal()
    fam = {'armed_clash', 'military_operation', 'attack_on_civilians'}
    for x in rows:
        lat, lon, t = float(x['latitude']), float(x['longitude']), x['event_type']; why = None
        if t not in ('Battles', 'Explosions/Remote violence', 'Violence against civilians'): why = 'not violence (' + t + ')'
        elif int(x['geo_precision']) > 2: why = 'imprecise location'
        elif not (UBOX[0] <= lon <= UBOX[2] and UBOX[1] <= lat <= UBOX[3]): why = 'outside map frame'
        else:
            d = P(x['event_date']); m = next((c for c in events if fam & set(c['cats']) and hav(lat, lon, c['lat'], c['lon']) <= 10 and P(c['s']) - 3 <= d and P(c['e']) + 3 >= d and P(c['e']) - P(c['s']) <= 31), None)
            if m: why = 'already present: ' + m['id']
        review.append([x['event_id_cnty'], x['event_date'], x['location'], x['actor1'], x['fatalities'], 'dropped' if why else 'kept', why or ''])
        if why: st[why.split(':')[0].split(' (')[0]] += 1; continue
        a = x['actor1']; civ = t == 'Violence against civilians'; f = int(x['fatalities'] or 0)
        cats = ['attack_on_civilians'] if civ else ['armed_clash', 'military_operation']
        title = f"{x['sub_event_type']}: {a.split(' (')[0].split(': ')[-1]}, {x['location']}" + (f" ({f} killed)" if f else '')
        out.append({'id': 'ACLED-' + x['event_id_cnty'], 'title': title, 's': x['event_date'], 'e': x['event_date'], 'lat': round(lat, 4), 'lon': round(lon, 4), 'cat': cats[0], 'cats': cats,
                    'actor': 'Not attributed', 'acts': uactors(a + ' ' + x['assoc_actor_1'], ''), 'attr': 'acled', 'grade': 'U', 'place_text': ', '.join(v for v in (x['location'], x['admin2'], x['admin1']) if v),
                    'when': x['event_date'], 'actor_line': a + (' (' + x['assoc_actor_1'] + ')' if x['assoc_actor_1'] else ''), 'claims': [], 'counter': [],
                    'geo': 'ACLED location precision ' + x['geo_precision'] + ' (1 = exact site, 2 = near)', 'catlabels': [],
                    'u': {'name': 'ACLED', 'best': f, 'low': f, 'high': f, 'civ': 0, 'clarity': '', 'src': [(x['source'], x['event_date'], x['notes'][:360])], 'n': 1}})
    return out, review, st

# ---------------- build ----------------
GR = {'A': 3, 'B': 2, 'C': 1}
CATS = ['armed_clash', 'attack_on_civilians', 'sexual_violence', 'detention_abduction', 'displacement_humanitarian', 'health_care_access',
        'looting_or_destruction', 'military_operation', 'forced_recruitment', 'de_facto_governance']
def main():
    geo = load_geo()
    open(os.path.join(HERE, 'geo.js'), 'w').write('window.GEO=' + dump(geo) + ';')
    print('geo.js bytes', os.path.getsize(os.path.join(HERE, 'geo.js')), {k: len(v['features']) for k, v in geo.items()})
    control, records, claims = J('control.json'), J('records.json'), J('claims.json')
    src = {r['id']: r['sources'] for r in csv.DictReader(open(os.path.join(SRC, 'claims.csv'), encoding='utf-8'))}
    need = set(); st_count = collections.Counter(); nogeo = 0; nodes = {}; review = []
    for o in control:
        state, left, how = classify(o)
        dd = pdate(o['d'], what='control date')
        review.append([o['id'], o['d'], o['place'], o['change'], o['held'], state, left or '', how])
        st_count[state] += 1
        if dd is None: continue
        if not o.get('xy'): nogeo += 1; continue
        if state == 'unknown': continue
        k = (round(o['xy'][0], 4), round(o['xy'][1], 4))
        n = nodes.setdefault(k, {'lat': k[0], 'lon': k[1], 'names': collections.Counter(), 'pv': collections.Counter(), 'tr': collections.Counter(), 'obs': []})
        n['names'][o['pn']] += 1; n['pv'][o['pv']] += 1; n['tr'][o['tr']] += 1
        n['obs'].append({'date': dd, 'd1': pdate(o['d1'], True, 'control d1') if o.get('d1') else None, 'state': state, 'left': left, 'held': o['held'],
                         'change': o['change'], 'grade': o['g'], 'dp': o['dp'], 'claimId': o['id'], 'place': o['place'], 'raw': o['d']})
        need.add(o['id'])
    out_nodes = []
    for n in nodes.values():
        # same-day tie: a withdrawal by X is demoted if another holder (not X) is reported that day; then higher grade, then contested
        hold = {(x['date'], x['state']) for x in n['obs']}
        dem = lambda x: x['state'] == 'vacated' and any((x['date'], s) in hold and s != x['left'] for s in ('m23', 'kin'))
        n['obs'].sort(key=lambda x: (x['date'], not dem(x), GR.get(x['grade'], 0), x['state'] == 'contested'))
        out_nodes.append({'name': n['names'].most_common(1)[0][0], 'lat': n['lat'], 'lon': n['lon'], 'tr': n['tr'].most_common(1)[0][0],
                          'pv': n['pv'].most_common(1)[0][0], 'obs': n['obs']})
    out_nodes.sort(key=lambda n: (-len(n['obs']), n['name']))
    # events
    events = []; ev_count = collections.Counter()
    for r in records.values():
        if r.get('kind') != 'event' or r.get('lat') is None or r.get('lon') is None: continue
        cats = [c['type'] for c in r['categories']]
        q = [c for c in cats if c in CATS]
        if not q: continue
        s = pdate(r['start'], what='event start'); e = pdate(r['end'] or r['start'], True, 'event end')
        if not s: continue
        e = max(e or s, s)
        core = r['claims']['core']; need.update(core); need.update(c['claim'] for c in r['counterclaims'] if c.get('claim'))
        ev_count[q[0]] += 1
        events.append({'id': r['id'], 'title': r['title'], 's': s, 'e': e, 'lat': r['lat'], 'lon': r['lon'], 'cat': q[0], 'cats': list(dict.fromkeys(cats)),
                       'actor': r['actor'], 'attr': r['attribution'], 'grade': r['best_grade'], 'place_text': r['place_text'], 'when': r['when_text'],
                       'actor_line': r['actor_line'], 'claims': core, 'counter': [{'c': c.get('claim'), 't': c['text']} for c in r['counterclaims']],
                       'geo': r.get('geo_basis')})
        events[-1]['catlabels'] = [c['label'] for c in r['categories']]
    uev, urev, ust = ucdp(events); events += uev
    aev, arev, ast = acled(events); events += aev
    print('acled: kept', len(aev), 'dropped', dict(ast))
    with open(os.path.join(HERE, 'acled_review.csv'), 'w', newline='', encoding='utf-8') as f:
        w = csv.writer(f); w.writerow(['acled_id', 'date', 'place', 'actor1', 'fatalities', 'status', 'reason']); w.writerows(arev)
    print('ucdp: kept', len(uev), 'after merging; dropped', dict(ust))
    with open(os.path.join(HERE, 'ucdp_review.csv'), 'w', newline='', encoding='utf-8') as f:
        w = csv.writer(f); w.writerow(['ucdp_id', 'date', 'place', 'dyad', 'best_deaths', 'status', 'reason']); w.writerows(urev)
    events.sort(key=lambda e: (e['s'], e['id']))
    cl = {}
    for i in need:
        c = claims.get(i)
        if c: cl[i] = {'s': c['s'], 'g': c['g'], 'src': src.get(i, '')}
    # key moments
    def moments(name):
        """capture = first grade-A m23 obs after the last Kinshasa-side obs preceding M23's last hold; end = first grade-A non-m23 obs after that last hold"""
        n = next((n for n in out_nodes if n['name'].lower() == name), None)
        if not n: return None, None
        o = n['obs']; ms = [i for i, x in enumerate(o) if x['state'] == 'm23']
        if not ms: return None, None
        lm = ms[-1]; lk = max([i for i, x in enumerate(o[:lm]) if x['state'] == 'kin' or x['left'] == 'kin'], default=-1)
        cap = next((x['date'] for x in o[lk + 1:lm + 1] if x['state'] == 'm23' and x['grade'] == 'A'), o[ms[0]]['date'])
        end = next((x['date'] for x in o[lm + 1:] if x['state'] != 'm23' and x['grade'] == 'A'), None)
        return cap, end
    mo = []
    for nm, lab in (('goma', 'M23 takes Goma'), ('bukavu', 'M23 takes Bukavu'), ('uvira', 'M23 enters Uvira')):
        c, e = moments(nm)
        if c: mo.append({'date': c, 'label': lab})
        if nm == 'uvira' and e: mo.append({'date': e, 'label': 'M23 leaves Uvira'})
    print('key moments', mo)
    alld = [o['date'] for n in out_nodes for o in n['obs']] + [e['s'] for e in events]
    # statements feed: official statements from DRC institutions only
    EXCL = re.compile(r'civil society|supporters|versus local sources|former vice|security sources|ngo', re.I)
    sts = []; st_skip = st_filt = 0; raw_st = J('statements.json')
    pf = os.path.join(HERE, 'people.json'); pj = json.load(open(pf, encoding='utf-8')) if os.path.exists(pf) else {'aliases': {}, 'people': {}}
    for r in raw_st:
        pr = r['pr'] or ''
        if not ((r['party'] or '').startswith('Kinshasa (DRC government') or pr in ('Democratic Republic of the Congo (Government)', 'Democratic Republic of the Congo', 'Congolese parliament (North Kivu deputy)')) or EXCL.search(pr):
            continue
        st_filt += 1
        d = pdate(r['d'], what='statement date'); c = claims.get(r['id'])
        if not d or not c or len(r['d']) == 4: st_skip += 1; continue  # year-only dates are too vague for a dated feed
        sts.append({'id': r['id'], 'd': d, 'dp': r['dp'], 'person': r['person'], 'role': r['role'], 'party': pr, 'pid': pj['aliases'].get(r['person']) if r['person'] else None,
                    'sk': r['sk'], 'k': r['k'], 'tr': r['tr'], 'pv': r['pv'], 'text': c['s'], 'g': c['g'], 'src': src.get(r['id'], '')})
    sts.sort(key=lambda x: (x['d'], x['id']))
    people = {x['pid']: pj['people'][x['pid']] for x in sts if x['pid'] and x['pid'] in pj['people']}
    print('statements passing filter', st_filt, '-> embedded', len(sts), '(dropped undated/year-only', st_skip, ') no person', sum(1 for x in sts if not x['person']),
          'people.json', 'found' if os.path.exists(pf) else 'MISSING', 'people used', len(people), 'with photo', sum(1 for p in people.values() if p.get('photo')))
    meta = {'min': min(alld), 'max': max(alld), 'nogeo': nogeo, 'nobs': sum(len(n['obs']) for n in out_nodes), 'cats': CATS}
    s = 'window.DATA=' + dump({'nodes': out_nodes, 'events': events, 'claims': cl, 'moments': mo, 'meta': meta, 'statements': sts, 'people': people}) + ';'
    open(os.path.join(HERE, 'data.js'), 'w', encoding='utf-8').write(s)
    with open(os.path.join(HERE, 'faction_review.csv'), 'w', newline='', encoding='utf-8') as f:
        w = csv.writer(f); w.writerow(['id', 'date', 'place', 'change', 'held', 'state', 'left', 'rule_or_override']); w.writerows(review)
    print('states', dict(st_count)); print('skipped (no coords)', nogeo, 'unparseable dates', dict(skips))
    print('overrides used (held-string):', sum(1 for r in review if r[7] == 'override:held'), 'rows;', len({r[4] for r in review if r[7] == 'override:held'}), 'distinct strings')
    print('nodes', len(out_nodes), 'obs on map', meta['nobs'], 'range', meta['min'], meta['max'])
    print('events', len(events), dict(ev_count)); print('claims', len(cl), 'data.js bytes', len(s.encode()))
main()
