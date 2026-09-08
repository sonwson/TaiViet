BEGIN;
CREATE TABLE IF NOT EXISTS source_records (
 id UUID PRIMARY KEY DEFAULT gen_random_uuid(), source_kind TEXT NOT NULL, source_hash TEXT NOT NULL,
 source_row INTEGER NOT NULL, legacy_mongo_id TEXT, payload JSONB NOT NULL,
 UNIQUE(source_hash,source_row)
);
CREATE TABLE IF NOT EXISTS lexemes (
 id UUID PRIMARY KEY DEFAULT gen_random_uuid(), tai_text_original TEXT NOT NULL CHECK(length(trim(tai_text_original))>0),
 romanization TEXT, grouping_status TEXT NOT NULL DEFAULT 'provisional',
 status TEXT NOT NULL DEFAULT 'pending' CHECK(status IN ('pending','approved','rejected')),
 source_type TEXT NOT NULL DEFAULT 'community', created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS word_senses (
 id UUID PRIMARY KEY DEFAULT gen_random_uuid(), lexeme_id UUID NOT NULL REFERENCES lexemes(id), legacy_mongo_id TEXT,
 source_record_id UUID REFERENCES source_records(id), vietnamese_meaning TEXT NOT NULL CHECK(length(trim(vietnamese_meaning))>0),
 part_of_speech TEXT, status TEXT NOT NULL DEFAULT 'pending' CHECK(status IN ('pending','approved','rejected')),
 created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS orthography_analyses (
 id UUID PRIMARY KEY DEFAULT gen_random_uuid(), lexeme_id UUID NOT NULL REFERENCES lexemes(id), initial_text TEXT, vowel_text TEXT,
 final_text TEXT, tone_text TEXT, rule_text TEXT, raw_analysis JSONB NOT NULL, rule_version TEXT NOT NULL,
 created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS sentences (
 id UUID PRIMARY KEY DEFAULT gen_random_uuid(), tai_text_original TEXT NOT NULL CHECK(length(trim(tai_text_original)) BETWEEN 1 AND 5000),
 romanization TEXT, source_type TEXT NOT NULL DEFAULT 'community', source_reference TEXT,
 region_original TEXT, contributor_id UUID, contributor_name TEXT, consent_version TEXT,
 status TEXT NOT NULL DEFAULT 'pending' CHECK(status IN ('pending','approved','rejected')),
 created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP, updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS translations (
 id UUID PRIMARY KEY DEFAULT gen_random_uuid(), sentence_id UUID NOT NULL REFERENCES sentences(id),
 vietnamese_text TEXT NOT NULL CHECK(length(trim(vietnamese_text)) BETWEEN 1 AND 5000),
 origin TEXT NOT NULL DEFAULT 'community', contributor_id UUID, contributor_name TEXT, consent_version TEXT,
 status TEXT NOT NULL DEFAULT 'pending' CHECK(status IN ('pending','approved','rejected')),
 created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP, updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS word_sense_examples (
 id UUID PRIMARY KEY DEFAULT gen_random_uuid(), word_sense_id UUID NOT NULL REFERENCES word_senses(id), sentence_id UUID NOT NULL REFERENCES sentences(id),
 translation_id UUID REFERENCES translations(id), source_record_id UUID NOT NULL REFERENCES source_records(id),
 example_index INTEGER NOT NULL, romanization_original TEXT, UNIQUE(word_sense_id,example_index)
);
CREATE TABLE IF NOT EXISTS translation_validations (
 id UUID PRIMARY KEY DEFAULT gen_random_uuid(), translation_id UUID NOT NULL REFERENCES translations(id), contributor_id UUID NOT NULL,
 validation_status TEXT NOT NULL CHECK(validation_status IN ('correct','needs_correction','incorrect')),
 suggested_translation TEXT, consent_version TEXT NOT NULL, created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
 CHECK(validation_status <> 'needs_correction' OR coalesce(length(trim(suggested_translation)),0)>0),
 UNIQUE(translation_id,contributor_id)
);
CREATE TABLE IF NOT EXISTS sentence_reviews (
 id UUID PRIMARY KEY DEFAULT gen_random_uuid(), sentence_id UUID NOT NULL REFERENCES sentences(id), contributor_id UUID NOT NULL,
 naturalness TEXT NOT NULL CHECK(naturalness IN ('natural','problematic','unsure')),
 consent_version TEXT NOT NULL, created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
 UNIQUE(sentence_id,contributor_id)
);
CREATE TABLE IF NOT EXISTS user_roles (
 user_id UUID PRIMARY KEY DEFAULT gen_random_uuid(), role TEXT NOT NULL CHECK(role='admin')
);
CREATE TABLE IF NOT EXISTS annotations (
 id UUID PRIMARY KEY DEFAULT gen_random_uuid(), sentence_id UUID NOT NULL REFERENCES sentences(id), annotation_type TEXT NOT NULL,
 annotation_data JSONB NOT NULL, version TEXT NOT NULL, contributor_id UUID,
 status TEXT NOT NULL DEFAULT 'pending' CHECK(status IN ('pending','approved','rejected')),
 created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS word_contributions (
 id UUID PRIMARY KEY DEFAULT gen_random_uuid(), tai_text_original TEXT, romanization_original TEXT,
 tai_text_generated TEXT, romanization_generated TEXT, tai_text_final TEXT, romanization_final TEXT,
 vietnamese_meaning TEXT NOT NULL CHECK(length(trim(vietnamese_meaning)) BETWEEN 1 AND 5000),
 value_sources JSONB NOT NULL, generated_suggestions JSONB NOT NULL, analysis JSONB NOT NULL, rule_version TEXT NOT NULL,
 consistency_status TEXT NOT NULL, inconsistency_confirmed INTEGER NOT NULL DEFAULT 0,
 contributor_id UUID NOT NULL, contributor_name TEXT, consent_version TEXT NOT NULL,
 status TEXT NOT NULL DEFAULT 'pending' CHECK(status IN ('pending','approved','rejected')),
 created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
 CHECK(coalesce(length(trim(tai_text_original)),0)>0 OR coalesce(length(trim(romanization_original)),0)>0)
);
CREATE TABLE IF NOT EXISTS moderation_events (
 id UUID PRIMARY KEY DEFAULT gen_random_uuid(), entity_table TEXT NOT NULL, entity_id UUID NOT NULL, previous_status TEXT NOT NULL,
 new_status TEXT NOT NULL, admin_id UUID NOT NULL, created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_lexemes_tai ON lexemes(tai_text_original);
CREATE INDEX IF NOT EXISTS idx_lexemes_roman ON lexemes(romanization);
CREATE INDEX IF NOT EXISTS idx_senses_lexeme ON word_senses(lexeme_id);
CREATE INDEX IF NOT EXISTS idx_senses_legacy ON word_senses(legacy_mongo_id);
CREATE INDEX IF NOT EXISTS idx_senses_meaning ON word_senses(vietnamese_meaning);
CREATE INDEX IF NOT EXISTS idx_analyses_lexeme ON orthography_analyses(lexeme_id);
CREATE INDEX IF NOT EXISTS idx_examples_sense ON word_sense_examples(word_sense_id);
CREATE INDEX IF NOT EXISTS idx_examples_sentence ON word_sense_examples(sentence_id);
CREATE INDEX IF NOT EXISTS idx_translations_sentence ON translations(sentence_id);
CREATE INDEX IF NOT EXISTS idx_sentences_status ON sentences(status);
CREATE INDEX IF NOT EXISTS idx_translations_status ON translations(status);
CREATE INDEX IF NOT EXISTS idx_contributions_status ON word_contributions(status);
CREATE INDEX IF NOT EXISTS idx_annotations_sentence ON annotations(sentence_id);

CREATE TABLE IF NOT EXISTS lexeme_search_keys (
 lexeme_id UUID NOT NULL REFERENCES lexemes(id), canonical_key TEXT NOT NULL,
 rule_version TEXT NOT NULL, PRIMARY KEY(lexeme_id,canonical_key,rule_version)
);
CREATE INDEX IF NOT EXISTS idx_canonical_search ON lexeme_search_keys(canonical_key,rule_version);
CREATE TABLE IF NOT EXISTS sentence_submissions (
 id UUID PRIMARY KEY DEFAULT gen_random_uuid(), sentence_id UUID REFERENCES sentences(id),
 tai_text_original TEXT, romanization_original TEXT, tai_text_generated TEXT, romanization_generated TEXT,
 tai_text_final TEXT, romanization_final TEXT, value_sources JSONB NOT NULL, generated_suggestions JSONB NOT NULL,
 analysis JSONB NOT NULL, rule_version TEXT NOT NULL, consistency_status TEXT NOT NULL,
 contributor_id UUID NOT NULL, status TEXT NOT NULL DEFAULT 'pending' CHECK(status IN ('pending','approved','rejected')),
 created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
 CHECK(coalesce(length(trim(tai_text_original)),0)>0 OR coalesce(length(trim(romanization_original)),0)>0)
);
CREATE INDEX IF NOT EXISTS idx_sentence_submissions_sentence ON sentence_submissions(sentence_id);
CREATE INDEX IF NOT EXISTS idx_sentence_submissions_status ON sentence_submissions(status);
CREATE TABLE IF NOT EXISTS romanization_corrections (
 id UUID PRIMARY KEY DEFAULT gen_random_uuid(), sentence_id UUID NOT NULL REFERENCES sentences(id), base_romanization TEXT,
 suggested_romanization TEXT NOT NULL CHECK(length(trim(suggested_romanization)) BETWEEN 1 AND 5000),
 base_source TEXT NOT NULL, rule_version TEXT NOT NULL, analysis JSONB NOT NULL,
 contributor_id UUID NOT NULL, status TEXT NOT NULL DEFAULT 'pending' CHECK(status IN ('pending','approved','rejected')),
 created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_romanization_corrections_sentence ON romanization_corrections(sentence_id,status);
CREATE TABLE IF NOT EXISTS sentence_corrections (
 id UUID PRIMARY KEY DEFAULT gen_random_uuid(), sentence_id UUID NOT NULL REFERENCES sentences(id), base_tai_text TEXT,
 suggested_tai_text TEXT NOT NULL CHECK(length(trim(suggested_tai_text)) BETWEEN 1 AND 5000),
 suggested_romanization TEXT NOT NULL CHECK(length(trim(suggested_romanization)) BETWEEN 1 AND 5000),
 suggested_meaning TEXT DEFAULT '',
 contributor_id UUID NOT NULL, status TEXT NOT NULL DEFAULT 'pending' CHECK(status IN ('pending','approved','rejected')),
 created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_sentence_corrections_sentence ON sentence_corrections(sentence_id,status);


CREATE TABLE IF NOT EXISTS user_accounts (
 id UUID PRIMARY KEY DEFAULT gen_random_uuid(), email TEXT NOT NULL UNIQUE, password_hash TEXT NOT NULL,
 display_name TEXT NOT NULL, created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS account_sessions (
 token_hash TEXT PRIMARY KEY, user_id UUID NOT NULL REFERENCES user_accounts(id),
 expires_at BIGINT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_account_sessions_user ON account_sessions(user_id);
CREATE INDEX IF NOT EXISTS idx_account_sessions_expiry ON account_sessions(expires_at);
CREATE TABLE IF NOT EXISTS password_resets (
 token_hash TEXT PRIMARY KEY, user_id UUID NOT NULL REFERENCES user_accounts(id),
 expires_at BIGINT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_password_resets_user ON password_resets(user_id);
CREATE INDEX IF NOT EXISTS idx_password_resets_expiry ON password_resets(expires_at);
CREATE INDEX IF NOT EXISTS idx_word_contributions_owner ON word_contributions(contributor_id,status);
CREATE INDEX IF NOT EXISTS idx_sentences_owner ON sentences(contributor_id,status);

-- Supabase: run as postgres / migration owner, never from a browser.
ALTER TABLE public.user_accounts ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.account_sessions ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.password_resets ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON public.user_accounts,public.account_sessions,public.password_resets FROM PUBLIC,anon,authenticated;
CREATE SCHEMA IF NOT EXISTS private;
REVOKE ALL ON SCHEMA private FROM PUBLIC;
GRANT USAGE ON SCHEMA private TO authenticated;
CREATE OR REPLACE FUNCTION private.is_admin() RETURNS BOOLEAN
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = '' AS $$
 SELECT EXISTS (SELECT 1 FROM public.user_roles WHERE user_id = (SELECT auth.uid()) AND role='admin');
$$;
REVOKE ALL ON FUNCTION private.is_admin() FROM PUBLIC;
GRANT EXECUTE ON FUNCTION private.is_admin() TO authenticated;

DO $$ DECLARE t TEXT; BEGIN
 FOREACH t IN ARRAY ARRAY['source_records','lexemes','word_senses','orthography_analyses','sentences','translations',
 'word_sense_examples','translation_validations','sentence_reviews','user_roles','annotations','word_contributions','moderation_events','lexeme_search_keys','sentence_submissions','romanization_corrections'] LOOP
  EXECUTE format('ALTER TABLE public.%I ENABLE ROW LEVEL SECURITY',t);
  EXECUTE format('REVOKE ALL ON public.%I FROM anon, authenticated',t);
  EXECUTE format('GRANT SELECT ON public.%I TO authenticated',t);
  EXECUTE format('DROP POLICY IF EXISTS admin_read ON public.%I',t);
  EXECUTE format('CREATE POLICY admin_read ON public.%I FOR SELECT TO authenticated USING ((SELECT private.is_admin()))',t);
 END LOOP;
END $$;

-- No client can update, delete, grant a role, write an import, or set approval status.
-- Administration is confined to the status-only RPC below. Bootstrap role via SQL editor.
DO $$ DECLARE t TEXT; BEGIN
 FOREACH t IN ARRAY ARRAY['lexemes','word_senses','sentences','translations'] LOOP
  EXECUTE format('GRANT SELECT ON public.%I TO anon',t);
  EXECUTE format('DROP POLICY IF EXISTS approved_read ON public.%I',t);
  EXECUTE format('CREATE POLICY approved_read ON public.%I FOR SELECT TO anon, authenticated USING (status=''approved'')',t);
 END LOOP;
END $$;
GRANT SELECT ON public.orthography_analyses,public.word_sense_examples TO anon;
DROP POLICY IF EXISTS approved_read ON public.orthography_analyses;
CREATE POLICY approved_read ON public.orthography_analyses FOR SELECT TO anon,authenticated USING (
 EXISTS(SELECT 1 FROM public.lexemes l WHERE l.id=lexeme_id AND l.status='approved'));
DROP POLICY IF EXISTS approved_read ON public.word_sense_examples;
CREATE POLICY approved_read ON public.word_sense_examples FOR SELECT TO anon,authenticated USING (
 EXISTS(SELECT 1 FROM public.word_senses s WHERE s.id=word_sense_id AND s.status='approved'));

GRANT INSERT ON public.sentences,public.translations,public.translation_validations,public.sentence_reviews,public.word_contributions TO authenticated;
DROP POLICY IF EXISTS own_read ON public.sentences;
CREATE POLICY own_read ON public.sentences FOR SELECT TO authenticated USING (contributor_id=(SELECT auth.uid()));
DROP POLICY IF EXISTS submit ON public.sentences;
CREATE POLICY submit ON public.sentences FOR INSERT TO authenticated WITH CHECK (
 contributor_id=(SELECT auth.uid()) AND status='pending' AND source_type IN ('self','oral','book','other') AND consent_version='research-v1');
DROP POLICY IF EXISTS own_read ON public.translations;
CREATE POLICY own_read ON public.translations FOR SELECT TO authenticated USING (contributor_id=(SELECT auth.uid()));
DROP POLICY IF EXISTS submit ON public.translations;
CREATE POLICY submit ON public.translations FOR INSERT TO authenticated WITH CHECK (
 contributor_id=(SELECT auth.uid()) AND status='pending' AND origin='community' AND consent_version='research-v1'
 AND EXISTS(SELECT 1 FROM public.sentences s WHERE s.id=sentence_id AND s.status='approved'));
DROP POLICY IF EXISTS own_read ON public.translation_validations;
CREATE POLICY own_read ON public.translation_validations FOR SELECT TO authenticated USING (contributor_id=(SELECT auth.uid()));
DROP POLICY IF EXISTS submit ON public.translation_validations;
CREATE POLICY submit ON public.translation_validations FOR INSERT TO authenticated WITH CHECK (
 contributor_id=(SELECT auth.uid()) AND consent_version='research-v1' AND EXISTS (
 SELECT 1 FROM public.translations t WHERE t.id=translation_id AND t.status='approved'
 AND t.contributor_id IS DISTINCT FROM (SELECT auth.uid())));
DROP POLICY IF EXISTS own_read ON public.sentence_reviews;
CREATE POLICY own_read ON public.sentence_reviews FOR SELECT TO authenticated USING (contributor_id=(SELECT auth.uid()));
DROP POLICY IF EXISTS submit ON public.sentence_reviews;
CREATE POLICY submit ON public.sentence_reviews FOR INSERT TO authenticated WITH CHECK (
 contributor_id=(SELECT auth.uid()) AND consent_version='research-v1'
 AND EXISTS(SELECT 1 FROM public.sentences s WHERE s.id=sentence_id AND s.status='approved'));
DROP POLICY IF EXISTS own_read ON public.word_contributions;
CREATE POLICY own_read ON public.word_contributions FOR SELECT TO authenticated USING (contributor_id=(SELECT auth.uid()));
-- Engine snapshots must be produced by trusted backend, so browser insert is revoked.
REVOKE INSERT ON public.word_contributions FROM authenticated;

CREATE OR REPLACE FUNCTION private.preserve_original() RETURNS trigger
LANGUAGE plpgsql SET search_path='' AS $$
BEGIN
 IF (to_jsonb(NEW)-'status'-'updated_at') IS DISTINCT FROM (to_jsonb(OLD)-'status'-'updated_at') THEN
  RAISE EXCEPTION 'Original data is immutable; append a separate revision';
 END IF;
 RETURN NEW;
END $$;
DO $$ DECLARE t TEXT; BEGIN
 FOREACH t IN ARRAY ARRAY['source_records','lexemes','word_senses','orthography_analyses','sentences','translations',
 'word_sense_examples','translation_validations','sentence_reviews','annotations','word_contributions','moderation_events','sentence_submissions','romanization_corrections'] LOOP
  EXECUTE format('DROP TRIGGER IF EXISTS preserve_original ON public.%I',t);
  EXECUTE format('CREATE TRIGGER preserve_original BEFORE UPDATE ON public.%I FOR EACH ROW EXECUTE FUNCTION private.preserve_original()',t);
 END LOOP;
END $$;

CREATE OR REPLACE FUNCTION public.moderate(entity TEXT, target UUID, decision TEXT) RETURNS VOID
LANGUAGE plpgsql SECURITY DEFINER SET search_path='' AS $$
DECLARE previous TEXT; linked UUID;
BEGIN
 IF NOT private.is_admin() THEN RAISE EXCEPTION 'Admin required'; END IF;
 IF entity NOT IN ('sentences','translations','word_contributions','annotations','lexemes','word_senses','sentence_submissions','romanization_corrections')
 OR decision NOT IN ('approved','rejected') THEN RAISE EXCEPTION 'Invalid moderation'; END IF;
 EXECUTE format('SELECT status FROM public.%I WHERE id=$1 FOR UPDATE',entity) INTO previous USING target;
 IF previous IS NULL THEN RAISE EXCEPTION 'Record not found'; END IF;
 EXECUTE format('UPDATE public.%I SET status=$1 WHERE id=$2',entity) USING decision,target;
 IF entity='sentences' THEN
  UPDATE public.sentence_submissions SET status=decision WHERE sentence_id=target;
 ELSIF entity='sentence_submissions' THEN
  SELECT sentence_id INTO linked FROM public.sentence_submissions WHERE id=target;
  IF linked IS NOT NULL THEN UPDATE public.sentences SET status=decision WHERE id=linked; END IF;
 END IF;
 INSERT INTO public.moderation_events(entity_table,entity_id,previous_status,new_status,admin_id)
 VALUES(entity,target,previous,decision,auth.uid());
END $$;
REVOKE ALL ON FUNCTION public.moderate(TEXT,UUID,TEXT) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION public.moderate(TEXT,UUID,TEXT) TO authenticated;

-- Reject oversized input and do basic per-contributor throttling even through REST.
CREATE OR REPLACE FUNCTION private.check_submission() RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER SET search_path='' AS $$
DECLARE recent BIGINT;
BEGIN
 IF auth.uid() IS NOT NULL THEN
  PERFORM pg_advisory_xact_lock(hashtextextended(auth.uid()::text,0));
  IF octet_length(to_jsonb(NEW)::text)>65536 THEN RAISE EXCEPTION 'Input too large'; END IF;
  IF NEW.contributor_id IS DISTINCT FROM auth.uid() THEN RAISE EXCEPTION 'Invalid contributor'; END IF;
  EXECUTE format('SELECT count(*) FROM public.%I WHERE contributor_id=$1 AND created_at>now()-interval ''1 minute''',TG_TABLE_NAME)
   INTO recent USING auth.uid();
  IF recent>=10 THEN RAISE EXCEPTION 'Please wait before submitting again'; END IF;
  NEW.created_at=now();
 END IF;
 RETURN NEW;
END $$;
DO $$ DECLARE t TEXT; BEGIN
 FOREACH t IN ARRAY ARRAY['sentences','translations','translation_validations','sentence_reviews','word_contributions'] LOOP
  EXECUTE format('DROP TRIGGER IF EXISTS check_submission ON public.%I',t);
  EXECUTE format('CREATE TRIGGER check_submission BEFORE INSERT ON public.%I FOR EACH ROW EXECUTE FUNCTION private.check_submission()',t);
 END LOOP;
END $$;

-- Additive v2 provenance: writes go through a trusted engine backend.
GRANT SELECT ON public.lexeme_search_keys TO anon;
DROP POLICY IF EXISTS approved_read ON public.lexeme_search_keys;
CREATE POLICY approved_read ON public.lexeme_search_keys FOR SELECT TO anon,authenticated USING (
 EXISTS(SELECT 1 FROM public.lexemes l WHERE l.id=lexeme_id AND l.status='approved'));
DO $$ DECLARE t TEXT; BEGIN
 FOREACH t IN ARRAY ARRAY['sentence_submissions','romanization_corrections'] LOOP
  EXECUTE format('DROP POLICY IF EXISTS own_read ON public.%I',t);
  EXECUTE format('CREATE POLICY own_read ON public.%I FOR SELECT TO authenticated USING (contributor_id=(SELECT auth.uid()))',t);
 END LOOP;
END $$;
GRANT SELECT ON public.romanization_corrections TO anon;
DROP POLICY IF EXISTS approved_read ON public.romanization_corrections;
CREATE POLICY approved_read ON public.romanization_corrections FOR SELECT TO anon,authenticated USING (
 status='approved' AND EXISTS(SELECT 1 FROM public.sentences s WHERE s.id=sentence_id AND s.status='approved'));

COMMIT;
