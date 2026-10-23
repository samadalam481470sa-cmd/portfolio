/**
 * Lightweight, heuristic resume-text parser.
 *
 * IMPORTANT: This never invents information. If something can't be found
 * in the resume text, the corresponding field is left blank so the user
 * can fill it in themselves.
 */
(function (global) {
  const EMAIL_RE = /[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}/;
  const PHONE_RE = /(\+?\d{1,3}[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}/;
  const LINKEDIN_RE = /(https?:\/\/)?(www\.)?linkedin\.com\/[a-zA-Z0-9\-_/%]+/i;
  const GITHUB_RE = /(https?:\/\/)?(www\.)?github\.com\/[a-zA-Z0-9\-_/%]+/i;
  const WEBSITE_RE = /(https?:\/\/)?(www\.)?[a-zA-Z0-9-]+\.(dev|io|me|co)\/[a-zA-Z0-9\-_./%]*/i;

  const SECTION_HEADERS = {
    skills: ["skills", "technical skills", "core competencies", "technologies", "skills & tools"],
    experience: ["experience", "work experience", "employment history", "professional experience", "relevant experience"],
    education: ["education", "academic background"],
    summary: ["summary", "professional summary", "objective", "about me", "profile"],
    projects: ["projects", "personal projects", "academic projects", "selected projects"],
    certifications: ["certifications", "certificates", "licenses", "awards", "honors"],
  };

  function extractFirstMatch(text, regex) {
    const match = text.match(regex);
    return match ? match[0].trim() : "";
  }

  function extractName(text) {
    const lines = text
      .split("\n")
      .map((l) => l.trim())
      .filter(Boolean);
    if (lines.length === 0) return "";
    // Heuristic: the name is almost always the first non-empty line,
    // as long as it doesn't look like an email/phone/section header and
    // isn't excessively long (which would suggest it's a sentence, not a name).
    const first = lines[0];
    const looksLikeContactInfo = EMAIL_RE.test(first) || PHONE_RE.test(first);
    const isReasonableLength = first.length > 0 && first.length <= 60;
    const wordCount = first.split(/\s+/).length;
    if (!looksLikeContactInfo && isReasonableLength && wordCount <= 5) {
      return first;
    }
    return "";
  }

  function extractLocation(text) {
    // Resumes almost always put "City, ST" in the header block.
    const headerLines = text.split("\n").slice(0, 6);
    for (const line of headerLines) {
      const placeholder = line.match(/\b(YOUR_CITY),\s*(YOUR_STATE)\b/);
      if (placeholder) return `${placeholder[1]}, ${placeholder[2]}`;
      const match = line.match(/\b([A-Z][a-zA-Z.'-]+(?:\s[A-Z][a-zA-Z.'-]+)*),\s*([A-Z]{2})\b/);
      if (match) return `${match[1]}, ${match[2]}`;
    }
    return "";
  }

  function findSectionIndex(lines, headerNames) {
    const normalized = lines.map((l) => l.trim().toLowerCase().replace(/[:\-–]+$/, ""));
    for (let i = 0; i < normalized.length; i++) {
      if (headerNames.includes(normalized[i])) return i;
    }
    return -1;
  }

  function extractSection(text, sectionKey) {
    const lines = text.split("\n");
    const headerNames = SECTION_HEADERS[sectionKey];
    const allHeaderNames = Object.values(SECTION_HEADERS).flat();
    const startIdx = findSectionIndex(lines, headerNames);
    if (startIdx === -1) return "";

    let endIdx = lines.length;
    const lowerLines = lines.map((l) => l.trim().toLowerCase().replace(/[:\-–]+$/, ""));
    for (let i = startIdx + 1; i < lines.length; i++) {
      if (allHeaderNames.includes(lowerLines[i]) && lowerLines[i] !== "") {
        endIdx = i;
        break;
      }
    }
    return lines
      .slice(startIdx + 1, endIdx)
      .join("\n")
      .trim();
  }

  function extractSkillsList(text) {
    const raw = extractSection(text, "skills");
    if (!raw) return [];
    // Skill sections are commonly written as "Category: item, item, item".
    // Drop the category label so it doesn't get stored as a skill.
    const withoutLabels = raw
      .split("\n")
      .map((line) => {
        const colonIdx = line.indexOf(":");
        return colonIdx > -1 && colonIdx < 40 ? line.slice(colonIdx + 1) : line;
      })
      .join("\n");

    return withoutLabels
      .split(/[\n,•|;]/)
      .map((s) => s.replace(/^[-*\s]+/, "").trim())
      .filter((s) => s.length > 1 && s.length < 40);
  }

  /**
   * Pulls individual bullet lines out of a section, so callers can rank and
   * re-order a candidate's real accomplishments per role.
   */
  function extractBullets(sectionText) {
    if (!sectionText) return [];
    return sectionText
      .split("\n")
      .map((line) => line.trim())
      .filter((line) => /^[•\-*\u2022\u25cf]/.test(line))
      .map((line) => line.replace(/^[•\-*\u2022\u25cf]+\s*/, "").trim())
      .filter((line) => line.length > 10);
  }

  function splitFullName(fullName) {
    const parts = fullName.trim().split(/\s+/);
    if (parts.length === 0) return { firstName: "", lastName: "" };
    if (parts.length === 1) return { firstName: parts[0], lastName: "" };
    return {
      firstName: parts[0],
      lastName: parts.slice(1).join(" "),
    };
  }

  /**
   * Parses raw resume text into a structured profile.
   * Every field defaults to an empty string/array rather than a guess.
   */
  function parseResume(text) {
    const cleanText = (text || "").replace(/\r\n/g, "\n");
    const name = extractName(cleanText);
    const { firstName, lastName } = splitFullName(name);

    return {
      name,
      firstName,
      lastName,
      email: extractFirstMatch(cleanText, EMAIL_RE),
      phone: extractFirstMatch(cleanText, PHONE_RE),
      linkedin: extractFirstMatch(cleanText, LINKEDIN_RE),
      website: extractFirstMatch(cleanText, GITHUB_RE) || extractFirstMatch(cleanText, WEBSITE_RE),
      location: extractLocation(cleanText),
      skills: extractSkillsList(cleanText),
      summary: extractSection(cleanText, "summary"),
      experience: extractSection(cleanText, "experience"),
      education: extractSection(cleanText, "education"),
      projects: extractSection(cleanText, "projects"),
      bullets: extractBullets(
        [extractSection(cleanText, "experience"), extractSection(cleanText, "projects")].filter(Boolean).join("\n")
      ),
      rawText: cleanText,
    };
  }

  global.ResumeParser = { parseResume, extractBullets, extractSection };

  // Also exported for Node (used by the GitLab CI job-finder pipeline).
  if (typeof module !== "undefined" && module.exports) {
    module.exports = global.ResumeParser;
  }
})(typeof window !== "undefined" ? window : globalThis);
