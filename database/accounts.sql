CREATE TABLE IF NOT EXISTS user_accounts (
 id TEXT PRIMARY KEY, email TEXT NOT NULL UNIQUE, password_hash TEXT NOT NULL,
 display_name TEXT NOT NULL, role TEXT NOT NULL DEFAULT 'user',
 name_updated_at BIGINT DEFAULT 0, password_updated_at BIGINT DEFAULT 0,
 created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS account_sessions (
 token_hash TEXT PRIMARY KEY, user_id TEXT NOT NULL REFERENCES user_accounts(id),
 expires_at BIGINT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_account_sessions_user ON account_sessions(user_id);
CREATE INDEX IF NOT EXISTS idx_account_sessions_expiry ON account_sessions(expires_at);
CREATE TABLE IF NOT EXISTS password_resets (
 token_hash TEXT PRIMARY KEY, user_id TEXT NOT NULL REFERENCES user_accounts(id),
 expires_at BIGINT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_password_resets_user ON password_resets(user_id);
CREATE INDEX IF NOT EXISTS idx_password_resets_expiry ON password_resets(expires_at);
CREATE INDEX IF NOT EXISTS idx_word_contributions_owner ON word_contributions(contributor_id,status);
CREATE INDEX IF NOT EXISTS idx_sentences_owner ON sentences(contributor_id,status);
