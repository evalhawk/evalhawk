CREATE TABLE examples (id TEXT PRIMARY KEY, record TEXT NOT NULL);
CREATE TABLE example_tags (
    example_id TEXT NOT NULL REFERENCES examples(id), tag TEXT NOT NULL,
    PRIMARY KEY (example_id, tag)
);
CREATE INDEX tags_lookup ON example_tags(tag, example_id);
CREATE TABLE split_sets (id TEXT PRIMARY KEY, salt TEXT NOT NULL UNIQUE, record TEXT NOT NULL);
CREATE TABLE splits (
    split_set_id TEXT NOT NULL REFERENCES split_sets(id),
    example_id TEXT NOT NULL REFERENCES examples(id), split_key TEXT NOT NULL,
    group_id TEXT, split TEXT NOT NULL CHECK (split IN ('train','dev','test')),
    PRIMARY KEY (split_set_id, example_id)
);
CREATE INDEX splits_lookup ON splits(split_set_id, split, example_id);
CREATE TRIGGER splits_no_update BEFORE UPDATE ON splits
BEGIN SELECT RAISE(ABORT, 'splits are immutable'); END;
CREATE TRIGGER splits_no_delete BEFORE DELETE ON splits
BEGIN SELECT RAISE(ABORT, 'splits are immutable'); END;
CREATE TRIGGER split_sets_no_update BEFORE UPDATE ON split_sets
BEGIN SELECT RAISE(ABORT, 'split sets are immutable'); END;
CREATE TRIGGER split_sets_no_delete BEFORE DELETE ON split_sets
BEGIN SELECT RAISE(ABORT, 'split sets are immutable'); END;
CREATE TABLE runs (id TEXT PRIMARY KEY, record TEXT NOT NULL);
CREATE TABLE traces (
    id TEXT PRIMARY KEY, example_id TEXT NOT NULL REFERENCES examples(id),
    run_id TEXT NOT NULL REFERENCES runs(id), repeat_index INTEGER NOT NULL CHECK (repeat_index >= 0),
    record TEXT NOT NULL, UNIQUE (example_id, run_id, repeat_index)
);
CREATE TABLE criteria (id TEXT PRIMARY KEY, record TEXT NOT NULL);
CREATE TABLE verdicts (
    trace_id TEXT NOT NULL REFERENCES traces(id), criterion_id TEXT NOT NULL REFERENCES criteria(id),
    judge_id TEXT NOT NULL, record TEXT NOT NULL,
    PRIMARY KEY (trace_id, criterion_id, judge_id)
);
CREATE TABLE labels (
    id TEXT PRIMARY KEY, trace_id TEXT NOT NULL REFERENCES traces(id),
    criterion_id TEXT NOT NULL REFERENCES criteria(id), record TEXT NOT NULL
);
CREATE INDEX labels_lookup ON labels(trace_id, criterion_id, id);
CREATE TABLE test_access_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT, split_set_id TEXT NOT NULL REFERENCES split_sets(id),
    purpose TEXT NOT NULL, at TEXT NOT NULL
);