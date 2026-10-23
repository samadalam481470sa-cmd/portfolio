import { Router } from 'express'
import path from 'node:path'
import fs from 'node:fs'
import { fileURLToPath } from 'node:url'
import { db } from '../db/index.ts'
import { requireAuth, requireRole, writeAudit } from '../middleware/security.ts'
import { rowToOpportunity, type DbOpportunityRow } from '../mappers.ts'

const __dirname = path.dirname(fileURLToPath(import.meta.url))
const DB_PATH = path.resolve(__dirname, '../../data/newport-crm.db')

export const exportRouter = Router()

exportRouter.use(requireAuth)

function csvEscape(value: unknown): string {
  const s = value === null || value === undefined ? '' : String(value)
  if (/[",\n\r]/.test(s)) return `"${s.replace(/"/g, '""')}"`
  return s
}

const CSV_COLUMNS = [
  'projectNumber',
  'projectName',
  'entityName',
  'type',
  'status',
  'stage',
  'dealLead',
  'sourceType',
  'sourceName',
  'specialty',
  'geography',
  'nwp',
  'netRevenue',
  'pfEbitda',
  'nextAction',
  'nextActionDate',
  'priority',
  'lastActivityDate',
  'needsAttention',
  'attentionReasons',
  'outstandingItems',
  'diligenceNotes',
] as const

function getAllOpportunities() {
  const rows = db
    .prepare('SELECT * FROM opportunities ORDER BY project_number ASC')
    .all() as DbOpportunityRow[]
  return rows.map(rowToOpportunity)
}

/** CSV export — opens in Excel anywhere. */
exportRouter.get('/opportunities.csv', (req, res) => {
  const opportunities = getAllOpportunities()
  const header = CSV_COLUMNS.join(',')
  const lines = opportunities.map((o) =>
    CSV_COLUMNS.map((col) => {
      const v = o[col as keyof typeof o]
      if (Array.isArray(v)) return csvEscape(v.join('; '))
      return csvEscape(v)
    }).join(','),
  )
  const csv = [header, ...lines].join('\r\n')

  writeAudit(
    req.auth!.userId,
    req.auth!.userName,
    'export.csv',
    'opportunities',
    null,
    `Exported ${opportunities.length} records as CSV`,
    req,
  )

  res.setHeader('Content-Type', 'text/csv; charset=utf-8')
  res.setHeader(
    'Content-Disposition',
    `attachment; filename="newport-opportunities-${new Date().toISOString().slice(0, 10)}.csv"`,
  )
  res.send(csv)
})

/** JSON export — machine-readable snapshot for integrations. */
exportRouter.get('/opportunities.json', (req, res) => {
  const opportunities = getAllOpportunities()

  writeAudit(
    req.auth!.userId,
    req.auth!.userName,
    'export.json',
    'opportunities',
    null,
    `Exported ${opportunities.length} records as JSON`,
    req,
  )

  res.setHeader(
    'Content-Disposition',
    `attachment; filename="newport-opportunities-${new Date().toISOString().slice(0, 10)}.json"`,
  )
  res.json({
    exportedAt: new Date().toISOString(),
    recordCount: opportunities.length,
    opportunities,
  })
})

/** Full SQLite database download — partner/admin only. */
exportRouter.get('/database', requireRole('admin', 'partner'), (req, res) => {
  if (!fs.existsSync(DB_PATH)) {
    return res.status(404).json({ error: 'Database file not found' })
  }

  // Checkpoint WAL so the main file contains all committed writes
  db.pragma('wal_checkpoint(TRUNCATE)')

  writeAudit(
    req.auth!.userId,
    req.auth!.userName,
    'export.database',
    'database',
    null,
    'Downloaded full SQLite database file',
    req,
  )

  res.setHeader('Content-Type', 'application/vnd.sqlite3')
  res.setHeader(
    'Content-Disposition',
    `attachment; filename="newport-crm-${new Date().toISOString().slice(0, 10)}.db"`,
  )
  fs.createReadStream(DB_PATH).pipe(res)
})
