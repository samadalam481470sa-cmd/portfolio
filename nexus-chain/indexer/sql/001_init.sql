-- NEXUS off-chain indexer schema (PostgreSQL)
-- Chain state remains source of truth; rebuild is idempotent from RPC/WS.

CREATE TABLE IF NOT EXISTS blocks (
  height        BIGINT PRIMARY KEY,
  hash          TEXT NOT NULL,
  app_hash      TEXT NOT NULL,
  proposer      TEXT,
  block_time    TIMESTAMPTZ,
  tx_count      INT NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS transactions (
  hash          TEXT PRIMARY KEY,
  height        BIGINT NOT NULL REFERENCES blocks(height),
  tx_index      INT NOT NULL,
  sender        TEXT,
  fee_amount    BIGINT,
  fee_denom     TEXT,
  code          INT NOT NULL DEFAULT 0,
  raw           JSONB
);

CREATE TABLE IF NOT EXISTS events (
  id            BIGSERIAL PRIMARY KEY,
  height        BIGINT NOT NULL,
  tx_hash       TEXT,
  type          TEXT NOT NULL,
  attributes    JSONB NOT NULL DEFAULT '{}'::jsonb
);

CREATE TABLE IF NOT EXISTS assets (
  id            TEXT PRIMARY KEY,
  denom         TEXT UNIQUE NOT NULL,
  display_name  TEXT,
  decimals      INT,
  issuer        TEXT,
  status        TEXT,
  created_height BIGINT
);

CREATE TABLE IF NOT EXISTS attestations (
  id            TEXT PRIMARY KEY,
  subject_ref   TEXT,
  schema_id     TEXT,
  payload_hash  TEXT NOT NULL,
  signer        TEXT,
  anchored_height BIGINT,
  status        TEXT
);

CREATE TABLE IF NOT EXISTS oracle_reports (
  id            TEXT PRIMARY KEY,
  feed_id       TEXT NOT NULL,
  value         TEXT NOT NULL,
  decimals      INT,
  quorum_met    BOOLEAN,
  expires_height BIGINT,
  timestamp_unix BIGINT
);

CREATE TABLE IF NOT EXISTS settlements (
  id            TEXT PRIMARY KEY,
  status        TEXT,
  settled_height BIGINT,
  legs          JSONB,
  oracle_feed   TEXT,
  attestation_ref TEXT
);

CREATE INDEX IF NOT EXISTS idx_tx_height ON transactions(height);
CREATE INDEX IF NOT EXISTS idx_events_height ON events(height);
CREATE INDEX IF NOT EXISTS idx_oracle_feed ON oracle_reports(feed_id);
