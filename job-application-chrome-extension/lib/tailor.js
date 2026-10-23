/**
 * Per-role resume tailoring, shared by the Chrome extension and the GitLab
 * CI job-finder pipeline.
 *
 * What tailoring means here: taking the candidate's REAL resume content and
 * deciding what to lead with for a specific posting — which of their existing
 * skills to list first, which of their existing bullets are most relevant,
 * and which of the posting's keywords they currently don't evidence.
 *
 * What it explicitly does NOT do: add skills, employers, titles, dates,
 * metrics, or accomplishments that aren't already in the resume. Gaps are
 * reported as gaps for the human to decide on — never quietly filled in.
 */
(function (global) {
  function getMatcher() {
    if (typeof global.JobMatcher !== "undefined") return global.JobMatcher;
    return null;
  }

  function tokenSet(text) {
    const matcher = getMatcher();
    if (matcher) return new Set(matcher.tokenize(text));
    return new Set(
      String(text || "")
        .toLowerCase()
        .replace(/[^a-z0-9+#.\s]/g, " ")
        .split(/\s+/)
        .filter((t) => t.length > 2)
    );
  }

  /**
   * Ranks the candidate's own skills by how strongly the posting emphasizes
   * them. Returns { lead, remaining } — both drawn only from their resume.
   */
  function rankSkills(skills, jobText) {
    const jobTokens = tokenTally(jobText);
    const scored = (skills || []).map((skill) => {
      const parts = tokenSet(skill);
      let weight = 0;
      parts.forEach((part) => {
        weight += jobTokens.get(part) || 0;
      });
      return { skill, weight };
    });

    const lead = scored
      .filter((s) => s.weight > 0)
      .sort((a, b) => b.weight - a.weight)
      .map((s) => s.skill);
    const leadSet = new Set(lead);
    const remaining = (skills || []).filter((s) => !leadSet.has(s));
    return { lead, remaining };
  }

  function tokenTally(text) {
    const tally = new Map();
    tokenSet(text).forEach((t) => tally.set(t, (tally.get(t) || 0) + 1));
    // Weight by raw frequency in the posting so emphasized terms rank higher.
    const matcher = getMatcher();
    if (matcher) {
      matcher.tokenize(text).forEach((t) => tally.set(t, (tally.get(t) || 0) + 1));
    }
    return tally;
  }

  /**
   * Ranks the candidate's own resume bullets by keyword overlap with the
   * posting, so the most relevant real accomplishments go at the top.
   */
  function rankBullets(bullets, jobText, limit) {
    const jobTokens = tokenTally(jobText);
    const scored = (bullets || []).map((bullet) => {
      let overlap = 0;
      tokenSet(bullet).forEach((t) => {
        if (jobTokens.has(t)) overlap += jobTokens.get(t);
      });
      return { bullet, overlap };
    });

    const ranked = scored.filter((b) => b.overlap > 0).sort((a, b) => b.overlap - a.overlap);
    if (ranked.length === 0) return [];

    // Only keep bullets that are meaningfully related to this posting. A
    // bullet that barely grazes the job text (e.g. unrelated prior-career
    // work) shouldn't be recommended as something to lead with.
    const threshold = ranked[0].overlap * 0.35;
    return ranked
      .filter((b) => b.overlap >= threshold)
      .slice(0, limit || 6)
      .map((b) => b.bullet);
  }

  // Words that show up constantly in postings but aren't skills a candidate
  // could sensibly "add" to a resume. Without this, gap lists fill up with
  // noise like "salary", "business", "team".
  const NON_SKILL_WORDS = new Set(
    (
      "salary business design building products product methods company companies teams team people " +
      "customers customer users user global world class hiring candidates candidate applicants role roles " +
      "position positions opportunity opportunities benefits compensation equity insurance paid leave " +
      "office offices hybrid onsite remote location locations department mission vision values culture " +
      "growth impact scale scaling fast paced environment ability strong excellent great good help helping " +
      "working works ensure ensuring support supporting including included various across within " +
      "responsibilities requirements qualifications preferred plus bonus stack tools technologies " +
      "solutions services partners partner stakeholders cross functional collaborate collaboration " +
      "communication written verbal degree bachelors masters equivalent related field years experience " +
      "contribute contributing make making take taking join want wants love like looking seeking need needs " +
      "new best better own owning drive driving deliver delivering focus focused end ends part"
    ).split(/\s+/)
  );

  /**
   * Identifies posting keywords the resume doesn't evidence. These are
   * surfaced as honest gaps, never auto-added to the resume.
   */
  function findGaps(resumeText, skills, jobText, limit, companyName) {
    const matcher = getMatcher();
    if (!matcher) return [];
    const result = matcher.computeMatchScore(resumeText, skills, jobText);
    const companyTokens = new Set(tokenSet(companyName || ""));

    return (result.missing || [])
      .map((word) => word.replace(/[.,;:]+$/, ""))
      .filter((word) => word.length > 2 && !NON_SKILL_WORDS.has(word) && !companyTokens.has(word))
      .slice(0, limit || 10);
  }

  /**
   * Main entry point. Returns a tailoring plan for one posting.
   */
  function tailorForRole(profile, jobText, options) {
    const opts = options || {};
    const skillRanking = rankSkills(profile.skills, jobText);
    const bullets = rankBullets(profile.bullets, jobText, opts.bulletLimit || 6);
    const gaps = findGaps(profile.rawText || "", profile.skills || [], jobText, opts.gapLimit || 10, opts.companyName);

    const matcher = getMatcher();
    const score = matcher ? matcher.computeMatchScore(profile.rawText || "", profile.skills || [], jobText).score : null;

    return {
      score,
      leadSkills: skillRanking.lead,
      otherSkills: skillRanking.remaining,
      leadBullets: bullets,
      gaps,
    };
  }

  /**
   * Renders a tailoring plan as a Markdown "tweaked resume" for one role.
   * Everything rendered comes from the candidate's own resume; the only added
   * text is guidance and [BRACKETED] prompts they must resolve themselves.
   */
  function renderTailoredResume(profile, job, plan) {
    const lines = [];
    const title = job.title || "[ROLE]";
    const company = job.company || "[COMPANY]";

    lines.push(`# Resume tweaks for: ${title} @ ${company}`);
    lines.push("");
    lines.push(
      "> **This is a re-prioritization of your existing resume, not a new resume.** " +
        "Every skill and bullet below is already yours — only the ordering and emphasis changed. " +
        "Do not add anything from the 'Gaps' section unless it is genuinely true of you."
    );
    lines.push("");
    lines.push(`- **Posting:** ${job.url || "(no URL)"}`);
    if (plan.score !== null && plan.score !== undefined) lines.push(`- **Current match score:** ${plan.score}%`);
    lines.push("");

    lines.push("## 1. Skills to lead with");
    lines.push("");
    if (plan.leadSkills.length > 0) {
      lines.push("Move these to the front of your Technical Skills section (they're emphasized in the posting):");
      lines.push("");
      lines.push(plan.leadSkills.map((s) => `**${s}**`).join(" · "));
    } else {
      lines.push("_None of your listed skills appear verbatim in this posting — this may be a weak fit, or the posting may use different terminology._");
    }
    if (plan.otherSkills.length > 0) {
      lines.push("");
      lines.push(`Keep the rest after those: ${plan.otherSkills.join(", ")}`);
    }
    lines.push("");

    lines.push("## 2. Bullets to lead with");
    lines.push("");
    if (plan.leadBullets.length > 0) {
      lines.push("Your most relevant existing bullets for this role, in order:");
      lines.push("");
      plan.leadBullets.forEach((b) => lines.push(`- ${b}`));
    } else {
      lines.push("_No bullets overlapped strongly with this posting. Consider whether this role is a fit before applying._");
    }
    lines.push("");

    lines.push("## 3. Gaps — your call, do not fabricate");
    lines.push("");
    if (plan.gaps.length > 0) {
      lines.push("The posting emphasizes these, and your resume doesn't currently evidence them:");
      lines.push("");
      plan.gaps.forEach((g) => lines.push(`- \`${g}\``));
      lines.push("");
      lines.push(
        "For each one, pick honestly: (a) you have real experience and forgot to mention it — add it; " +
          "(b) you have adjacent/coursework exposure — mention it accurately as such; or " +
          "(c) you don't have it — leave it out. Claiming (c) as (a) is how offers get rescinded."
      );
    } else {
      lines.push("_No significant gaps detected._");
    }
    lines.push("");

    lines.push("## 4. Summary line to consider");
    lines.push("");
    const summaryBase = profile.summary && profile.summary.trim() ? profile.summary.trim() : "";
    if (summaryBase) {
      lines.push(`Your existing summary, with this role's emphasis: "${summaryBase}"`);
    } else {
      const topThree = plan.leadSkills.slice(0, 3);
      lines.push(
        `You don't have a summary section. If you want one for this application, build it from facts already in your resume — e.g. your degree, your current role, and ${
          topThree.length ? topThree.join("/") : "your strongest skills"
        }. [WRITE THIS IN YOUR OWN WORDS.]`
      );
    }
    lines.push("");

    return lines.join("\n");
  }

  global.ResumeFitTailor = { tailorForRole, renderTailoredResume, rankSkills, rankBullets, findGaps };

  if (typeof module !== "undefined" && module.exports) {
    module.exports = global.ResumeFitTailor;
  }
})(typeof window !== "undefined" ? window : globalThis);
