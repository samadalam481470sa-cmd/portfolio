import 'dotenv/config'
import express from 'express'
import cors from 'cors'
import helmet from 'helmet'
import { apiRateLimit } from './middleware/security.ts'
import { authRouter } from './routes/auth.ts'
import { opportunitiesRouter } from './routes/opportunities.ts'
import { securityRouter } from './routes/security.ts'
import { exportRouter } from './routes/export.ts'
import { resourcesRouter } from './routes/resources.ts'
import './db/index.ts'

const app = express()
const PORT = Number(process.env.API_PORT || 3001)

app.set('trust proxy', 1)

app.use(
  helmet({
    // API serves JSON only; default-src 'none' blocks any attempt to render it
    contentSecurityPolicy: {
      directives: { defaultSrc: ["'none'"], frameAncestors: ["'none'"] },
    },
    crossOriginResourcePolicy: { policy: 'cross-origin' },
  }),
)
app.use(
  cors({
    origin: true,
    credentials: true,
    allowedHeaders: ['Content-Type', 'Authorization', 'X-API-Key', 'X-Request-Id'],
  }),
)
app.use(express.json({ limit: '100kb' }))
app.use(apiRateLimit)

app.get('/api/health', (_req, res) => {
  res.json({
    ok: true,
    service: 'newport-acquisition-crm',
    database: 'sqlite',
    apiKeySlots: 5,
  })
})

app.use('/api/auth', authRouter)
app.use('/api/opportunities', opportunitiesRouter)
app.use('/api/security', securityRouter)
app.use('/api/export', exportRouter)
app.use('/api/resources', resourcesRouter)

app.use((_req, res) => {
  res.status(404).json({ error: 'Not found' })
})

app.use(
  (
    err: Error,
    _req: express.Request,
    res: express.Response,
    _next: express.NextFunction,
  ) => {
    console.error(err)
    res.status(500).json({ error: 'Internal server error' })
  },
)

app.listen(PORT, '0.0.0.0', () => {
  console.log(`Newport CRM API listening on http://localhost:${PORT}`)
})
