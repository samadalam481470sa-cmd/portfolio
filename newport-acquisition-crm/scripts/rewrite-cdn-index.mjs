#!/usr/bin/env node
/**
 * Rewrites dist/index.html so JS/CSS/favicon load from jsDelivr with absolute URLs.
 * Many GitHub raw CDNs serve .html as text/plain (browser shows source). Hosts that
 * do serve text/html (e.g. rawcdn.githack) still need assets from a MIME-correct CDN.
 *
 * Usage: node scripts/rewrite-cdn-index.mjs <commit-sha>
 */
import fs from 'node:fs'
import path from 'node:path'

const sha = process.argv[2]
if (!sha) {
  console.error('Usage: node scripts/rewrite-cdn-index.mjs <commit-sha>')
  process.exit(1)
}

const repo = 'samadalam481470sa-cmd/portfolio'
const cdn = `https://cdn.jsdelivr.net/gh/${repo}@${sha}`
const indexPath = path.resolve('dist/index.html')
let html = fs.readFileSync(indexPath, 'utf8')

html = html.replace(
  /(href|src)="\.\/(assets\/[^"]+|favicon\.svg)"/g,
  (_, attr, file) => `${attr}="${cdn}/${file}"`,
)

fs.writeFileSync(indexPath, html)
console.log(`Rewrote ${indexPath} → assets via ${cdn}`)
