CREATE TABLE IF NOT EXISTS lexeme_search_keys (
 lexeme_id TEXT NOT NULL REFERENCES lexemes(id), canonical_key TEXT NOT NULL,
 rule_version TEXT NOT NULL, PRIMARY KEY(lexeme_id,canonical_key,rule_version)
);
CREATE INDEX IF NOT EXISTS idx_canonical_search ON lexeme_search_keys(canonical_key,rule_version);
CREATE TABLE IF NOT EXISTS sentence_submissions (
 id TEXT PRIMARY KEY, sentence_id TEXT REFERENCES sentences(id),
 tai_text_original TEXT, romanization_original TEXT, tai_text_generated TEXT, romanization_generated TEXT,
 tai_text_final TEXT, romanization_final TEXT, value_sources TEXT NOT NULL, generated_suggestions TEXT NOT NULL,
 analysis TEXT NOT NULL, rule_version TEXT NOT NULL, consistency_status TEXT NOT NULL,
 contributor_id TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'pending' CHECK(status IN ('pending','approved','rejected')),
 created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
 CHECK(coalesce(length(trim(tai_text_original)),0)>0 OR coalesce(length(trim(romanization_original)),0)>0)
);
CREATE INDEX IF NOT EXISTS idx_sentence_submissions_sentence ON sentence_submissions(sentence_id);
CREATE INDEX IF NOT EXISTS idx_sentence_submissions_status ON sentence_submissions(status);
CREATE TABLE IF NOT EXISTS romanization_corrections (
 id TEXT PRIMARY KEY, sentence_id TEXT NOT NULL REFERENCES sentences(id), base_romanization TEXT,
 suggested_romanization TEXT NOT NULL CHECK(length(trim(suggested_romanization)) BETWEEN 1 AND 5000),
 base_source TEXT NOT NULL, rule_version TEXT NOT NULL, analysis TEXT NOT NULL,
 contributor_id TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'pending' CHECK(status IN ('pending','approved','rejected')),
 created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_romanization_corrections_sentence ON romanization_corrections(sentence_id,status);
