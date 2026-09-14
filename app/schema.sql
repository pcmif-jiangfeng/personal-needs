PRAGMA foreign_keys = ON;
BEGIN;
CREATE TABLE IF NOT EXISTS schema_migrations (
    version INTEGER PRIMARY KEY,
    applied_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
);
CREATE TABLE IF NOT EXISTS themes (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL UNIQUE CHECK(length(trim(name)) > 0),
    description TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
);
CREATE TABLE IF NOT EXISTS records (
    id INTEGER PRIMARY KEY,
    context TEXT NOT NULL CHECK(length(trim(context)) > 0),
    problem TEXT NOT NULL CHECK(length(trim(problem)) > 0),
    original_context TEXT NOT NULL,
    original_problem TEXT NOT NULL,
    original_feeling TEXT NOT NULL DEFAULT '[]' CHECK(json_valid(original_feeling) AND json_type(original_feeling) = 'array'),
    feeling TEXT NOT NULL DEFAULT '[]' CHECK(json_valid(feeling) AND json_type(feeling) = 'array'),
    feeling_note TEXT NOT NULL DEFAULT '',
    scene TEXT NOT NULL DEFAULT '其他',
    occurred_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    pain_score INTEGER CHECK(pain_score BETWEEN 1 AND 5),
    frequency_score INTEGER CHECK(frequency_score BETWEEN 1 AND 5),
    time_cost_score INTEGER CHECK(time_cost_score BETWEEN 1 AND 5),
    current_process TEXT NOT NULL DEFAULT '',
    pain_point TEXT NOT NULL DEFAULT '',
    current_solution TEXT NOT NULL DEFAULT '',
    solution_problem TEXT NOT NULL DEFAULT '',
    desired_state TEXT NOT NULL DEFAULT '',
    input TEXT NOT NULL DEFAULT '',
    output TEXT NOT NULL DEFAULT '',
    repeatability TEXT CHECK(repeatability IN ('一次性','偶尔','每月','每周','每天','高频')),
    standardizable TEXT CHECK(standardizable IN ('是','部分可以','不确定','否')),
    automation_potential INTEGER CHECK(automation_potential BETWEEN 1 AND 5),
    usage_intent INTEGER CHECK(usage_intent BETWEEN 1 AND 5),
    willingness_to_build TEXT CHECK(willingness_to_build IN ('不值得','30 分钟','几小时','一两天','一周','长期项目')),
    status TEXT NOT NULL DEFAULT 'Inbox' CHECK(status IN ('Inbox','Observing','Candidate','Project','Building','Solved','Archived')),
    related_need INTEGER REFERENCES themes(id) ON DELETE SET NULL
);
CREATE TABLE IF NOT EXISTS tags (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL CHECK(length(trim(name)) > 0),
    category TEXT NOT NULL DEFAULT 'custom' CHECK(category IN ('scene','problem','custom')),
    UNIQUE(name, category)
);
CREATE TABLE IF NOT EXISTS record_tags (
    record_id INTEGER NOT NULL REFERENCES records(id) ON DELETE CASCADE,
    tag_id INTEGER NOT NULL REFERENCES tags(id) ON DELETE CASCADE,
    PRIMARY KEY(record_id, tag_id)
);
CREATE INDEX IF NOT EXISTS idx_records_occurred ON records(occurred_at);
CREATE INDEX IF NOT EXISTS idx_records_theme ON records(related_need);
CREATE INDEX IF NOT EXISTS idx_records_status ON records(status);
CREATE INDEX IF NOT EXISTS idx_record_tags_tag ON record_tags(tag_id);
CREATE TRIGGER IF NOT EXISTS preserve_original_expression
BEFORE UPDATE OF original_context, original_problem, original_feeling ON records
WHEN NEW.original_context != OLD.original_context OR NEW.original_problem != OLD.original_problem OR NEW.original_feeling != OLD.original_feeling
BEGIN
    SELECT RAISE(ABORT, 'Original expression is immutable');
END;
INSERT OR IGNORE INTO schema_migrations(version) VALUES(1);
COMMIT;
