/**
 * Minimal HTML -> plain text conversion. Job APIs return descriptions as
 * HTML (sometimes double-escaped); we only need readable text for keyword
 * scoring and cover-letter drafting.
 */
const NAMED_ENTITIES = {
  amp: "&",
  lt: "<",
  gt: ">",
  quot: '"',
  apos: "'",
  nbsp: " ",
  ndash: "-",
  mdash: "-",
  hellip: "...",
  rsquo: "'",
  lsquo: "'",
  ldquo: '"',
  rdquo: '"',
};

function decodeEntities(text) {
  return (text || "")
    .replace(/&#(\d+);/g, (_, code) => String.fromCharCode(Number(code)))
    .replace(/&#x([0-9a-fA-F]+);/g, (_, code) => String.fromCharCode(parseInt(code, 16)))
    .replace(/&([a-zA-Z]+);/g, (match, name) => (NAMED_ENTITIES[name] !== undefined ? NAMED_ENTITIES[name] : match));
}

function stripHtml(input) {
  if (!input) return "";
  // Some APIs (e.g. Greenhouse) return HTML that is itself entity-escaped,
  // so decode first, then strip tags, then decode again.
  let text = decodeEntities(String(input));
  text = text
    .replace(/<\s*(script|style)[^>]*>[\s\S]*?<\s*\/\s*\1\s*>/gi, " ")
    .replace(/<\s*br\s*\/?\s*>/gi, "\n")
    .replace(/<\s*\/\s*(p|div|li|h[1-6]|tr)\s*>/gi, "\n")
    .replace(/<[^>]+>/g, " ");
  text = decodeEntities(text);
  return text
    .replace(/[ \t\u00a0]+/g, " ")
    .replace(/\n{3,}/g, "\n\n")
    .split("\n")
    .map((line) => line.trim())
    .join("\n")
    .trim();
}

module.exports = { stripHtml, decodeEntities };
