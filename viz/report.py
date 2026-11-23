#!/usr/bin/env python3
"""Build report.js from ../report-data.json (the focused report's data file, v1.1, data as of 2026-10-28). Stdlib only.

What goes on the map, and why (the rest of the file stays off it):
- unplaced: violation records with no map point. They name only a province ("North Kivu"), so they have no dot;
  without them the map hides most sexual-violence reports. Counted per province; records naming both provinces count
  in both; the 8 naming "Eastern DRC", the whole country or Burundi are left out.
- hk: kind of attack on health care, per record.
- disc: facts on which sources disagree, per record, each version kept.
- acc: which parties gave an account of the event (claim ids), and which were searched for and not found.
Names of people, leads and the command/sanctions tables are not used: being named is not a finding."""
import calendar, json, os, re

HERE = os.path.dirname(os.path.abspath(__file__))
CAT = {'Attacks on civilians': 'attack_on_civilians', 'Health care': 'health_care_access', 'Sexual violence': 'sexual_violence',
       'Detention and abduction': 'detention_abduction', 'Looting and destruction': 'looting_or_destruction',
       'Forced recruitment': 'forced_recruitment'}
PROV = {'North Kivu': ['nk'], 'South Kivu': ['sk'], 'Uvira (city)': ['sk'], 'North Kivu and South Kivu': ['nk', 'sk']}
SIDE = {'AFC/M23 and Rwandan forces': 'AFC/M23 and Rwanda', 'FARDC, Wazalendo, Burundian forces': 'FARDC and allies',
        'Other armed groups (ADF, others)': 'Other armed groups'}   # the map's buckets; build.py's records agree on all but 5
def day(x, end=False):
    """'2025' / '2025-03' / '2025-03-14' -> a full date: the first day of the span, or its last with end=True."""
    if len(x) == 10:
        return x
    if len(x) == 4:
        return x + ('-12-31' if end else '-01-01')
    y, m = map(int, x.split('-'))
    return f'{x}-{(calendar.monthrange(y, m)[1] if end else 1):02}'


short = lambda p: 'Kinshasa' if p.startswith('Kinshasa') else p


def load(name):
    t = open(os.path.join(HERE, name), encoding='utf-8').read()
    return json.loads(t[t.index('{'):t.rindex('}') + 1])


def main():
    d = json.load(open(os.path.join(HERE, '..', 'report-data.json'), encoding='utf-8'))
    D, mapped = d['data'], {e['id'] for e in load('data.js')['events']}
    recs = {r['id']: r for r in D['records_all']}
    need = set()

    unplaced = []
    for r in D['records_all']:
        if r['id'] in mapped or r['map_point'] == 'yes' or r['region'] not in PROV or not r['start']:
            continue
        need.update(r['core_claims'])
        unplaced.append({'id': r['id'], 'title': r['title'], 's': day(r['start']), 'e': day(r['end'] or r['start'], True), 'as_given': [r['start'], r['end']],
                         'when': r['date_precision'], 'place': r['place'], 'pv': PROV[r['region']],
                         'cats': [CAT[c] for c in r['categories'] if c in CAT], 'grade': r['grade'],
                         'actor': SIDE.get(r['side_alleged'], 'Not attributed'), 'attr': {'Attribution disputed': 'disputed', 'No perpetrator stated': 'not_stated'}.get(r['side_alleged'], 'stated'), 'actor_line': r['perpetrator_as_alleged'], 'claims': r['core_claims']})

    hk = {r['id']: r['health_care_kinds'] for r in D['records_all'] if r['health_care_kinds']}

    disc = {}
    for x in D['discrepancies']:
        for rid in x['records']:
            disc.setdefault(rid, []).append({'title': x['title'], 'type': x['type'],
                                             'sides': [re.sub(r'\s*\[[^\]]*\]\s*$', '', s) for s in x['sides']]})

    acc = {}
    for a in D['accounts']:
        spoke = {short(k): v for k, v in a.items() if isinstance(v, list) and v and k != 'no_statement_found'}
        if spoke:
            acc[a['event']] = {'spoke': spoke}
            need.update(c for v in spoke.values() for c in v)
    for x in D['nostatement']:
        acc.setdefault(x['event'], {}).setdefault('silent', []).append({'party': short(x['party']), 'langs': x['languages'],
                                                                       'n': x['searches']})

    src = {s['source']: s for s in D['sources']}
    claims = {}
    for c in D['claims']:
        if c['claim'] in need:
            s = src.get((c['sources'] or [''])[0], {})
            claims[c['claim']] = {'t': c['text'], 'g': c['grade'], 'o': s.get('outlet', ''), 'u': s.get('url', ''),
                                  'd': s.get('date', '')}

    out = {'about': {'version': d['report_version'], 'as_of': d['data_as_of']},
           'unplaced': unplaced, 'hk': hk, 'disc': disc, 'acc': acc, 'claims': claims}
    open(os.path.join(HERE, 'report.js'), 'w', encoding='utf-8').write(
        'window.REPORT=' + json.dumps(out, ensure_ascii=False, separators=(',', ':')) + ';')
    from collections import Counter
    print('unplaced', len(unplaced), Counter(p for u in unplaced for p in u['pv']),
          'sexual violence', sum('sexual_violence' in u['cats'] for u in unplaced))
    print('health kinds', len(hk), 'on map', len(set(hk) & mapped), '| disagreements on', len(disc), 'records, on map',
          len(set(disc) & mapped), '| accounts', len(acc), 'on map', len(set(acc) & mapped), '| claims', len(claims))
    assert all(c in claims for u in unplaced for c in u['claims']), 'unplaced record cites a claim not in the file'


if __name__ == '__main__':
    assert (day('2025'), day('2025', True), day('2024-02', True), day('2025-03-14')) == ('2025-01-01', '2025-12-31', '2024-02-29', '2025-03-14')
    main()
