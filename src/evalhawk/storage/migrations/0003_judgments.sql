-- Judgment cache (Phase 4): a verdict keyed by everything the judge saw, so identical
-- judgments across runs and repeats are reused instead of paid for again.
CREATE TABLE judgments (
    key TEXT PRIMARY KEY, judge_id TEXT NOT NULL, criterion_id TEXT NOT NULL, record TEXT NOT NULL
);
