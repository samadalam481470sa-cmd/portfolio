import { Router } from 'express'
import { db } from '../db/index.ts'
import { requireAuth, requireRole } from '../middleware/security.ts'

export const securityRouter = Router()

securityRouter.use(requireAuth)

/** Returns the five API key slots — never returns key hashes or secrets. */
securityRouter.get('/api-keys', requireRole('admin', 'partner'), (_req, res) => {
  const keys = db
    .prepare(
      `SELECT id, slot, label, key_prefix, status, last_used_at, expires_at, created_at
       FROM api_keys ORDER BY slot ASC`,
    )
    .all()
  res.json({
    slots: keys,
    capacity: 5,
    note: 'API keys are provisioned by the security team. This CRM stores only hashed values.',
  })
})

securityRouter.get('/audit-logs', requireRole('admin', 'partner'), (req, res) => {
  const limit = Math.min(Number(req.query.limit) || 50, 200)
  const logs = db
    .prepare(
      `SELECT id, actor_name, action, resource_type, resource_id, detail, created_at
       FROM audit_logs ORDER BY created_at DESC LIMIT ?`,
    )
    .all(limit)
  res.json(logs)
})

/**
 * Permanent change history for every create/update/delete across the database.
 * Filterable by API key slot (1–5), resource type, or specific record id so
 * daily edits by any of the five key holders can be reviewed.
 */
securityRouter.get('/change-history', requireRole('admin', 'partner'), (req, res) => {
  const limit = Math.min(Number(req.query.limit) || 100, 500)
  const slot = req.query.slot ? Number(req.query.slot) : null
  const resourceType = typeof req.query.resourceType === 'string' ? req.query.resourceType : null
  const resourceId = typeof req.query.resourceId === 'string' ? req.query.resourceId : null

  const clauses: string[] = []
  const params: unknown[] = []
  if (slot && slot >= 1 && slot <= 5) {
    clauses.push('api_key_slot = ?')
    params.push(slot)
  }
  if (resourceType) {
    clauses.push('resource_type = ?')
    params.push(resourceType)
  }
  if (resourceId) {
    clauses.push('resource_id = ?')
    params.push(resourceId)
  }

  const where = clauses.length ? `WHERE ${clauses.join(' AND ')}` : ''
  const rows = db
    .prepare(
      `SELECT id, actor_name, api_key_slot, auth_method, resource_type, resource_id,
              change_type, changed_fields, before_json, after_json, created_at
       FROM change_history ${where}
       ORDER BY created_at DESC LIMIT ?`,
    )
    .all(...params, limit) as Array<{
    id: string
    actor_name: string | null
    api_key_slot: number | null
    auth_method: string
    resource_type: string
    resource_id: string
    change_type: string
    changed_fields: string
    before_json: string | null
    after_json: string | null
    created_at: string
  }>

  res.json({
    count: rows.length,
    changes: rows.map((r) => ({
      id: r.id,
      actorName: r.actor_name,
      apiKeySlot: r.api_key_slot,
      authMethod: r.auth_method,
      resourceType: r.resource_type,
      resourceId: r.resource_id,
      changeType: r.change_type,
      changedFields: JSON.parse(r.changed_fields || '[]') as string[],
      before: r.before_json ? (JSON.parse(r.before_json) as Record<string, unknown>) : null,
      after: r.after_json ? (JSON.parse(r.after_json) as Record<string, unknown>) : null,
      createdAt: r.created_at,
    })),
  })
})

securityRouter.get('/me', (req, res) => {
  res.json({
    userId: req.auth!.userId,
    userName: req.auth!.userName,
    role: req.auth!.role,
    authMethod: req.auth!.authMethod,
    apiKeyId: req.auth!.apiKeyId ?? null,
  })
})
