"""Generate the deployable SQL schema from the shared local table definitions."""
from pathlib import Path
import re
ROOT=Path(__file__).resolve().parents[1]


def main():
    sql=(ROOT/'database/local.sql').read_text(encoding='utf-8').split('CREATE TRIGGER')[0]
    sql+='\n'+(ROOT/'database/extensions.sql').read_text(encoding='utf-8')
    sql+='\n'+(ROOT/'database/accounts.sql').read_text(encoding='utf-8')
    sql=sql.replace('PRAGMA foreign_keys = ON;','BEGIN;')
    sql=re.sub(r'\b(id|lexeme_id|source_record_id|sentence_id|translation_id|word_sense_id|contributor_id|user_id|admin_id|entity_id) TEXT',r'\1 UUID',sql)
    sql=re.sub(r'\b(payload|raw_analysis|annotation_data|value_sources|generated_suggestions|analysis) TEXT',r'\1 JSONB',sql)
    sql=re.sub(r'\b(created_at|updated_at) TEXT',r'\1 TIMESTAMPTZ',sql)
    sql=sql.replace('id UUID PRIMARY KEY,','id UUID PRIMARY KEY DEFAULT gen_random_uuid(),')
    # SQL NULL must not bypass required suggested corrections.
    sql=sql.replace('OR length(trim(suggested_translation))>0','OR coalesce(length(trim(suggested_translation)),0)>0')
    sql+='\n'+(ROOT/'database/security.sql').read_text(encoding='utf-8')+'\nCOMMIT;\n'
    (ROOT/'database/supabase.sql').write_text(sql,encoding='utf-8')

if __name__=='__main__': main()
