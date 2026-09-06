-- Replace :parameters with bound parameters in your SQL client / backend.
-- Tai -> all senses (same spelling can legitimately have several lexemes)
SELECT l.id,l.tai_text_original,l.romanization,w.vietnamese_meaning,w.part_of_speech,w.legacy_mongo_id
FROM lexemes l JOIN word_senses w ON w.lexeme_id=l.id
WHERE l.tai_text_original=:tai_text ORDER BY l.id,w.id;

-- Romanization -> spelling candidates
SELECT id,tai_text_original,romanization,grouping_status FROM lexemes WHERE romanization=:romanization;

-- Vietnamese meaning -> Tai
SELECT l.tai_text_original,l.romanization,w.* FROM word_senses w JOIN lexemes l ON l.id=w.lexeme_id
WHERE w.vietnamese_meaning LIKE :meaning_pattern;

-- Lexeme -> original orthographic analysis
SELECT * FROM orthography_analyses WHERE lexeme_id=:lexeme_id;

-- Sense -> exact examples and their imported translations
SELECT s.*,t.vietnamese_text,e.romanization_original,e.source_record_id
FROM word_sense_examples e JOIN sentences s ON s.id=e.sentence_id
LEFT JOIN translations t ON t.id=e.translation_id WHERE e.word_sense_id=:sense_id;

-- Sentence -> all translations -> all validations (no latest-value overwrite)
SELECT t.*,v.id validation_id,v.validation_status,v.suggested_translation
FROM translations t LEFT JOIN translation_validations v ON v.translation_id=t.id
WHERE t.sentence_id=:sentence_id ORDER BY t.id,v.created_at;

-- Source trace back to complete JSON / workbook row
SELECT s.legacy_mongo_id,r.source_kind,r.source_row,r.payload
FROM word_senses s JOIN source_records r ON r.id=s.source_record_id WHERE s.id=:sense_id;
