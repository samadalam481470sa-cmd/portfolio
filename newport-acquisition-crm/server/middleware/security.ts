import type { Request, Response, NextFunction } from 'express'
import rateLimit from 'express-rate-limit'
import { db, hashToken } from '../db/index.ts'

export interface AuthContext {
  userId: string
  userName: string
  role: string
  authMethod: 'demo' | 'api_key' | 'password'
  apiKeyId?: string
  sessionId: string
}

declare global {
  namespace Express {
    interface Request {
      auth?: AuthContext
    }
  }
}

export const authRateLimit = rateLimit({
  windowMs: 15 * 60 * 1000,
  max: 10,
  standardHeaders: true,
  legacyHeaders: false,
  message: { error: 'Too many authentication attempts. Try again later.' },
})

// ---------------------------------------------------------------------------
// Brute-force lockout: 5 failed credential attempts per IP → 30-minute lock.
// Kept in memory (resets on restart); rate limiting still applies regardless.
// ---------------------------------------------------------------------------
const MAX_FAILED_ATTEMPTS = 5
const FAILURE_WINDOW_MS = 15 * 60 * 1000
const LOCKOUT_MS = 30 * 60 * 1000

interface FailureRecord {
  count: number
  firstFailureAt: number
  lockedUntil: number | null
}

const failuresByIp = new Map<string, FailureRecord>()

setInterval(() => {
  const now = Date.now()
  for (const [ip, rec] of failuresByIp) {
    const lockExpired = rec.lockedUntil !== null && rec.lockedUntil < now
    const windowExpired = rec.lockedUntil === null && now - rec.firstFailureAt > FAILURE_WINDOW_MS
    if (lockExpired || windowExpired) failuresByIp.delete(ip)
  }
}, 60 * 1000).unref()

export function isLockedOut(ip: string | undefined): boolean {
  if (!ip) return false
  const rec = failuresByIp.get(ip)
  return !!rec?.lockedUntil && rec.lockedUntil > Date.now()
}

export function recordAuthFailure(ip: string | undefined, req?: Request): void {
  if (!ip) return
  const now = Date.now()
  const rec = failuresByIp.get(ip)
  if (!rec || now - rec.firstFailureAt > FAILURE_WINDOW_MS) {
    failuresByIp.set(ip, { count: 1, firstFailureAt: now, lockedUntil: null })
    return
  }
  rec.count += 1
  if (rec.count >= MAX_FAILED_ATTEMPTS && !rec.lockedUntil) {
    rec.lockedUntil = now + LOCKOUT_MS
    writeAudit(
      null,
      'system',
      'auth.lockout',
      'ip_address',
      ip,
      `IP locked for 30 minutes after ${rec.count} failed attempts`,
      req,
    )
  }
}

export function clearAuthFailures(ip: string | undefined): void {
  if (ip) failuresByIp.delete(ip)
}

export function lockoutGuard(req: Request, res: Response, next: NextFunction) {
  if (isLockedOut(req.ip)) {
    return res
      .status(429)
      .json({ error: 'Too many failed attempts. This address is temporarily locked.' })
  }
  return next()
}

export const apiRateLimit = rateLimit({
  windowMs: 60 * 1000,
  max: 120,
  standardHeaders: true,
  legacyHeaders: false,
  message: { error: 'Rate limit exceeded.' },
})

function getBearerOrApiKey(req: Request): string | null {
  const auth = req.header('authorization')
  if (auth?.startsWith('Bearer ')) return auth.slice(7).trim()
  const apiKey = req.header('x-api-key')
  if (apiKey) return apiKey.trim()
  return null
}

export function requireAuth(req: Request, res: Response, next: NextFunction) {
  const token = getBearerOrApiKey(req)
  if (!token) {
    return res.status(401).json({ error: 'Authentication required' })
  }

  // Session token path
  if (token.startsWith('nwp_sess_')) {
    const session = db
      .prepare(
        `SELECT s.id AS session_id, s.auth_method, s.api_key_id, s.expires_at,
                u.id AS user_id, u.name AS user_name, u.role
         FROM sessions s
         JOIN users u ON u.id = s.user_id
         WHERE s.token_hash = ?`,
      )
      .get(hashToken(token)) as
      | {
          session_id: string
          auth_method: AuthContext['authMethod']
          api_key_id: string | null
          expires_at: string
          user_id: string
          user_name: string
          role: string
        }
      | undefined

    if (!session) {
      return res.status(401).json({ error: 'Invalid or expired session' })
    }
    if (new Date(session.expires_at).getTime() < Date.now()) {
      db.prepare('DELETE FROM sessions WHERE id = ?').run(session.session_id)
      return res.status(401).json({ error: 'Session expired' })
    }

    req.auth = {
      userId: session.user_id,
      userName: session.user_name,
      role: session.role,
      authMethod: session.auth_method,
      apiKeyId: session.api_key_id ?? undefined,
      sessionId: session.session_id,
    }
    return next()
  }

  // Direct API key access (for programmatic clients — 5 reserved slots)
  if (isLockedOut(req.ip)) {
    return res
      .status(429)
      .json({ error: 'Too many failed attempts. This address is temporarily locked.' })
  }
  const key = db
    .prepare(
      `SELECT id, slot, status, key_hash FROM api_keys WHERE key_hash = ? AND status = 'active'`,
    )
    .get(hashToken(token)) as
    | { id: string; slot: number; status: string; key_hash: string }
    | undefined

  if (!key) {
    recordAuthFailure(req.ip, req)
    writeAudit(null, 'anonymous', 'auth.failed', 'api_key', null, 'Invalid API key', req)
    return res.status(401).json({ error: 'Invalid API key' })
  }
  clearAuthFailures(req.ip)

  db.prepare(`UPDATE api_keys SET last_used_at = datetime('now') WHERE id = ?`).run(key.id)

  // API-key-only access maps to a service principal (Dennis one-stop view scope)
  req.auth = {
    userId: 'user-dennis',
    userName: 'API Key Access',
    role: 'partner',
    authMethod: 'api_key',
    apiKeyId: key.id,
    sessionId: `api-${key.id}`,
  }
  return next()
}

export function requireRole(...roles: string[]) {
  return (req: Request, res: Response, next: NextFunction) => {
    if (!req.auth) return res.status(401).json({ error: 'Authentication required' })
    if (!roles.includes(req.auth.role) && req.auth.role !== 'admin') {
      writeAudit(
        req.auth.userId,
        req.auth.userName,
        'auth.forbidden',
        'route',
        req.path,
        `Role ${req.auth.role} denied`,
        req,
      )
      return res.status(403).json({ error: 'Insufficient permissions' })
    }
    return next()
  }
}

export function writeAudit(
  actorId: string | null,
  actorName: string | null,
  action: string,
  resourceType: string,
  resourceId: string | null,
  detail: string,
  req?: Request,
) {
  db.prepare(
    `INSERT INTO audit_logs (id, actor_id, actor_name, action, resource_type, resource_id, detail, ip_address)
     VALUES (@id, @actor_id, @actor_name, @action, @resource_type, @resource_id, @detail, @ip_address)`,
  ).run({
    id: `aud_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`,
    actor_id: actorId,
    actor_name: actorName,
    action,
    resource_type: resourceType,
    resource_id: resourceId,
    detail,
    ip_address: req?.ip ?? null,
  })
}

function resolveApiKeySlot(apiKeyId: string | undefined): number | null {
  if (!apiKeyId) return null
  const row = db.prepare(`SELECT slot FROM api_keys WHERE id = ?`).get(apiKeyId) as
    | { slot: number }
    | undefined
  return row?.slot ?? null
}

function diffFields(
  before: Record<string, unknown> | null,
  after: Record<string, unknown> | null,
): string[] {
  if (!before && after) return Object.keys(after)
  if (before && !after) return Object.keys(before)
  if (!before || !after) return []
  const keys = new Set([...Object.keys(before), ...Object.keys(after)])
  const changed: string[] = []
  for (const key of keys) {
    if (key === 'created_at' || key === 'updated_at') continue
    const a = JSON.stringify(before[key] ?? null)
    const b = JSON.stringify(after[key] ?? null)
    if (a !== b) changed.push(key)
  }
  return changed
}

/**
 * Permanently records a data change for any of the 5 API key users (or demo session).
 * before/after snapshots are stored as JSON so daily edits can be reconstructed.
 */
export function recordChange(
  req: Request,
  resourceType: string,
  resourceId: string,
  changeType: 'create' | 'update' | 'delete',
  before: Record<string, unknown> | null,
  after: Record<string, unknown> | null,
) {
  const auth = req.auth
  const changed = diffFields(before, after)
  db.prepare(
    `INSERT INTO change_history (
       id, actor_id, actor_name, api_key_id, api_key_slot, auth_method,
       resource_type, resource_id, change_type, before_json, after_json,
       changed_fields, ip_address
     ) VALUES (
       @id, @actor_id, @actor_name, @api_key_id, @api_key_slot, @auth_method,
       @resource_type, @resource_id, @change_type, @before_json, @after_json,
       @changed_fields, @ip_address
     )`,
  ).run({
    id: `chg_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`,
    actor_id: auth?.userId ?? null,
    actor_name: auth?.userName ?? null,
    api_key_id: auth?.apiKeyId ?? null,
    api_key_slot: resolveApiKeySlot(auth?.apiKeyId),
    auth_method: auth?.authMethod ?? 'demo',
    resource_type: resourceType,
    resource_id: resourceId,
    change_type: changeType,
    before_json: before ? JSON.stringify(before) : null,
    after_json: after ? JSON.stringify(after) : null,
    changed_fields: JSON.stringify(changed),
    ip_address: req.ip ?? null,
  })
}
