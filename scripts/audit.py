"""Read-only audits, full-corpus evaluation and reproducible source reconciliation."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tai_engine.engine import Engine, ROOT, remove_tone, values
from collections import defaultdict, Counter
import json
import hashlib
import unicodedata as ud
import runpy


def save(name, value):
    folder = ROOT / 'reports'; folder.mkdir(exist_ok=True)
    (folder / name).write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')


def audit_rules(engine):
    chars, romans = defaultdict(list), defaultdict(list)
    for group, rule in engine.rules['consonants'].items():
        for cls in ('low', 'high'):
            chars[rule[cls]].append({'rule':f'consonants.{group}.{cls}', 'readings':values(rule['ipa'])})
            for r in values(rule['ipa']): romans[r].append(rule[cls])
    for rid, rule in engine.vowels.items():
        for c in rule['pattern'].replace('...', ''):
            chars[c].append({'rule':rid, 'readings':rule['readings']})
        for r in rule['readings']: romans[r].append(rule['pattern'])
    for c, rule in engine.tones.items(): chars[c].append({'rule':'tones.'+c,'metadata':rule})
    for name, rule in engine.rules['special_symbols'].items():
        chars[rule['symbol']].append({'rule':'special_symbols.'+name,'metadata':rule})
    unicode_inventory = [{'character':c,'codepoint':f'U+{ord(c):04X}', 'unicode_name':ud.name(c,'UNASSIGNED'),
                          'rules':refs} for c,refs in chars.items()]
    secondary = runpy.run_path(str(ROOT/'scripts/rules.py'))['TAI_VIET_RULES']
    tertiary = runpy.run_path(str(ROOT/'scripts/taiviet_rules.py'))
    conflicts = []
    for c, item in engine.consonants.items():
        for source, other in [('rules.py',secondary['consonants'].get(c,{}).get('ipa')),
                              ('taiviet_rules.py',tertiary['ALL_CONSONANTS'].get(c))]:
            if other and other not in item['readings']:
                conflicts.append(dict(character=c,source=source,group_rules=item['readings'],other=other))
    return dict(rule_version=engine.version, unicode_inventory=unicode_inventory,
        overlapping_characters=[x for x in unicode_inventory if len(x['rules'])>1],
        reverse_ambiguities={r:sorted(set(cs)) for r,cs in romans.items() if len(set(cs))>1},
        non_single_readings={c:r for c,r in engine.consonants.items() if len(r['readings'])>1},
        cross_file_consonant_conflicts=conflicts,
        special_context_rules=engine.rules['special_consonant_rules'],
        not_reversible=['Unmarked tone mapping absent from group_rules',
            'Special V medial prose lacks ordered assembly patterns',
            'pos_modifier has syllable readings but no context decomposition',
            'pos_right ꪽ constraint is unclear', 'Zero initial carrier ꪮ is not specified',
            'High ꫁ is approximately nặng; no exact acoustic equivalence',
            'Tone serialization order is observed in corpus, not specified by group_rules',
            'Latin o and U+AAC4 (unassigned) are literal keys in group_rules'],
        tokenizer_used_by_engine=False)


def audit_tokenizer(engine):
    path=ROOT/'data/taiviet_tokenizer.json'
    raw=json.loads(path.read_text(encoding='utf-8'))
    model=raw['model']; vocab=model['vocab']; counts=Counter(vocab.values())
    tai_chars={c for w in engine.words for c in w if '\uaa80'<=c<='\uaadf'}
    result=dict(sha256=hashlib.sha256(path.read_bytes()).hexdigest(),model_type=model['type'],
        normalizer=raw.get('normalizer'),pre_tokenizer=raw.get('pre_tokenizer'),decoder=raw.get('decoder'),
        vocabulary_size=len(vocab), duplicate_ids=[i for i,n in counts.items() if n>1],
        absent_standalone_characters=sorted(tai_chars-set(vocab)), used_by_engine=False)
    try:
        from tokenizers import Tokenizer
        tokenizer=Tokenizer.from_file(str(path))
        failures=[]; unknown=[]
        for word in engine.words:
            enc=tokenizer.encode(word,add_special_tokens=False)
            decoded=tokenizer.decode(enc.ids,skip_special_tokens=False)
            if decoded!=word: failures.append(dict(original=word,decoded=decoded,tokens=enc.tokens))
            if model.get('unk_token') in enc.tokens: unknown.append(word)
        result.update(runtime_load=True, tested_unique_words=len(engine.words), decode_exact_failures=len(failures),
                      unk_words=len(unknown),failure_examples=failures[:100],unknown_examples=unknown[:100])
    except (ImportError,Exception) as exc: result.update(runtime_load=False,error=str(exc))
    return result


def reconcile_xlsx(engine):
    import openpyxl
    workbook=openpyxl.load_workbook(ROOT/'data/TaiViet_dataframe.xlsx',read_only=True,data_only=True)
    iterator=iter(workbook.active.values); headers=next(iterator)
    rows=[dict(zip(headers,r)) for r in iterator]
    workbook.close()
    byid={str(r['_id']):r for r in engine.records}
    missing=[]; differences=[]; extras=[]
    for i,row in enumerate(rows,2):
        doc=byid.get(str(row['IDNTN']))
        if not doc: missing.append({'excel_row':i,'data':row}); continue
        for x,j in [('TuNgu','tu_thai'),('PhienAm','phien_am'),('NghiaTiengViet','nghia_tieng_viet')]:
            if row.get(x)!=doc.get(j): differences.append(dict(excel_row=i,id=doc['_id'],field=x,xlsx=row.get(x),json=doc.get(j)))
        for field in ['MoTa2','MoTa3','MoTa4']:
            if row.get(field): extras.append(dict(excel_row=i,id=doc['_id'],field=field,raw=row[field]))
    save('xlsx_rows_original.json',rows)
    save('xlsx_not_in_json.json',missing)
    save('xlsx_additional_examples_raw.json',extras)
    return dict(xlsx_rows=len(rows),json_rows=len(engine.records),xlsx_not_in_json=len(missing),
        differences=differences,additional_example_fields=len(extras),
        policy='XLSX is separately archived in source_records; missing rows and free-text examples need review, not silent colon splitting.')


def evaluate(engine):
    words=list(engine.words); pairs=list(dict.fromkeys((r['tu_thai'],r['phien_am']) for r in engine.records))
    parse_ok=round_ok=ambiguous=0; failures=[]; inference=defaultdict(Counter); evidence=defaultdict(list)
    for word in words:
        p=engine.parse_tai_word(word)
        if p['supported']:
            parse_ok+=1
            if engine.compose_tai_word(p)==word: round_ok+=1
            ambiguous+=any(len(s['candidates'])>1 for s in p['syllables'])
        else: failures.append(dict(word=word,syllables=[s['original'] for s in p['syllables'] if not s['candidates']]))
    forward={w:engine.tai_to_romanization(w) for w in words}
    reverse={r:engine.romanization_to_tai(r) for _,r in pairs}
    hits=Counter(); pair_failures=[]
    for w,r in pairs:
        f=[x['romanization'] for x in forward[w]['candidates']]
        b=[x['tai'] for x in reverse[r]['candidates']]
        hits['tai_to_romanization']+=r in f
        for k in (1,3,5): hits[f'top_{k}']+=w in b[:k]
        hits['top_k_limit_100']+=w in b
        if r not in f or w not in b: pair_failures.append(dict(tai=w,romanization=r,forward_match=r in f,reverse_match=w in b))
        ws,rs=w.split(),r.split()
        if len(ws)!=len(rs): continue
        for tw,rr in zip(ws,rs):
            candidates=engine.parse_syllable(tw)
            if len(candidates)!=1: continue
            a=candidates[0]; _,tone=remove_tone(rr)
            key=f"{a['initial_class']}|{a['tone_mark'] or 'no_mark'}|{a['final'] or 'open'}"
            inference[key][tone]+=1
            evidence[key].append(dict(tai=tw,romanization=rr,tone=tone))
    inferred=[]
    for key,c in sorted(inference.items()):
        dominant,n=c.most_common(1)[0]
        inferred.append(dict(pattern=key,proposed_tone=dominant,support=n,total=sum(c.values()),
            confidence=n/sum(c.values()),distribution=dict(c),status='inferred_not_enabled',
            counterexamples=[x for x in evidence[key] if x['tone']!=dominant][:30]))
    save('inferred_tone_rules.json',inferred); save('engine_parse_failures.json',failures)
    save('engine_pair_failures.json',pair_failures)
    return dict(unique_words=len(words),unique_pairs=len(pairs),parse_success=parse_ok,round_trip_success=round_ok,
        structural_ambiguity=ambiguous,counts=dict(hits),
        percentages={k:round(v/len(pairs)*100,3) for k,v in hits.items()},
        parse_percent=round(parse_ok/len(words)*100,3),round_trip_percent=round(round_ok/len(words)*100,3),
        generation_truncated_pairs=sum(reverse[r]['truncated'] or forward[w]['truncated'] for w,r in pairs),
        methodology='Exact Unicode comparison on unique pairs, rule-generated candidates only; dictionary-frequency ranking uses the same corpus, so ranking is in-sample, NOT held-out accuracy. Unsupported cases count as failures. Top-1 tie breaks lexically, not confidence. Missing tone rules are not inferred into production.')


def main():
    engine=Engine()
    for filename,func in [('rules_audit.json',audit_rules),('tokenizer_audit.json',audit_tokenizer),
                          ('source_reconciliation.json',reconcile_xlsx),('engine_metrics.json',evaluate)]:
        result=func(engine); save(filename,result)
        print(filename, 'written',flush=True)
    print(json.dumps(json.loads((ROOT/'reports/engine_metrics.json').read_text(encoding='utf-8')),ensure_ascii=True,indent=2))

if __name__=='__main__': main()
