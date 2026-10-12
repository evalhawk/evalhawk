ALTER TABLE verdicts ADD COLUMN outcome TEXT GENERATED ALWAYS AS (json_extract(record, '$.outcome')) VIRTUAL;
ALTER TABLE labels ADD COLUMN outcome TEXT GENERATED ALWAYS AS (json_extract(record, '$.outcome')) VIRTUAL;
ALTER TABLE labels ADD COLUMN annotator TEXT GENERATED ALWAYS AS (json_extract(record, '$.annotator')) VIRTUAL;
ALTER TABLE labels ADD COLUMN inclusion_prob REAL GENERATED ALWAYS AS (json_extract(record, '$.inclusion_prob')) VIRTUAL;
ALTER TABLE labels ADD COLUMN created_at TEXT GENERATED ALWAYS AS (json_extract(record, '$.created_at')) VIRTUAL;