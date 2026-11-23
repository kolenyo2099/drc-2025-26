#!/usr/bin/env python3
"""Build srv.js and srv_review.csv for srv.html, the map focused on sexual and reproductive violence. Stdlib only;
every source file is only read.

strand: which of the page's three threads a record belongs to, read from its title and core claims (never from
        context claims, which describe the surroundings of an event and not the event):
          sv       sexual violence: rape, sexual slavery, forced marriage, forced pregnancy, forced nudity
          care     access to care: post-rape kits, services for survivors, maternity and obstetric care
          justice  justice and impunity: trials, convictions, and escapes of people convicted of these crimes
tags:   finer detail shown in the record's panel (children, men and boys, detention, slavery, forced pregnancy).
terr:   for records with no map point, the territories their core claims name (at most three), so that the record
        can sit at the centre of its territory and not only in the province count.
stm:    statements by any party whose topic is sexual violence, shaped like data.js statements.
Every rule match is written to srv_review.csv with the words that triggered it, to be checked by hand."""
import csv, json, os, re
from care import KIVU_TERR, HERE, fold, centre, load

RAPE = r'\brap(e|ed|es|ing|ist|ists)\b|gang[- ]rap|sexual(ly)? (violence|assault|abuse|exploit|slave|purposes)|sexual and gender|sex(ual)? slave|forced "?marriage|forced pregnan|stripped naked|forced nudity|body search'
STRAND = {
    'sv': RAPE,
    'care': r'post-exposure|\bPEP\b|post-rape|sexual violence survivors|rape kits?|kits? for (rape )?survivors|survivors?[^.]{0,80}\b(care|services|treatment|treated)\b|\b(care|services|treat\w*)\b[^.]{0,60}survivors? of sexual'
            r'|maternit|obstetr|childbirth|g[ai]v(e|ing) birth|midwi|pregnant wom|newborn|neonat|caesarean|gyn[ae]+colog|fistula|contracepti|family planning|abortion',
    'justice': r'(tribunal|court|trial|hearing|sentenc|convict|prosecut|impunity|escape)[^.]{0,160}(\brap|sexual)|(\brap|sexual)[^.]{0,160}(tribunal|court|trial|hearing|sentenc|convict|prosecut|impunity)',
}
NOT_AN_ACT = r'post-rape|survivors of sexual violence|sexual violence survivors|report on conflict-related sexual violence'
DROP = {('REC-0309', 'sv')}   # checked by hand in srv_review.csv: the record is about punishments M23 imposed, sexual violence among the offences punished
TAGS = {
    'Children among the victims': r'(girls?|minors?|child(ren)?|\d+-(year|month)-old)[^.]{0,80}(\brap|sexual)|(\brap|sexual)[^.]{0,80}(girls?|minors?|child(ren)?|\d+-(year|month)-old)',
    'Men or boys among the victims': r'against men|men and boys|\bman\b[^.]{0,40}(stripped|raped)|rape of (a |two |three )?(man|men|boys?)\b|LGBT',
    'In detention': r'(detention|detain|prison|\bcell\b|enclosure)[^.]{0,120}(\brap|sexual)|(\brap|sexual)[^.]{0,120}(detention|detain|prison|\bcell\b)',
    'Sexual slavery or forced marriage': r'sex(ual)? slave|forced "?marriage|sexual purposes|sexually exploit',
    'Forced pregnancy': r'forced pregnan',
}


def main():
    d = json.load(open(os.path.join(HERE, '..', 'report-data.json'), encoding='utf-8'))['data']
    data, geo = load('data.js'), load('geo.js')
    rc = {c['claim']: c for c in d['claims']}
    recs = {}   # id -> (title, text of title + core claims, tagged sexual violence by the researchers, core claim ids)
    for r in d['records_all']:
        recs[r['id']] = (r['title'], ' '.join([r['title']] + [rc[c]['text'] for c in r['core_claims'] if c in rc]), 'Sexual violence' in r['categories'], r['core_claims'])
    for e in data['events']:
        if e['id'] not in recs:
            recs[e['id']] = (e['title'], ' '.join([e['title']] + [data['claims'][c]['s'] for c in e['claims'] if c in data['claims']]),
                             'sexual_violence' in e['cats'] or e['title'].startswith('Sexual violence:'), [])
    strand, tags, review = {}, {}, []
    for rid, (title, text, tagged, _) in sorted(recs.items()):
        hit = {}
        for s, rx in STRAND.items():
            # naming the survivors, the kits or a UN report on sexual violence is about care, and is not itself a report of an act
            m = re.search(rx, re.sub(NOT_AN_ACT, lambda x: ' ' * len(x[0]), text, flags=re.I) if s == 'sv' else text, re.I)
            if (rid, s) in DROP:
                m = None
            if m:
                hit[s] = text[max(0, m.start() - 40):m.end() + 40]
        if tagged and 'sv' not in hit:
            hit['sv'] = '(tagged sexual violence by the researchers)'
        if not hit:
            continue
        strand[rid] = [s for s in STRAND if s in hit]
        t = [k for k, rx in TAGS.items() if re.search(rx, text, re.I)]
        if t:
            tags[rid] = t
        for s in strand[rid]:
            review.append([rid, s, 'yes' if tagged else '', title, hit[s].replace('\n', ' '), '; '.join(t)])

    cen = {fold(f['properties']['n']): (f['properties']['n'], *centre(f['geometry'])) for f in geo['territories']['features'] if f['properties']['n'] in KIVU_TERR}
    terr = {}
    for r in d['records_all']:
        if r['id'] in strand and r['map_point'] != 'yes':
            names = dict.fromkeys(fold(rc[c]['territory']) for c in r['core_claims'] if c in rc and rc[c].get('territory'))
            got = [cen[n] for n in names if n in cen]
            if 0 < len(got) <= 3:
                terr[r['id']] = got

    src = {s['source']: s for s in d['sources']}
    al = json.load(open(os.path.join(HERE, 'people.json'), encoding='utf-8'))['aliases']
    stm = []
    for s in d['statements_all']:
        m = re.match(r'\d{4}-\d\d-\d\d', s['date'] or '')
        if 'Sexual violence' not in (s['topics'] or []) or not m:   # a statement with no day cannot sit on a dated feed
            continue
        o = src.get((rc.get(s['claim'], {}).get('sources') or [''])[0], {})
        stm.append({'id': s['claim'], 'd': m[0], 'dp': 'day' if s['date_precision'] == 'day' else 'approx', 'person': s['person'], 'role': s['role'],
                    'party': s['party'].replace('Kinshasa (DRC government and FARDC)', 'DRC government and FARDC'), 'pid': al.get(s['person']),
                    'sk': s['setting'], 'k': 'denial_or_counterclaim' if 'Denial or counterclaim' in s['stances'] else ', '.join(s['stances']).lower(),
                    'tr': '', 'pv': '', 'text': s['text'], 'g': s['grade'], 'src': o.get('outlet', ''), 'ev': s['events']})
    stm.sort(key=lambda x: (x['d'], x['id']))

    out = {'strand': strand, 'tags': tags, 'terr': terr, 'stm': stm}
    open(os.path.join(HERE, 'srv.js'), 'w', encoding='utf-8').write('window.SRV=' + json.dumps(out, ensure_ascii=False, separators=(',', ':')) + ';')
    with open(os.path.join(HERE, 'srv_review.csv'), 'w', newline='', encoding='utf-8') as f:
        w = csv.writer(f)
        w.writerow(['id', 'strand', 'tagged_sexual_violence_by_researchers', 'title', 'words_that_matched', 'detail_tags'])
        w.writerows(review)
    from collections import Counter
    mapped = {e['id'] for e in data['events']}
    print('records with a strand', len(strand), Counter(s for v in strand.values() for s in v), '| with a dot', len(set(strand) & mapped),
          '| placed by territory', len(terr), '| added by the rules, not tagged by researchers', sum(not recs[i][2] for i in strand))
    print('detail tags', Counter(t for v in tags.values() for t in v)); print('statements', len(stm), Counter(x['party'] for x in stm))


if __name__ == '__main__':
    main()
