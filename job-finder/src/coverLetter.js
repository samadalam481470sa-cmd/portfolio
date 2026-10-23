/**
 * Builds a cover-letter *draft* for a matched posting.
 *
 * Hard rule: this only recombines facts that already exist in the user's
 * resume. Anything it cannot know (why this specific company, specific
 * metrics, referral names) is emitted as an explicit [BRACKETED PLACEHOLDER]
 * for the human to fill in — it is never invented.
 */
function firstMeaningfulLine(text) {
  if (!text) return "";
  const line = text
    .split("\n")
    .map((l) => l.replace(/^[-•*\s]+/, "").trim())
    .find((l) => l.length > 12);
  return line || "";
}

function buildCoverLetterDraft(profile, job) {
  const name = profile.name || "[YOUR NAME]";
  const company = job.company || "[COMPANY]";
  const title = job.title || "[ROLE]";

  const matchedSkills = (job.matched || []).filter((k) => k.length > 2).slice(0, 6);
  const skillsSentence = matchedSkills.length
    ? `My background lines up with several things in the posting — ${matchedSkills.join(", ")}.`
    : "";

  const summaryLine = profile.summary ? profile.summary.trim() : "";
  const experienceLine = firstMeaningfulLine(profile.experience);

  const paragraphs = [
    `Dear ${company} Hiring Team,`,
    `I'd like to apply for the ${title} role.${summaryLine ? ` ${summaryLine}` : ""}`,
    skillsSentence,
    experienceLine ? `Most recently: ${experienceLine}.` : "",
    `[ADD 1-2 SENTENCES: something specific about ${company} or this role that genuinely interests you — this is the part hiring managers actually read, so write it yourself.]`,
    `[OPTIONAL: add one concrete result from your experience with a real number, e.g. "cut page load time by 40%".]`,
    `Thanks for your time, and I'd welcome the chance to talk further.`,
    `Best regards,\n${name}`,
  ].filter(Boolean);

  const missing = (job.missing || []).slice(0, 8);

  return `# Cover letter DRAFT — ${title} @ ${company}

> **This is a draft, not a finished letter.** It only reassembles facts from
> your resume. Read it end to end, replace every \`[BRACKETED]\` placeholder,
> and rewrite anything that doesn't sound like you before sending. Do not
> submit it as-is.

- **Posting:** ${job.url || "(no URL)"}
- **Match score:** ${job.score}%
- **Keywords you already match:** ${matchedSkills.length ? matchedSkills.join(", ") : "(none detected)"}
- **Keywords in the posting missing from your resume:** ${missing.length ? missing.join(", ") : "(none detected)"}${
    missing.length
      ? "\n  - Only address these if you genuinely have the experience. Don't claim skills you don't have."
      : ""
  }

---

${paragraphs.join("\n\n")}
`;
}

module.exports = { buildCoverLetterDraft, firstMeaningfulLine };
