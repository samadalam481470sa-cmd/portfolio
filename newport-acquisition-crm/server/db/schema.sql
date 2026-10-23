-- Newport Specialty Partners Acquisition CRM Database
-- SQLite database for acquisition deal tracking (confidential M&A data).
-- Schema is the source of truth; replace SQLite with Postgres in production.

PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS users (
  id TEXT PRIMARY KEY,
  email TEXT NOT NULL UNIQUE,
  name TEXT NOT NULL,
  role TEXT NOT NULL CHECK (role IN ('admin', 'partner', 'analyst', 'viewer')),
  initials TEXT NOT NULL,
  password_hash TEXT,
  created_at TEXT NOT NULL DEFAULT (datetime('now')),
  updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

-- Exactly five API key slots for application access (keys provisioned by security team).
-- Only hashed keys are stored. Plaintext keys are never persisted.
CREATE TABLE IF NOT EXISTS api_keys (
  id TEXT PRIMARY KEY,
  slot INTEGER NOT NULL UNIQUE CHECK (slot BETWEEN 1 AND 5),
  label TEXT NOT NULL,
  key_prefix TEXT NOT NULL,
  key_hash TEXT,
  status TEXT NOT NULL DEFAULT 'pending'
    CHECK (status IN ('pending', 'active', 'revoked')),
  created_by TEXT,
  last_used_at TEXT,
  expires_at TEXT,
  created_at TEXT NOT NULL DEFAULT (datetime('now')),
  updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS sessions (
  id TEXT PRIMARY KEY,
  user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  token_hash TEXT NOT NULL UNIQUE,
  auth_method TEXT NOT NULL CHECK (auth_method IN ('demo', 'api_key', 'password')),
  api_key_id TEXT REFERENCES api_keys(id),
  ip_address TEXT,
  user_agent TEXT,
  expires_at TEXT NOT NULL,
  created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS opportunities (
  id TEXT PRIMARY KEY,
  project_number INTEGER NOT NULL UNIQUE,
  project_name TEXT NOT NULL,
  entity_name TEXT NOT NULL,
  type TEXT NOT NULL,
  status TEXT NOT NULL,
  stage TEXT NOT NULL,
  deal_lead TEXT NOT NULL DEFAULT '',
  source_type TEXT NOT NULL,
  source_name TEXT NOT NULL,
  specialty TEXT NOT NULL,
  geography TEXT NOT NULL,
  nwp REAL NOT NULL DEFAULT 0,
  net_revenue REAL NOT NULL DEFAULT 0,
  pf_ebitda REAL NOT NULL DEFAULT 0,
  next_action TEXT,
  next_action_date TEXT,
  priority TEXT NOT NULL DEFAULT 'C',
  last_activity_date TEXT NOT NULL,
  needs_attention INTEGER NOT NULL DEFAULT 0,
  attention_reasons TEXT NOT NULL DEFAULT '[]',
  outstanding_items TEXT NOT NULL DEFAULT '[]',
  diligence_notes TEXT NOT NULL DEFAULT '',
  created_at TEXT NOT NULL DEFAULT (datetime('now')),
  updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS audit_logs (
  id TEXT PRIMARY KEY,
  actor_id TEXT,
  actor_name TEXT,
  action TEXT NOT NULL,
  resource_type TEXT NOT NULL,
  resource_id TEXT,
  detail TEXT NOT NULL,
  ip_address TEXT,
  created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

-- Permanent record of every data change made by any of the 5 API key users
-- (or demo/password sessions). Stores before/after snapshots so daily edits
-- are never lost and can be attributed to a specific key slot.
CREATE TABLE IF NOT EXISTS change_history (
  id TEXT PRIMARY KEY,
  actor_id TEXT,
  actor_name TEXT,
  api_key_id TEXT,
  api_key_slot INTEGER,
  auth_method TEXT NOT NULL DEFAULT 'demo',
  resource_type TEXT NOT NULL,
  resource_id TEXT NOT NULL,
  change_type TEXT NOT NULL CHECK (change_type IN ('create', 'update', 'delete')),
  before_json TEXT,
  after_json TEXT,
  changed_fields TEXT NOT NULL DEFAULT '[]',
  ip_address TEXT,
  created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

-- Relationships: people tied to deals (management, bankers, counsel, accountants)
CREATE TABLE IF NOT EXISTS contacts (
  id TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  title TEXT NOT NULL DEFAULT '',
  company TEXT NOT NULL DEFAULT '',
  category TEXT NOT NULL DEFAULT 'Other',
  email TEXT NOT NULL DEFAULT '',
  phone TEXT NOT NULL DEFAULT '',
  opportunity_id TEXT,
  project_name TEXT NOT NULL DEFAULT '',
  status TEXT NOT NULL DEFAULT 'Active',
  last_contact_date TEXT,
  notes TEXT NOT NULL DEFAULT '',
  created_at TEXT NOT NULL DEFAULT (datetime('now')),
  updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

-- Tasks & follow-ups (A/B/C priorities)
CREATE TABLE IF NOT EXISTS tasks (
  id TEXT PRIMARY KEY,
  priority TEXT NOT NULL DEFAULT 'B',
  action TEXT NOT NULL,
  opportunity_id TEXT,
  project_name TEXT NOT NULL DEFAULT '',
  owner TEXT NOT NULL DEFAULT '',
  due_date TEXT,
  status TEXT NOT NULL DEFAULT 'Open',
  notes TEXT NOT NULL DEFAULT '',
  created_at TEXT NOT NULL DEFAULT (datetime('now')),
  updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

-- Deal sources: bankers and intermediaries
CREATE TABLE IF NOT EXISTS sources (
  id TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  firm TEXT NOT NULL DEFAULT '',
  type TEXT NOT NULL DEFAULT 'Investment Banker',
  email TEXT NOT NULL DEFAULT '',
  phone TEXT NOT NULL DEFAULT '',
  status TEXT NOT NULL DEFAULT 'Active',
  deals_referred INTEGER NOT NULL DEFAULT 0,
  notes TEXT NOT NULL DEFAULT '',
  created_at TEXT NOT NULL DEFAULT (datetime('now')),
  updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

-- Carriers / reinsurers capacity partners
CREATE TABLE IF NOT EXISTS carriers (
  id TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  kind TEXT NOT NULL DEFAULT 'Carrier',
  am_best_rating TEXT NOT NULL DEFAULT '',
  lines TEXT NOT NULL DEFAULT '',
  capacity_status TEXT NOT NULL DEFAULT 'Active',
  contact_name TEXT NOT NULL DEFAULT '',
  contact_email TEXT NOT NULL DEFAULT '',
  notes TEXT NOT NULL DEFAULT '',
  created_at TEXT NOT NULL DEFAULT (datetime('now')),
  updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

-- Completed acquisitions
CREATE TABLE IF NOT EXISTS portfolio_companies (
  id TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  acquired_date TEXT,
  specialty TEXT NOT NULL DEFAULT '',
  geography TEXT NOT NULL DEFAULT '',
  nwp REAL NOT NULL DEFAULT 0,
  pf_ebitda REAL NOT NULL DEFAULT 0,
  integration_status TEXT NOT NULL DEFAULT 'Integrating',
  deal_lead TEXT NOT NULL DEFAULT '',
  notes TEXT NOT NULL DEFAULT '',
  created_at TEXT NOT NULL DEFAULT (datetime('now')),
  updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

-- Deal document register (metadata; file storage via secure link)
CREATE TABLE IF NOT EXISTS documents (
  id TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  doc_type TEXT NOT NULL DEFAULT 'Other',
  opportunity_id TEXT,
  project_name TEXT NOT NULL DEFAULT '',
  status TEXT NOT NULL DEFAULT 'Draft',
  confidentiality TEXT NOT NULL DEFAULT 'Confidential',
  uploaded_by TEXT NOT NULL DEFAULT '',
  link TEXT NOT NULL DEFAULT '',
  uploaded_at TEXT NOT NULL DEFAULT (datetime('now')),
  notes TEXT NOT NULL DEFAULT '',
  created_at TEXT NOT NULL DEFAULT (datetime('now')),
  updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_opportunities_status ON opportunities(status);
CREATE INDEX IF NOT EXISTS idx_opportunities_stage ON opportunities(stage);
CREATE INDEX IF NOT EXISTS idx_sessions_token ON sessions(token_hash);
CREATE INDEX IF NOT EXISTS idx_audit_created ON audit_logs(created_at);
CREATE INDEX IF NOT EXISTS idx_change_history_created ON change_history(created_at);
CREATE INDEX IF NOT EXISTS idx_change_history_resource ON change_history(resource_type, resource_id);
CREATE INDEX IF NOT EXISTS idx_change_history_slot ON change_history(api_key_slot);
CREATE INDEX IF NOT EXISTS idx_contacts_opp ON contacts(opportunity_id);
CREATE INDEX IF NOT EXISTS idx_tasks_status ON tasks(status);
CREATE INDEX IF NOT EXISTS idx_documents_opp ON documents(opportunity_id);
