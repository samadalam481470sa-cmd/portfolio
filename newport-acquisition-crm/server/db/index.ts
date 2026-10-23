import Database from 'better-sqlite3'
import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'
import bcrypt from 'bcryptjs'
import { randomBytes, createHash } from 'node:crypto'
import { mockOpportunities } from '../../src/data/mockOpportunities.ts'
import {
  mockCarriers,
  mockContacts,
  mockDocuments,
  mockPortfolio,
  mockSources,
  mockTasksDb,
} from '../../src/data/mockModules.ts'

const __dirname = path.dirname(fileURLToPath(import.meta.url))
const dataDir = path.resolve(__dirname, '../../data')
const dbPath = path.join(dataDir, 'newport-crm.db')

fs.mkdirSync(dataDir, { recursive: true })

export const db = new Database(dbPath)
db.pragma('journal_mode = WAL')
db.pragma('foreign_keys = ON')

const schema = fs.readFileSync(path.join(__dirname, 'schema.sql'), 'utf8')
db.exec(schema)

function hashToken(token: string) {
  return createHash('sha256').update(token).digest('hex')
}

export function seedDatabase() {
  const userCount = db.prepare('SELECT COUNT(*) AS c FROM users').get() as { c: number }
  if (userCount.c === 0) {
    const insertUser = db.prepare(`
      INSERT INTO users (id, email, name, role, initials, password_hash)
      VALUES (@id, @email, @name, @role, @initials, @password_hash)
    `)
    insertUser.run({
      id: 'user-mary',
      email: 'mary@newportspecialty.demo',
      name: 'Mary Sbaschnig',
      role: 'partner',
      initials: 'MS',
      password_hash: bcrypt.hashSync('demo-only-not-for-production', 10),
    })
    insertUser.run({
      id: 'user-dennis',
      email: 'dennis@newportspecialty.demo',
      name: 'Dennis DiCapua',
      role: 'partner',
      initials: 'DD',
      password_hash: bcrypt.hashSync('demo-only-not-for-production', 10),
    })
  }

  const keyCount = db.prepare('SELECT COUNT(*) AS c FROM api_keys').get() as { c: number }
  if (keyCount.c === 0) {
    const insertKey = db.prepare(`
      INSERT INTO api_keys (id, slot, label, key_prefix, key_hash, status)
      VALUES (@id, @slot, @label, @key_prefix, @key_hash, @status)
    `)
    // Five reserved key slots. Security team provisions real keys later.
    // Slot 1 is seeded with a demo key for infrastructure testing only.
    const demoPlain = 'nwp_demo_key_slot1_replace_me_by_security_team'
    insertKey.run({
      id: 'key-slot-1',
      slot: 1,
      label: 'Primary integration (demo)',
      key_prefix: 'nwp_demo_',
      key_hash: hashToken(demoPlain),
      status: 'active',
    })
    for (let slot = 2; slot <= 5; slot++) {
      insertKey.run({
        id: `key-slot-${slot}`,
        slot,
        label: `Reserved slot ${slot}`,
        key_prefix: 'nwp_pending_',
        key_hash: null,
        status: 'pending',
      })
    }
  }

  const oppCount = db.prepare('SELECT COUNT(*) AS c FROM opportunities').get() as { c: number }
  if (oppCount.c === 0) {
    const insertOpp = db.prepare(`
      INSERT INTO opportunities (
        id, project_number, project_name, entity_name, type, status, stage,
        deal_lead, source_type, source_name, specialty, geography,
        nwp, net_revenue, pf_ebitda, next_action, next_action_date,
        priority, last_activity_date, needs_attention, attention_reasons,
        outstanding_items, diligence_notes
      ) VALUES (
        @id, @project_number, @project_name, @entity_name, @type, @status, @stage,
        @deal_lead, @source_type, @source_name, @specialty, @geography,
        @nwp, @net_revenue, @pf_ebitda, @next_action, @next_action_date,
        @priority, @last_activity_date, @needs_attention, @attention_reasons,
        @outstanding_items, @diligence_notes
      )
    `)

    const outstandingById: Record<string, string[]> = {
      'opp-guardian': ['Review initial materials', 'Confirm NDA scope with counsel'],
      'opp-jugular': ['Schedule follow-up with management', 'Call accountant re: broker comps'],
      'opp-beacon': ['Finalize LOI terms', 'Call lawyer on exclusivity language'],
      'opp-summit': ['Review diligence findings pack', 'Confirm data room access'],
      'opp-atlas': ['Confirm exclusivity extension'],
      'opp-vertex': ['Assign next action', 'Re-engage banker'],
      'opp-cipher': ['Assign deal lead'],
    }

    mockOpportunities.forEach((opp, index) => {
      insertOpp.run({
        id: opp.id,
        project_number: index + 1,
        project_name: opp.projectName,
        entity_name: opp.entityName,
        type: opp.type,
        status: opp.status,
        stage: opp.stage,
        deal_lead: opp.dealLead,
        source_type: opp.sourceType,
        source_name: opp.sourceName,
        specialty: opp.specialty,
        geography: opp.geography,
        nwp: opp.nwp,
        net_revenue: opp.netRevenue,
        pf_ebitda: opp.pfEbitda,
        next_action: opp.nextAction,
        next_action_date: opp.nextActionDate,
        priority: opp.priority,
        last_activity_date: opp.lastActivityDate,
        needs_attention: opp.needsAttention ? 1 : 0,
        attention_reasons: JSON.stringify(opp.attentionReasons),
        outstanding_items: JSON.stringify(outstandingById[opp.id] ?? []),
        diligence_notes:
          opp.stage === 'Due Diligence'
            ? 'Diligence in progress — financial, legal, and carrier reviews outstanding.'
            : '',
      })
    })
  }
}

function seedModuleTables() {
  const count = (table: string) =>
    (db.prepare(`SELECT COUNT(*) AS c FROM ${table}`).get() as { c: number }).c

  if (count('contacts') === 0) {
    const ins = db.prepare(`
      INSERT INTO contacts (id, name, title, company, category, email, phone,
        opportunity_id, project_name, status, last_contact_date, notes)
      VALUES (@id, @name, @title, @company, @category, @email, @phone,
        @opportunityId, @projectName, @status, @lastContactDate, @notes)
    `)
    mockContacts.forEach((r) => ins.run(r))
  }

  if (count('tasks') === 0) {
    const ins = db.prepare(`
      INSERT INTO tasks (id, priority, action, opportunity_id, project_name,
        owner, due_date, status, notes)
      VALUES (@id, @priority, @action, @opportunityId, @projectName,
        @owner, @dueDate, @status, @notes)
    `)
    mockTasksDb.forEach((r) => ins.run(r))
  }

  if (count('sources') === 0) {
    const ins = db.prepare(`
      INSERT INTO sources (id, name, firm, type, email, phone, status, deals_referred, notes)
      VALUES (@id, @name, @firm, @type, @email, @phone, @status, @dealsReferred, @notes)
    `)
    mockSources.forEach((r) => ins.run(r))
  }

  if (count('carriers') === 0) {
    const ins = db.prepare(`
      INSERT INTO carriers (id, name, kind, am_best_rating, lines, capacity_status,
        contact_name, contact_email, notes)
      VALUES (@id, @name, @kind, @amBestRating, @lines, @capacityStatus,
        @contactName, @contactEmail, @notes)
    `)
    mockCarriers.forEach((r) => ins.run(r))
  }

  if (count('portfolio_companies') === 0) {
    const ins = db.prepare(`
      INSERT INTO portfolio_companies (id, name, acquired_date, specialty, geography,
        nwp, pf_ebitda, integration_status, deal_lead, notes)
      VALUES (@id, @name, @acquiredDate, @specialty, @geography,
        @nwp, @pfEbitda, @integrationStatus, @dealLead, @notes)
    `)
    mockPortfolio.forEach((r) => ins.run(r))
  }

  if (count('documents') === 0) {
    const ins = db.prepare(`
      INSERT INTO documents (id, name, doc_type, opportunity_id, project_name, status,
        confidentiality, uploaded_by, link, uploaded_at, notes)
      VALUES (@id, @name, @docType, @opportunityId, @projectName, @status,
        @confidentiality, @uploadedBy, @link, @uploadedAt, @notes)
    `)
    mockDocuments.forEach((r) => ins.run(r))
  }
}

export function createSessionToken() {
  return `nwp_sess_${randomBytes(24).toString('hex')}`
}

export { hashToken }

seedDatabase()
seedModuleTables()
