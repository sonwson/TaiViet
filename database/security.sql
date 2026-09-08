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
