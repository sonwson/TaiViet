"""Additive schema + rebuildable canonical search index; original corpus is untouched."""
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from tai_engine.engine import Engine,ROOT
import sqlite3,json
from contextlib import closing
from datetime import datetime

def upgrade(path,engine=None):
    e=engine or Engine()
    with closing(sqlite3.connect(path)) as db,db:
        db.executescript((ROOT/'database/extensions.sql').read_text(encoding='utf-8'))
        rows=[]
        for lid,roman in db.execute('SELECT id,romanization FROM lexemes WHERE romanization IS NOT NULL'):
            rows.extend((lid,key,e.version) for key in e.canonical_keys(roman))
        db.executemany('INSERT INTO lexeme_search_keys(lexeme_id,canonical_key,rule_version) VALUES(?,?,?) ON CONFLICT DO NOTHING',rows)
        return len(rows)

if __name__=='__main__':
    path=ROOT/'runtime/tai.db'
    backup=ROOT/'backups'/('tai-upgrade34-'+datetime.now().strftime('%Y%m%d-%H%M%S')+'.db')
    with closing(sqlite3.connect(path)) as source,closing(sqlite3.connect(backup)) as dest:source.backup(dest)
    count=upgrade(path)
    out=ROOT/'reports/promt34';out.mkdir(exist_ok=True)
    with closing(sqlite3.connect(path)) as db:
        statements=['BEGIN;']
        for row in db.execute('SELECT lexeme_id,canonical_key,rule_version FROM lexeme_search_keys'):
            escaped=["'"+v.replace("'","''")+"'" for v in row]
            statements.append('INSERT INTO lexeme_search_keys(lexeme_id,canonical_key,rule_version) VALUES('+','.join(escaped)+') ON CONFLICT DO NOTHING;')
        statements.append('COMMIT;')
        (out/'search_index.sql').write_text('\n'.join(statements)+'\n',encoding='utf-8')
    print(json.dumps({'search_keys':count,'backup':str(backup)}))
