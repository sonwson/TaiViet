"""Deterministic, non-destructive relational migration. Default is dry-run.

SQLite is an executable local development target, PostgreSQL is the deployment target.
The exact JSON bundle can be loaded transactionally into either schema.
"""
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from tai_engine.engine import ROOT
import argparse
from collections import defaultdict,Counter
import hashlib
import json
import sqlite3
import uuid
import shutil
from contextlib import closing
from datetime import datetime,timezone

TABLES=['source_records','lexemes','word_senses','orthography_analyses','sentences','translations','word_sense_examples']
NS=uuid.UUID('11a65a78-13be-453f-8d25-b635810e0608')
def canonical(value): return json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':'))
def uid(kind,key): return str(uuid.uuid5(NS,kind+':'+canonical(key)))
def dump(path,obj): path.write_text(json.dumps(obj,ensure_ascii=False,indent=2),encoding='utf-8')


def build(records, source_hash='fixture', xlsx_rows=None):
    if not isinstance(records,list): raise ValueError('Source root must be an array')
    tables={t:{} for t in TABLES}; errors=[]; warnings=[]; seen_ids=set()
    groups={k:defaultdict(list) for k in ['exact_duplicates','possible_duplicates','homographs','homophones','polysemous_candidates']}
    for index,r in enumerate(records):
        sid=uid('source',[source_hash,index])
        tables['source_records'][sid]=dict(id=sid,source_kind='dictionary_json',source_hash=source_hash,
            source_row=index+1,legacy_mongo_id=str(r.get('_id')) if isinstance(r,dict) else None,payload=r)
        bad=[]
        if not isinstance(r,dict): bad=['record is not an object']
        else:
            for key in ['tu_thai','nghia_tieng_viet']:
                if not isinstance(r.get(key),str) or not r[key].strip(): bad.append(key+' must be nonempty text')
            for key in ['phien_am','loai_tu']:
                if r.get(key) is not None and not isinstance(r[key],str): bad.append(key+' invalid type')
            if not isinstance(r.get('cau_vi_du',[]),list): bad.append('cau_vi_du must be list')
            if not isinstance(r.get('cau_tao_chu',{}),dict): bad.append('cau_tao_chu must be object')
            if '_id' not in r or isinstance(r['_id'],(dict,list,bool)) or r['_id'] is None: bad.append('invalid legacy ID')
            elif str(r['_id']) in seen_ids: bad.append('duplicate legacy ID')
            else: seen_ids.add(str(r['_id']))
        if bad:
            errors.append(dict(source_row=index+1,source_record_id=sid,errors=bad)); continue
        legacy=str(r['_id']); word=r['tu_thai']; roman=r.get('phien_am'); ortho=r.get('cau_tao_chu',{})
        # Provisional grouping is explicit; original records permit later homonym splitting.
        # Missing romanization, homonym/region differences, POS or analysis differences stay separate.
        key=[word,roman,r.get('loai_tu'),ortho,r.get('region'),r.get('homonym_id')]
        if not roman or not ortho: key.append(legacy)
        lid=uid('lexeme',key)
        tables['lexemes'].setdefault(lid,dict(id=lid,tai_text_original=word,romanization=roman,
            grouping_status='provisional',status='approved',source_type='dictionary'))
        senseid=uid('sense',[source_hash,legacy])
        tables['word_senses'][senseid]=dict(id=senseid,lexeme_id=lid,legacy_mongo_id=legacy,
            source_record_id=sid,vietnamese_meaning=r['nghia_tieng_viet'],part_of_speech=r.get('loai_tu'),status='approved')
        aid=uid('orthography',[lid,ortho])
        tables['orthography_analyses'].setdefault(aid,dict(id=aid,lexeme_id=lid,initial_text=ortho.get('phu_am_dau'),
            vowel_text=ortho.get('nguyen_am'),final_text=ortho.get('phu_am_cuoi'),tone_text=ortho.get('dau_thanh'),
            rule_text=ortho.get('quy_tac'),raw_analysis=ortho,rule_version='legacy_import_unverified'))
        for k,key2 in [('exact_duplicates',{k:v for k,v in r.items() if k!='_id'}),
                       ('possible_duplicates',[word,roman]),('homographs',word),('homophones',roman),
                       ('polysemous_candidates',lid)]: groups[k][canonical(key2)].append(legacy)
        for exindex,ex in enumerate(r.get('cau_vi_du',[])):
            if not isinstance(ex,dict) or not isinstance(ex.get('thai'),str) or not ex['thai'].strip():
                errors.append(dict(legacy_mongo_id=legacy,example_index=exindex,error='invalid Tai example; retained in source_records')); continue
            if ex.get('phien_am') is not None and not isinstance(ex['phien_am'],str):
                errors.append(dict(legacy_mongo_id=legacy,example_index=exindex,error='invalid example romanization; retained in source_records')); continue
            sentence=uid('sentence',[ex['thai'],ex.get('phien_am')])
            tables['sentences'].setdefault(sentence,dict(id=sentence,tai_text_original=ex['thai'],romanization=ex.get('phien_am'),
                source_type='dictionary',status='approved',source_reference='dictionary_json:'+source_hash))
            trans=None
            if isinstance(ex.get('nghia_viet'),str) and ex['nghia_viet'].strip():
                trans=uid('translation',[sentence,ex['nghia_viet']])
                tables['translations'].setdefault(trans,dict(id=trans,sentence_id=sentence,vietnamese_text=ex['nghia_viet'],
                    origin='dictionary_import',status='approved'))
            else: warnings.append(dict(legacy_mongo_id=legacy,example_index=exindex,warning='missing/invalid translation retained in source record'))
            eid=uid('example',[senseid,exindex])
            tables['word_sense_examples'][eid]=dict(id=eid,word_sense_id=senseid,sentence_id=sentence,
                translation_id=trans,source_record_id=sid,example_index=exindex,romanization_original=ex.get('phien_am'))
    if xlsx_rows:
        xhash=hashlib.sha256((ROOT/'data/TaiViet_dataframe.xlsx').read_bytes()).hexdigest()
        for n,row in enumerate(xlsx_rows,2):
            sid=uid('source',[xhash,n])
            tables['source_records'][sid]=dict(id=sid,source_kind='xlsx',source_hash=xhash,source_row=n,
                legacy_mongo_id=str(row.get('IDNTN')),payload=row)
    duplicates={k:[dict(key=json.loads(key),legacy_ids=ids) for key,ids in group.items() if len(ids)>1]
                for k,group in groups.items()}
    # Distinguish homographs/homophones from repeated senses.
    lookup={str(r['_id']):r for r in records if isinstance(r,dict) and '_id' in r}
    duplicates['homographs']=[g for g in duplicates['homographs'] if len({lookup[i].get('phien_am') for i in g['legacy_ids']})>1]
    duplicates['homophones']=[g for g in duplicates['homophones'] if len({lookup[i].get('tu_thai') for i in g['legacy_ids']})>1]
    report=dict(input_records=len(records),counts={t:len(rows) for t,rows in tables.items()},errors=errors,warnings=warnings,
        duplicate_group_counts={k:len(v) for k,v in duplicates.items()},source_hash=source_hash,
        merge_policy='Exact Tai + romanization + POS + full orthography + region + explicit homonym ID; provisional grouping. No source or sense deleted.')
    return {t:list(rows.values()) for t,rows in tables.items()},report,duplicates


def load_sqlite(path,bundle):
    path=Path(path)
    path.parent.mkdir(parents=True,exist_ok=True)
    if path.exists():
        backup=path.with_name(path.name+'.before-'+datetime.now().strftime('%Y%m%d%H%M%S')+'.bak')
        with closing(sqlite3.connect(path)) as src,closing(sqlite3.connect(backup)) as dest: src.backup(dest)
    with closing(sqlite3.connect(path)) as db, db:
        db.execute('PRAGMA foreign_keys=ON')
        db.executescript((ROOT/'database/local.sql').read_text(encoding='utf-8'))
        for table in TABLES:
            for row in bundle[table]:
                vals=[canonical(v) if isinstance(v,(dict,list)) else v for v in row.values()]
                columns=','.join(row)
                db.execute(f'INSERT INTO {table} ({columns}) VALUES ({",".join("?" for _ in row)}) ON CONFLICT(id) DO NOTHING',vals)
                saved=db.execute(f'SELECT {columns} FROM {table} WHERE id=?',(row['id'],)).fetchone()
                if tuple(vals)!=saved: raise ValueError(f'Existing {table}/{row["id"]} differs; refusing overwrite')
        violations=db.execute('PRAGMA foreign_key_check').fetchall()
        if violations: raise ValueError(violations)
        return {t:db.execute(f'SELECT count(*) FROM {t}').fetchone()[0] for t in TABLES}


def postgres_sql(bundle):
    lines=['BEGIN;', "SET LOCAL standard_conforming_strings = on;"]
    for table in TABLES:
        for row in bundle[table]:
            vals=[]
            for v in row.values():
                if v is None: vals.append('NULL')
                elif isinstance(v,int): vals.append(str(v))
                else: vals.append("'"+(canonical(v) if isinstance(v,(dict,list)) else str(v)).replace("'","''")+"'")
            lines.append(f'INSERT INTO public.{table} ({",".join(row)}) VALUES ({",".join(vals)}) ON CONFLICT(id) DO NOTHING;')
    lines.append('COMMIT;')
    return '\n'.join(lines)+'\n'


def main():
    parser=argparse.ArgumentParser(); parser.add_argument('--source',type=Path,default=ROOT/'data/taiviet_dictionary_dataset.json')
    parser.add_argument('--dry-run',action='store_true'); parser.add_argument('--sqlite',type=Path)
    parser.add_argument('--postgres-sql',action='store_true'); args=parser.parse_args()
    raw=args.source.read_bytes(); digest=hashlib.sha256(raw).hexdigest()
    backups=ROOT/'backups'; backups.mkdir(exist_ok=True)
    backup=backups/(digest+'.json')
    if not backup.exists(): backup.write_bytes(raw)
    if hashlib.sha256(backup.read_bytes()).hexdigest()!=digest: raise ValueError('Backup hash mismatch')
    xlsx_path=ROOT/'reports/xlsx_rows_original.json'
    xlsx=json.loads(xlsx_path.read_text(encoding='utf-8')) if xlsx_path.exists() else None
    bundle,report,duplicates=build(json.loads(raw.decode('utf-8-sig')),digest,xlsx)
    out=ROOT/'reports'; out.mkdir(exist_ok=True)
    dump(out/'migration_bundle.json',bundle); dump(out/'migration_report.json',report); dump(out/'duplicates.json',duplicates)
    if args.sqlite and not args.dry_run:
        report['sqlite_counts']=load_sqlite(args.sqlite,bundle); dump(out/'migration_report.json',report)
    if args.postgres_sql:
        (out/'migration.sql').write_text(postgres_sql(bundle),encoding='utf-8')
    print(json.dumps({k:v for k,v in report.items() if k not in ['errors','warnings']},indent=2))
    print('Errors:',len(report['errors']),'Warnings:',len(report['warnings']))

if __name__=='__main__': main()
