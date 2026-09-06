PRAGMA foreign_keys = ON;
CREATE TABLE IF NOT EXISTS source_records (
 id TEXT PRIMARY KEY, source_kind TEXT NOT NULL, source_hash TEXT NOT NULL,
 source_row INTEGER NOT NULL, legacy_mongo_id TEXT, payload TEXT NOT NULL,
 UNIQUE(source_hash,source_row)
);
CREATE TABLE IF NOT EXISTS lexemes (
 id TEXT PRIMARY KEY, tai_text_original TEXT NOT NULL CHECK(length(trim(tai_text_original))>0),
 romanization TEXT, grouping_status TEXT NOT NULL DEFAULT 'provisional',
 status TEXT NOT NULL DEFAULT 'pending' CHECK(status IN ('pending','approved','rejected')),
 source_type TEXT NOT NULL DEFAULT 'community', created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS word_senses (
 id TEXT PRIMARY KEY, lexeme_id TEXT NOT NULL REFERENCES lexemes(id), legacy_mongo_id TEXT,
 source_record_id TEXT REFERENCES source_records(id), vietnamese_meaning TEXT NOT NULL CHECK(length(trim(vietnamese_meaning))>0),
 part_of_speech TEXT, status TEXT NOT NULL DEFAULT 'pending' CHECK(status IN ('pending','approved','rejected')),
 created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS orthography_analyses (
 id TEXT PRIMARY KEY, lexeme_id TEXT NOT NULL REFERENCES lexemes(id), initial_text TEXT, vowel_text TEXT,
 final_text TEXT, tone_text TEXT, rule_text TEXT, raw_analysis TEXT NOT NULL, rule_version TEXT NOT NULL,
 created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS sentences (
 id TEXT PRIMARY KEY, tai_text_original TEXT NOT NULL CHECK(length(trim(tai_text_original)) BETWEEN 1 AND 5000),
 romanization TEXT, source_type TEXT NOT NULL DEFAULT 'community', source_reference TEXT,
 region_original TEXT, contributor_id TEXT, contributor_name TEXT, consent_version TEXT,
 status TEXT NOT NULL DEFAULT 'pending' CHECK(status IN ('pending','approved','rejected')),
 created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS translations (
 id TEXT PRIMARY KEY, sentence_id TEXT NOT NULL REFERENCES sentences(id),
 vietnamese_text TEXT NOT NULL CHECK(length(trim(vietnamese_text)) BETWEEN 1 AND 5000),
 origin TEXT NOT NULL DEFAULT 'community', contributor_id TEXT, contributor_name TEXT, consent_version TEXT,
 status TEXT NOT NULL DEFAULT 'pending' CHECK(status IN ('pending','approved','rejected')),
 created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS word_sense_examples (
 id TEXT PRIMARY KEY, word_sense_id TEXT NOT NULL REFERENCES word_senses(id), sentence_id TEXT NOT NULL REFERENCES sentences(id),
 translation_id TEXT REFERENCES translations(id), source_record_id TEXT NOT NULL REFERENCES source_records(id),
 example_index INTEGER NOT NULL, romanization_original TEXT, UNIQUE(word_sense_id,example_index)
);
CREATE TABLE IF NOT EXISTS translation_validations (
 id TEXT PRIMARY KEY, translation_id TEXT NOT NULL REFERENCES translations(id), contributor_id TEXT NOT NULL,
 validation_status TEXT NOT NULL CHECK(validation_status IN ('correct','needs_correction','incorrect')),
 suggested_translation TEXT, consent_version TEXT NOT NULL, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
 CHECK(validation_status <> 'needs_correction' OR coalesce(length(trim(suggested_translation)),0)>0),
 UNIQUE(translation_id,contributor_id)
);
CREATE TABLE IF NOT EXISTS sentence_reviews (
 id TEXT PRIMARY KEY, sentence_id TEXT NOT NULL REFERENCES sentences(id), contributor_id TEXT NOT NULL,
 naturalness TEXT NOT NULL CHECK(naturalness IN ('natural','problematic','unsure')),
 consent_version TEXT NOT NULL, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
 UNIQUE(sentence_id,contributor_id)
);
CREATE TABLE IF NOT EXISTS user_roles (
 user_id TEXT PRIMARY KEY, role TEXT NOT NULL CHECK(role='admin')
);
CREATE TABLE IF NOT EXISTS annotations (
 id TEXT PRIMARY KEY, sentence_id TEXT NOT NULL REFERENCES sentences(id), annotation_type TEXT NOT NULL,
 annotation_data TEXT NOT NULL, version TEXT NOT NULL, contributor_id TEXT,
 status TEXT NOT NULL DEFAULT 'pending' CHECK(status IN ('pending','approved','rejected')),
 created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS word_contributions (
 id TEXT PRIMARY KEY, tai_text_original TEXT, romanization_original TEXT,
 tai_text_generated TEXT, romanization_generated TEXT, tai_text_final TEXT, romanization_final TEXT,
 vietnamese_meaning TEXT NOT NULL CHECK(length(trim(vietnamese_meaning)) BETWEEN 1 AND 5000),
 value_sources TEXT NOT NULL, generated_suggestions TEXT NOT NULL, analysis TEXT NOT NULL, rule_version TEXT NOT NULL,
 consistency_status TEXT NOT NULL, inconsistency_confirmed INTEGER NOT NULL DEFAULT 0,
 contributor_id TEXT NOT NULL, contributor_name TEXT, consent_version TEXT NOT NULL,
 status TEXT NOT NULL DEFAULT 'pending' CHECK(status IN ('pending','approved','rejected')),
 created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
 CHECK(coalesce(length(trim(tai_text_original)),0)>0 OR coalesce(length(trim(romanization_original)),0)>0)
);
CREATE TABLE IF NOT EXISTS moderation_events (
 id TEXT PRIMARY KEY, entity_table TEXT NOT NULL, entity_id TEXT NOT NULL, previous_status TEXT NOT NULL,
 new_status TEXT NOT NULL, admin_id TEXT NOT NULL, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
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
CREATE TRIGGER IF NOT EXISTS immutable_sentence BEFORE UPDATE OF tai_text_original,romanization,source_type,source_reference,region_original,contributor_id,consent_version ON sentences
BEGIN SELECT RAISE(ABORT,'Original sentence fields are immutable'); END;
CREATE TRIGGER IF NOT EXISTS immutable_translation BEFORE UPDATE OF vietnamese_text,sentence_id,origin,contributor_id,consent_version ON translations
BEGIN SELECT RAISE(ABORT,'Translations are append only'); END;
CREATE TRIGGER IF NOT EXISTS immutable_sources BEFORE UPDATE ON source_records
BEGIN SELECT RAISE(ABORT,'Source archive is immutable'); END;
