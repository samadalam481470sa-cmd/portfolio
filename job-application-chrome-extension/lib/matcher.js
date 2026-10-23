/**
 * Simple, transparent keyword-overlap scoring between a resume and a job
 * description. No AI guessing, no fabricated claims — just literal
 * keyword overlap so the user can judge fit for themselves.
 */
(function (global) {
  const STOPWORDS = new Set(
    (
      "a about above after again against all am an and any are aren't as at be because been before " +
      "being below between both but by can't cannot could couldn't did didn't do does doesn't doing don't " +
      "down during each few for from further had hadn't has hasn't have haven't having he he'd he'll he's " +
      "her here here's hers herself him himself his how how's i i'd i'll i'm i've if in into is isn't it it's " +
      "its itself let's me more most mustn't my myself no nor not of off on once only or other ought our ours " +
      "ourselves out over own same shan't she she'd she'll she's should shouldn't so some such than that " +
      "that's the their theirs them themselves then there there's these they they'd they'll they're they've " +
      "this those through to too under until up very was wasn't we we'd we'll we're we've were weren't what " +
      "what's when when's where where's which while who who's whom why why's with won't would wouldn't you " +
      "you'd you'll you're you've your yours yourself yourselves will etc using use used work works " +
      "role team join us we're looking role responsibilities requirements job description years experience"
    ).split(/\s+/)
  );

  function tokenize(text) {
    return (text || "")
      .toLowerCase()
      .replace(/[^a-z0-9+#.\s]/g, " ")
      .split(/\s+/)
      .map((t) => t.trim())
      .filter((t) => t.length > 2 && !STOPWORDS.has(t));
  }

  function wordFrequency(tokens) {
    const freq = new Map();
    for (const t of tokens) freq.set(t, (freq.get(t) || 0) + 1);
    return freq;
  }

  /**
   * Returns { score (0-100), matched: string[], missing: string[] }
   * comparing resume text/skills against a job description's text.
   */
  function computeMatchScore(resumeText, resumeSkills, jobText) {
    const resumeTokens = new Set([
      ...tokenize(resumeText),
      ...(resumeSkills || []).map((s) => s.toLowerCase().trim()),
    ]);
    const jobTokens = tokenize(jobText);
    const jobFreq = wordFrequency(jobTokens);

    // Rank job keywords by frequency so the most emphasized terms surface first.
    const rankedJobKeywords = Array.from(jobFreq.entries())
      .sort((a, b) => b[1] - a[1])
      .map(([word]) => word);

    const topKeywords = rankedJobKeywords.slice(0, 40);
    const matched = topKeywords.filter((word) => resumeTokens.has(word));
    const missing = topKeywords.filter((word) => !resumeTokens.has(word)).slice(0, 15);

    const score = topKeywords.length > 0 ? Math.round((matched.length / topKeywords.length) * 100) : 0;

    return {
      score,
      matched: matched.slice(0, 15),
      missing,
    };
  }

  global.JobMatcher = { tokenize, computeMatchScore };

  // Also exported for Node (used by the GitLab CI job-finder pipeline) so the
  // browser extension and the pipeline score jobs with identical logic.
  if (typeof module !== "undefined" && module.exports) {
    module.exports = global.JobMatcher;
  }
})(typeof window !== "undefined" ? window : globalThis);
