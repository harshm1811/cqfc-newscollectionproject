CREATE TABLE IF NOT EXISTS EQUITIES (
    ticker TEXT PRIMARY KEY,
    company_name TEXT,
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
);

CREATE TABLE IF NOT EXISTS SOURCES (
    source_id INTEGER PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,
    source_type TEXT,
    primary_source INTEGER NOT NULL DEFAULT 0 CHECK (primary_source IN (0, 1)),
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
);

CREATE TABLE IF NOT EXISTS ARTICLES (
    article_id TEXT PRIMARY KEY,
    ticker TEXT REFERENCES EQUITIES(ticker) ON UPDATE CASCADE ON DELETE SET NULL,
    source_id INTEGER REFERENCES SOURCES(source_id) ON DELETE SET NULL,
    title TEXT,
    description TEXT,
    url TEXT,
    published_at TEXT,
    first_seen_at TEXT,
    retrieved_at TEXT,
    clean_text TEXT,
    relevance_score REAL CHECK (relevance_score IS NULL OR relevance_score BETWEEN 0 AND 1),
    duplicate_cluster_id TEXT,
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
);

CREATE TABLE IF NOT EXISTS EVENTS (
    event_id TEXT PRIMARY KEY,
    ticker TEXT REFERENCES EQUITIES(ticker) ON UPDATE CASCADE ON DELETE SET NULL,
    type TEXT,
    timestamp TEXT,
    headline TEXT,
    sentiment_score REAL CHECK (sentiment_score IS NULL OR sentiment_score BETWEEN -1 AND 1),
    sentiment_probabilities_json TEXT CHECK (sentiment_probabilities_json IS NULL OR json_valid(sentiment_probabilities_json)),
    importance REAL CHECK (importance IS NULL OR importance BETWEEN 0 AND 1),
    article_count INTEGER CHECK (article_count IS NULL OR article_count >= 0),
    source_count INTEGER CHECK (source_count IS NULL OR source_count >= 0),
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
);

CREATE TABLE IF NOT EXISTS ARTICLE_EVENT_MAP (
    article_id TEXT NOT NULL REFERENCES ARTICLES(article_id) ON DELETE CASCADE,
    event_id TEXT NOT NULL REFERENCES EVENTS(event_id) ON DELETE CASCADE,
    PRIMARY KEY (article_id, event_id)
);

CREATE TABLE IF NOT EXISTS SENTIMENT_RESULTS (
    sentiment_id INTEGER PRIMARY KEY,
    article_id TEXT REFERENCES ARTICLES(article_id) ON DELETE CASCADE,
    event_id TEXT REFERENCES EVENTS(event_id) ON DELETE CASCADE,
    model_version TEXT,
    label TEXT,
    score REAL CHECK (score IS NULL OR score BETWEEN -1 AND 1),
    probabilities_json TEXT CHECK (probabilities_json IS NULL OR json_valid(probabilities_json)),
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    CHECK (article_id IS NOT NULL OR event_id IS NOT NULL)
);

CREATE TABLE IF NOT EXISTS DAILY_FEATURES (
    feature_id INTEGER PRIMARY KEY,
    ticker TEXT NOT NULL REFERENCES EQUITIES(ticker) ON UPDATE CASCADE ON DELETE CASCADE,
    feature_date TEXT NOT NULL,
    feature_name TEXT NOT NULL,
    feature_value REAL,
    source_run_id TEXT REFERENCES COLLECTION_RUNS(run_id) ON DELETE SET NULL,
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    UNIQUE (ticker, feature_date, feature_name)
);

CREATE TABLE IF NOT EXISTS COLLECTION_RUNS (
    run_id TEXT PRIMARY KEY,
    requested_ticker TEXT,
    start_time TEXT,
    end_time TEXT,
    configuration_json TEXT CHECK (configuration_json IS NULL OR json_valid(configuration_json)),
    collectors_json TEXT CHECK (collectors_json IS NULL OR json_valid(collectors_json)),
    model_versions_json TEXT CHECK (model_versions_json IS NULL OR json_valid(model_versions_json)),
    status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending','running','succeeded','partial_failure','failed')),
    article_count INTEGER NOT NULL DEFAULT 0 CHECK (article_count >= 0),
    event_count INTEGER NOT NULL DEFAULT 0 CHECK (event_count >= 0),
    failure_count INTEGER NOT NULL DEFAULT 0 CHECK (failure_count >= 0),
    failures_json TEXT CHECK (failures_json IS NULL OR json_valid(failures_json)),
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    FOREIGN KEY (requested_ticker) REFERENCES EQUITIES(ticker) ON UPDATE CASCADE ON DELETE SET NULL
);

CREATE INDEX IF NOT EXISTS idx_articles_ticker_published ON ARTICLES(ticker, published_at);
CREATE INDEX IF NOT EXISTS idx_articles_source ON ARTICLES(source_id);
CREATE INDEX IF NOT EXISTS idx_articles_duplicate_cluster ON ARTICLES(duplicate_cluster_id);
CREATE INDEX IF NOT EXISTS idx_events_ticker_timestamp ON EVENTS(ticker, timestamp);
CREATE INDEX IF NOT EXISTS idx_article_event_event ON ARTICLE_EVENT_MAP(event_id);
CREATE INDEX IF NOT EXISTS idx_sentiment_article ON SENTIMENT_RESULTS(article_id);
CREATE INDEX IF NOT EXISTS idx_sentiment_event ON SENTIMENT_RESULTS(event_id);
CREATE INDEX IF NOT EXISTS idx_daily_features_ticker_date ON DAILY_FEATURES(ticker, feature_date);
CREATE INDEX IF NOT EXISTS idx_runs_ticker_created ON COLLECTION_RUNS(requested_ticker, created_at);
