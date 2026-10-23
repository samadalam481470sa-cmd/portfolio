import { Router } from 'express'
import { z } from 'zod'
import { db } from '../db/index.ts'
import { requireAuth, requireRole, writeAudit, recordChange } from '../middleware/security.ts'

/**
 * Generic CRUD for the CRM module tables.
 * Column lists are the single source of truth for what clients may write.
 */

interface ResourceDef {
  table: string
  /** snake_case writable columns (id/timestamps excluded) */
  columns: string[]
  orderBy: string
}

const RESOURCES: Record<string, ResourceDef> = {
  contacts: {
    table: 'contacts',
    columns: [
      'name',
      'title',
      'company',
      'category',
      'email',
      'phone',
      'opportunity_id',
      'project_name',
      'status',
      'last_contact_date',
      'notes',
    ],
    orderBy: 'name ASC',
  },
  tasks: {
    table: 'tasks',
    columns: [
      'priority',
      'action',
      'opportunity_id',
      'project_name',
      'owner',
      'due_date',
      'status',
      'notes',
    ],
    orderBy: "CASE priority WHEN 'A' THEN 0 WHEN 'B' THEN 1 ELSE 2 END, due_date ASC",
  },
  sources: {
    table: 'sources',
    columns: ['name', 'firm', 'type', 'email', 'phone', 'status', 'deals_referred', 'notes'],
    orderBy: 'deals_referred DESC, name ASC',
  },
  carriers: {
    table: 'carriers',
    columns: [
      'name',
      'kind',
      'am_best_rating',
      'lines',
      'capacity_status',
      'contact_name',
      'contact_email',
      'notes',
    ],
    orderBy: 'name ASC',
  },
  portfolio: {
    table: 'portfolio_companies',
    columns: [
      'name',
      'acquired_date',
      'specialty',
      'geography',
      'nwp',
      'pf_ebitda',
      'integration_status',
      'deal_lead',
      'notes',
    ],
    orderBy: 'acquired_date DESC',
  },
  documents: {
    table: 'documents',
    columns: [
      'name',
      'doc_type',
      'opportunity_id',
      'project_name',
      'status',
      'confidentiality',
      'uploaded_by',
      'link',
      'uploaded_at',
      'notes',
    ],
    orderBy: 'uploaded_at DESC',
  },
}

const valueSchema = z.union([
  z.string().max(5000),
  z.number().finite(),
  z.boolean(),
  z.null(),
])
const payloadSchema = z.record(z.string(), valueSchema)

function snakeToCamel(s: string) {
  return s.replace(/_([a-z])/g, (_, c: string) => c.toUpperCase())
}
function camelToSnake(s: string) {
  return s.replace(/[A-Z]/g, (c) => `_${c.toLowerCase()}`)
}

function rowToApi(row: Record<string, unknown>) {
  const out: Record<string, unknown> = {}
  for (const [k, v] of Object.entries(row)) {
    if (k === 'created_at' || k === 'updated_at') continue
    out[snakeToCamel(k)] = v
  }
  return out
}

function isConstraintError(err: unknown): boolean {
  return (
    typeof err === 'object' &&
    err !== null &&
    'code' in err &&
    String((err as { code: unknown }).code).startsWith('SQLITE_CONSTRAINT')
  )
}

function pickWritable(def: ResourceDef, body: Record<string, unknown>) {
  const picked: Record<string, unknown> = {}
  for (const [key, value] of Object.entries(body)) {
    const col = camelToSnake(key)
    if (def.columns.includes(col)) picked[col] = value === false ? 0 : value === true ? 1 : value
  }
  return picked
}

export const resourcesRouter = Router()

resourcesRouter.use(requireAuth)

resourcesRouter.param('resource', (req, res, next, key: string) => {
  if (!RESOURCES[key]) return res.status(404).json({ error: 'Unknown resource' })
  next()
})

resourcesRouter.get('/:resource', (req, res) => {
  const def = RESOURCES[req.params.resource]
  const rows = db
    .prepare(`SELECT * FROM ${def.table} ORDER BY ${def.orderBy}`)
    .all() as Record<string, unknown>[]
  res.json(rows.map(rowToApi))
})

resourcesRouter.post('/:resource', requireRole('admin', 'partner', 'analyst'), (req, res) => {
  const def = RESOURCES[req.params.resource]
  const parsed = payloadSchema.safeParse(req.body)
  if (!parsed.success) return res.status(400).json({ error: 'Invalid payload' })

  const data = pickWritable(def, parsed.data)
  if (Object.keys(data).length === 0) {
    return res.status(400).json({ error: 'No writable fields provided' })
  }

  const id = `${req.params.resource.slice(0, 3)}_${Date.now()}_${Math.random()
    .toString(36)
    .slice(2, 7)}`
  const cols = ['id', ...Object.keys(data)]
  const placeholders = cols.map((c) => `@${c}`).join(', ')
  try {
    db.prepare(`INSERT INTO ${def.table} (${cols.join(', ')}) VALUES (${placeholders})`).run({
      id,
      ...data,
    })
  } catch (err) {
    if (isConstraintError(err)) {
      return res.status(400).json({ error: 'Missing or invalid required fields' })
    }
    throw err
  }

  const row = db.prepare(`SELECT * FROM ${def.table} WHERE id = ?`).get(id) as Record<
    string,
    unknown
  >

  writeAudit(
    req.auth!.userId,
    req.auth!.userName,
    `${req.params.resource}.create`,
    req.params.resource,
    id,
    `Created with fields: ${Object.keys(data).join(', ')}`,
    req,
  )
  recordChange(req, req.params.resource, id, 'create', null, row)

  res.status(201).json(rowToApi(row))
})

resourcesRouter.patch(
  '/:resource/:id',
  requireRole('admin', 'partner', 'analyst'),
  (req, res) => {
    const def = RESOURCES[req.params.resource]
    const parsed = payloadSchema.safeParse(req.body)
    if (!parsed.success) return res.status(400).json({ error: 'Invalid payload' })

    const existing = db
      .prepare(`SELECT * FROM ${def.table} WHERE id = ?`)
      .get(req.params.id) as Record<string, unknown> | undefined
    if (!existing) return res.status(404).json({ error: 'Record not found' })

    const data = pickWritable(def, parsed.data)
    if (Object.keys(data).length === 0) {
      return res.status(400).json({ error: 'No writable fields provided' })
    }

    const sets = Object.keys(data)
      .map((c) => `${c} = @${c}`)
      .join(', ')
    try {
      db.prepare(
        `UPDATE ${def.table} SET ${sets}, updated_at = datetime('now') WHERE id = @id`,
      ).run({ ...data, id: req.params.id })
    } catch (err) {
      if (isConstraintError(err)) {
        return res.status(400).json({ error: 'Missing or invalid required fields' })
      }
      throw err
    }

    const row = db
      .prepare(`SELECT * FROM ${def.table} WHERE id = ?`)
      .get(req.params.id) as Record<string, unknown>

    writeAudit(
      req.auth!.userId,
      req.auth!.userName,
      `${req.params.resource}.update`,
      req.params.resource,
      req.params.id,
      `Updated fields: ${Object.keys(data).join(', ')}`,
      req,
    )
    recordChange(req, req.params.resource, req.params.id, 'update', existing, row)

    res.json(rowToApi(row))
  },
)

  resourcesRouter.delete(
  '/:resource/:id',
  requireRole('admin', 'partner'),
  (req, res) => {
    const def = RESOURCES[req.params.resource]
    const existing = db
      .prepare(`SELECT * FROM ${def.table} WHERE id = ?`)
      .get(req.params.id) as Record<string, unknown> | undefined
    if (!existing) return res.status(404).json({ error: 'Record not found' })

    db.prepare(`DELETE FROM ${def.table} WHERE id = ?`).run(req.params.id)

    writeAudit(
      req.auth!.userId,
      req.auth!.userName,
      `${req.params.resource}.delete`,
      req.params.resource,
      req.params.id,
      'Record deleted',
      req,
    )
    recordChange(req, req.params.resource, req.params.id, 'delete', existing, null)

    res.json({ ok: true })
  },
)
