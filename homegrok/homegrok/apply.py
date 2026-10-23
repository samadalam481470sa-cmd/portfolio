"""Application filler: opens job applications in HomeGrok's own Chrome window and fills them in.

  * Answers come from your current resume (profile.py) and your saved answers
    (workspace/config.json -> "apply_answers"), including every answer you give it later.
  * When it meets a required question it can't answer, the question appears on the HomeGrok
    page; once you answer, it fills it in and remembers the answer for every future application.
  * The HomeGrok page shows a live picture of the window. Click it to bring the window forward,
    change anything, and HomeGrok keeps filling whatever is still empty (it never overwrites you).
  * Several applications open as tabs in the same window. The window keeps its own Chrome
    profile, so sign-ins you let Chrome remember stay remembered.
It never clicks Submit, never types passwords, never creates accounts and never solves CAPTCHAs:
you review each application and submit it yourself. Uses no Claude usage.
"""
import json
import os
import re
import subprocess
import sys
import time

from .profile import current_resume, current_resume_info

# Your answers (you can change any of them in workspace/config.json -> "apply_answers").
# Every value below is a placeholder. Put your own name, address, phone, email, school,
# GPA, employers, and other details here before you apply. Do not commit real personal details.
DEFAULT_ANSWERS = {
    "degree": "YOUR_DEGREE",
    "school": ["YOUR_SCHOOL"],
    "start_date": "YOUR_START_DATE",
    "country": ["YOUR_COUNTRY"],
    "street": "YOUR_STREET_ADDRESS", "address_city": "YOUR_CITY", "state": ["YOUR_STATE", "YOUR_STATE_ABBR"], "zip": "YOUR_ZIP",
    "phone": "YOUR_PHONE", "email": "you@example.com",
    "current_city": ["YOUR_CITY, YOUR_STATE", "YOUR_CITY, YOUR_STATE_ABBR"],
    "school_start_month": "YOUR_START_MONTH", "school_start_year": "YOUR_START_YEAR",
    "grad_month": "YOUR_GRAD_MONTH", "grad_year": "YOUR_GRAD_YEAR",
    "gpa": "YOUR_GPA", "race": ["YOUR_RACE"], "veteran": "YOUR_VETERAN_STATUS", "hispanic": "YOUR_HISPANIC_LATINO",
    "citizen": "YOUR_ANSWER", "authorized": "YOUR_ANSWER", "sponsorship": "YOUR_ANSWER", "heard": "YOUR_REFERRAL_SOURCE",
    "work_authorization_needed": "YOUR_ANSWER",
    "gender": "YOUR_GENDER",
    "criminal_record": "YOUR_ANSWER",
    "salary_expectation": "YOUR_SALARY", "salary_digits": "YOUR_SALARY_MIN", "salary_end": "YOUR_SALARY_MAX",
    "custom": {},   # question -> answer, from what you answer on the HomeGrok page
}

FIND_FIELDS = r"""() => {
  const text = (n) => (n ? n.innerText || n.textContent || '' : '').replace(/\s+/g, ' ').trim();
  const ownLabel = (el) => {
    let t = el.getAttribute('aria-label') || '';
    if (el.id) { const l = document.querySelector(`label[for="${CSS.escape(el.id)}"]`); if (l) t += ' ' + text(l); }
    for (const id of (el.getAttribute('aria-labelledby') || '').split(' ')) if (id) t += ' ' + text(document.getElementById(id));
    if (el.closest('label')) t += ' ' + text(el.closest('label'));
    return t.trim();
  };
  // The question a field belongs to: the nearest container that holds only this field (or its option group).
  const question = (el) => {
    const fs = el.closest('fieldset'); if (fs) { const lg = fs.querySelector('legend'); if (lg) return text(lg); }
    let n = el.parentElement;
    while (n && n !== document.body) {
      const inputs = n.querySelectorAll('input:not([type=hidden]), select, textarea');
      const group = el.name ? n.querySelectorAll(`[name="${CSS.escape(el.name)}"]`).length : 1;
      if (inputs.length > Math.max(1, group)) break;
      const t = text(n); if (t.length > 2) return t.slice(0, 300);
      n = n.parentElement;
    }
    return '';
  };
  const out = []; let i = 0;
  for (const el of document.querySelectorAll('input, textarea, select')) {
    const type = (el.type || '').toLowerCase();
    if (['hidden', 'submit', 'button', 'image', 'reset', 'password', 'search'].includes(type)) continue;
    const box = el.getBoundingClientRect();
    const choice = ['checkbox', 'radio'].includes(type);
    if (type !== 'file' && !choice && (box.width === 0 || box.height === 0)) continue;
    const own = ownLabel(el);
    const q = choice ? question(el.closest('label') || el) : (own.length > 2 ? '' : question(el));
    const id = 'hg' + (i++);
    el.setAttribute('data-hg', id);
    const label = (own + ' ' + q + ' ' + (el.name || '') + ' ' + (el.placeholder || '')).replace(/\s+/g, ' ').trim();
    out.push({ id, tag: el.tagName.toLowerCase(), type, own, label: label.slice(0, 300), question: q,
               value: el.value || '', checked: !!el.checked,
               required: el.required || el.getAttribute('aria-required') === 'true' || /\*/.test(own + q),
               combo: el.getAttribute('role') === 'combobox' || !!el.getAttribute('aria-autocomplete'),
               options: el.tagName === 'SELECT' ? Array.from(el.options).map(o => o.text) : [] });
  }
  return out;
}"""

BANNER = """(msg) => {
  let d = document.getElementById('homegrok-banner');
  if (!d) { d = document.createElement('div'); d.id = 'homegrok-banner'; document.body.appendChild(d); }
  d.textContent = msg;
  d.style.cssText = 'position:fixed;top:0;left:0;right:0;z-index:2147483647;background:#3b3283;color:#fff;' +
                    'font:15px -apple-system,sans-serif;padding:12px 16px;text-align:center';
}"""

GENERIC = {"the", "of", "at", "in", "and", "or", "a", "an", "degree", "university", "college", "school", "s"}


def _words(text):
    return {w for w in re.findall(r"[a-z0-9&]+", text.lower().replace("'s", "")) if w not in GENERIC}


def same_answer(option, value):
    """True if a dropdown option really means the answer (not just a similar-looking one)."""
    o, v = _words(option), _words(value)
    return bool(o and v) and v <= o   # every distinctive word of the answer must be in the option


def question_key(text):
    """A stable name for a question, so a saved answer is found again on other applications."""
    text = re.sub(r"[^a-z0-9 ]+", " ", text.lower().replace("*", ""))
    return re.sub(r"\s+", " ", text).strip()[:120]


def profile_from_resume(text):
    """Contact and education details from the top of a resume."""
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    name = lines[0] if lines else ""
    p = {"name": name, "first": name.split()[0] if name else "", "last": name.split()[-1] if len(name.split()) > 1 else ""}
    if m := re.search(r"[\w.+-]+@[\w-]+\.[\w.]+", text):
        p["email"] = m.group()
    if m := re.search(r"\(?\d{3}\)?[\s.-]?\d{3}[\s.-]?\d{4}", text):
        p["phone"] = m.group()
    if m := re.search(r"(?:https?://)?(?:www\.)?linkedin\.com/in/[\w-]+/?", text, re.I):
        p["linkedin"] = m.group() if m.group().startswith("http") else "https://" + m.group()
    if m := re.search(r"(Bachelor|Master)[\w ]*? (?:of|in) [A-Z][\w ]+", text):
        p["major"] = re.sub(r".*? (?:of|in) (?:Science|Arts)? ?(?:in )?", "", m.group().strip()).strip()
    if m := re.search(r"Graduat\w*:?\s*([A-Z][a-z]+) (\d{4})", text):
        p["graduation"], p["grad_month"], p["grad_year"] = f"{m.group(1)} {m.group(2)}", m.group(1), m.group(2)
    return p


# Facts that are always true for you. Any yes/no answer to these questions, from any source
# (saved answers, Claude, past applications), is corrected to match.
FACT_GUARDS = [
    (re.compile(r"convicted|felony|criminal (?:offen|conviction|record|history)|legal proceeding", re.I), "YOUR_ANSWER"),
    (re.compile(r"sponsor|visa|h-?1b|immigration", re.I), "YOUR_ANSWER"),
    (re.compile(r"authori[sz]|legally (?:able|eligible|permitted)|eligible to work|right to work", re.I), "YOUR_ANSWER"),
    (re.compile(r"\bu\.?s\.? citizen|are you a citizen", re.I), "YOUR_ANSWER"),
]


def guard(question, value):
    """The last check before anything is typed: keep answers consistent with your real facts."""
    if not isinstance(value, str) or value.strip().lower() not in ("yes", "no"):
        return value
    for pattern, truth in FACT_GUARDS:
        if pattern.search(question or ""):
            return truth
    return value


FACT_CHECKS = [   # (question pattern, your saved value key, how to compare)
    (re.compile(r"\bgpa\b|grade point", re.I), "gpa", "number"),
    (re.compile(r"\bzip|postal", re.I), "zip", "digits"),
    (re.compile(r"school|university|college", re.I), "school", "school"),
]


def check_fact(question, value, a):
    """Before anything is typed: an answer that contradicts a saved fact is replaced by the saved fact."""
    if not isinstance(value, str) or not value.strip():
        return value
    for pattern, key, kind in FACT_CHECKS:
        if not pattern.search(question or ""):
            continue
        truth = a.get(key)
        if truth is None:
            continue
        if kind == "number":
            nums = re.findall(r"\d+(?:\.\d+)?", value)
            truth_nums = re.findall(r"\d+(?:\.\d+)?", str(truth))
            if nums and not truth_nums:
                return str(truth)
            if nums and truth_nums and float(nums[0]) != float(truth_nums[0]):
                return str(truth)
        elif kind == "digits":
            digits = re.sub(r"\D", "", value)
            if digits and digits != re.sub(r"\D", "", str(truth)):
                return str(truth)
        elif kind == "school":
            names = truth if isinstance(truth, list) else [truth]
            if not any(same_answer(value, n) for n in names):
                return names[0]
    return value


def answer_for(field, p, a):
    question = " ".join(x for x in (field.get("question"), field.get("own"), field.get("label")) if x)
    if re.match(r"\s*if (yes|no|you)\b", question, re.I):
        return None   # a follow-up question only applies to one answer; leave it empty unless asked
    return check_fact(question, guard(question, _answer_for(field, p, a)), a)


def _own_detail(saved, from_resume, placeholder):
    """Prefer a real saved answer, then the resume, then the committed placeholder."""
    if saved and saved != placeholder:
        return saved
    return from_resume or saved or placeholder


def _answer_for(field, p, a):
    """What to put in one form field, or None if HomeGrok doesn't know (then it asks you)."""
    custom = a.get("custom", {})
    for text in (field["question"], field["own"], field["label"]):
        if not text:
            continue
        qk = question_key(text)
        if qk in custom:
            return custom[qk]
        # a saved answer still matches when the page adds or drops a few words at the end
        for saved_key, saved in custom.items():
            n = min(len(qk), len(saved_key), 80)
            if n >= 40 and qk[:n] == saved_key[:n]:
                return saved
    rules = [
        (r"first name|given name|preferred name", p.get("first")), (r"last name|family name|surname", p.get("last")),
        (r"full name|^name\b|your name|legal name", p.get("name")),
        (r"e-?mail", _own_detail(a.get("email"), p.get("email"), "you@example.com")),
        (r"phone|mobile", _own_detail(a.get("phone"), p.get("phone"), "YOUR_PHONE")),
        (r"linkedin", p.get("linkedin")),
        (r"\bgpa\b|grade point", a["gpa"]), (r"school|university|college|institution", a["school"]),
        (r"discipline|major|field of study|area of study", p.get("major")), (r"\bdegree\b", a["degree"]),
        (r"end date month|graduation month", p.get("grad_month") or a.get("grad_month") or "YOUR_GRAD_MONTH"),
        (r"end date year|graduation year", p.get("grad_year") or a.get("grad_year") or "YOUR_GRAD_YEAR"),
        (r"start date month|start month", a["school_start_month"]), (r"start date year|start year", a["school_start_year"]),
        (r"graduat", p.get("graduation") or f"{a.get('grad_month', 'YOUR_GRAD_MONTH')} {a.get('grad_year', 'YOUR_GRAD_YEAR')}"),
        (r"\bgender\b|\bsex\b", a.get("gender", "YOUR_GENDER")), (r"hispanic|latin", a["hispanic"]), (r"\brace\b|ethnicity", a["race"]),
        (r"veteran", a["veteran"]),
        (r"how did you (?:hear|find|learn)|hear about (?:us|this)|where did you (?:hear|find|see)|brought you to (?:this|the) (?:job|posting|role)", a["heard"]),
        # "Do you currently have any work or employment authorization...?" is about needing one: a US citizen doesn't
        (r"(?:have|hold|need|require)\w*\s+(?:any\s+)?(?:current\s+)?(?:work|employment)\s+authori", a.get("work_authorization_needed", "No")),
        (r"convicted|felony|criminal (?:offen|conviction|record|history)|legal proceeding|jail|prison|incarcerat", a.get("criminal_record", "No")),
        # Salary ranges: the beginning gets the number in digits (forms reject "$" and commas); the end is yours to pick.
        (r"(?:beginning|minimum|lowest|from).{0,60}(?:salary|pay|compensation)|(?:salary|pay|compensation).{0,60}(?:beginning|minimum|lowest)",
         a.get("salary_digits", "YOUR_SALARY_MIN")),
        # The high end of a pay range. Replace YOUR_SALARY_MAX with your own number; forms need digits.
        (r"(?:end|maximum|highest|upper|to).{0,60}(?:salary|pay|compensation)|(?:salary|pay|compensation).{0,60}(?:end|maximum|highest)",
         a.get("salary_end", "YOUR_SALARY_MAX")),
        (r"salary|compensation|pay (?:expectation|range|rate)|desired pay|expected pay|hourly rate", a.get("salary_expectation", "YOUR_SALARY")),
        (r"authori[sz]ed|authori[sz]ation|legally (?:able|eligible|permitted)", a["authorized"]),
        (r"sponsor|visa", a["sponsorship"]),
        (r"citizen", a["citizen"]),
        (r"availab|in-?office|on-?site|days (?:a|per|/) ?week|days/week|shifts?\b|weekends?|overtime|hybrid",
         "Yes" if re.match(r"\s*(are|can|will|would|do|is)\b", field.get("own") or field.get("question") or "", re.I)
         else a.get("availability", "Available 24/7, any day and any shift")),
        (r"desired start|earliest start|when can you start|availab\w* to start|start date(?! (?:month|year))", a["start_date"]),
        (r"country", a["country"]), (r"street|address line|^address|home address", a["street"]),
        (r"zip|postal", a["zip"]), (r"\bstate\b|province", a["state"]),
        (r"current (?:city|location)|location|where are you (?:based|located)|city you live", a["current_city"]),
        (r"\bcity\b", a["address_city"]),
    ]
    # A long free-text question (a paragraph) only matches on its own words, never on a keyword buried in it:
    # A buried word such as "gender" inside a long prompt must not fill the gender answer.
    free_text = field.get("tag") == "textarea" or field.get("type") in ("text", "")
    for text in (field["own"], field["question"], field["label"]):
        text = text.lower()
        if free_text and len(text) > 160:
            continue
        for pattern, value in rules:
            if text and re.search(pattern, text):
                return value
    return None


def qtext(field):
    """The question as a person reads it on the page; never blank."""
    text = tidy(" ".join(x for x in (field.get("question"), field.get("own"), field.get("label")) if x)).strip()
    return (text or "A question on the application form (see the form)")[:200]


def option_matches(option, value):
    """Does a checkbox/radio option (like "3.5 - 4.0" or "Yes") match the answer?"""
    option, value = option.lower().strip(), str(value).lower()
    nums = [float(x) for x in re.findall(r"\d+\.\d+|\d+", option)]
    if re.fullmatch(r"\d+(\.\d+)?", value) and nums:
        v = float(value)
        if any(w in option for w in ("below", "under", "less")):
            return v <= nums[0]
        if any(w in option for w in ("above", "higher", "more")) or "+" in option:
            return v >= nums[0]
        return len(nums) >= 2 and nums[0] <= v <= nums[1]
    # Whole-option matches only: "No" must not match "Not really", and a short word must not match a longer one.
    return option == value or bool(re.match(re.escape(value) + r"[\s,(/.\-]", option))


def choose(options, wanted):
    for w in [wanted] if isinstance(wanted, str) else wanted:
        for i, o in enumerate(options):
            if same_answer(o, w) or (len(w) > 3 and w.lower() in o.lower()):
                return i
    return None


def search_terms(value):
    """What to type into a search-as-you-type list, most useful first.

    Search boxes match single distinctive words far better than long phrases ("City" finds
    "Example University - City"; the full phrase finds nothing), so those come first.
    """
    terms = []
    for v in ([value] if isinstance(value, str) else value):
        v = re.sub(r"^The ", "", v)
        words = [w for w in re.findall(r"[A-Za-z0-9&']+", v) if w.lower().replace("'s", "") not in GENERIC]
        if words:
            terms.append(words[-1])   # e.g. "City"
        terms.append(v)
    return list(dict.fromkeys(t for t in terms if len(t) >= 3))[:4]


def _visible_texts(frame, option_css):
    rows = frame.evaluate("""(css) => Array.from(document.querySelectorAll(css))
        .map(n => ({text: (n.innerText || '').trim(), visible: n.offsetParent !== null}))""", option_css)
    return [r["text"] for r in rows if r["visible"]][:300]


def _option_texts(frame, option_css):
    """Texts of the visible options, in the same order as _clickable() positions."""
    return _visible_texts(frame, option_css)


def _clickable(frame, option_css, text_index):
    """Locator for the Nth VISIBLE option (what a person sees)."""
    return frame.locator(option_css).filter(visible=True).nth(text_index)


def pick_from_dropdown(page, frame, loc, value):
    """Pick an option the way a person does: open the list and click the match.

    Short lists (Yes/No, countries, degrees) are read straight away. Long lists (schools) are
    searched by typing, and we wait until the list has actually filtered. Never presses Enter.
    Returns the chosen option's text, or the options it offered when nothing matched.
    """
    wanted = [value] if isinstance(value, str) else list(value)

    def option_css():
        # the list id only appears while the list is open, so read it at the time of use
        listbox = loc.get_attribute("aria-controls")
        return f'[id="{listbox}"] [role="option"]' if listbox else '[role="option"]'

    # the visible box of the dropdown (the text input itself can be only a few pixels wide)
    box = loc.locator("xpath=ancestor::*[contains(@class,'select__control')][1]")
    target = box if box.count() else loc

    def matches(text):
        return any(same_answer(text, w) for w in wanted)

    def click_match(texts):
        for k, text in enumerate(texts):
            if matches(text):
                _clickable(frame, option_css(), k).click(timeout=3000)
                return text or True
        return None

    # 0. start clean: close any menu left open by the field before, and bring this field into view
    page.keyboard.press("Escape")
    if not target.is_visible():
        target.scroll_into_view_if_needed(timeout=3000)
    # 1. open the list and look at it as it is
    target.click(timeout=3000)
    frame.wait_for_timeout(500)
    texts = _option_texts(frame, option_css())
    if texts and len(texts) <= 30:
        chosen = click_match(texts)
        if chosen:
            return chosen
        page.keyboard.press("Escape")
        return texts   # a short list without the answer: report it so the question can be asked

    # 2. long list: type to search, and wait for the list to show the typed words
    for term in search_terms(value):
        loc.click(timeout=3000)   # the text input itself: clicking the box again would close the list
        loc.fill("", timeout=3000)
        loc.press_sequentially(term, delay=25, timeout=5000)
        first_word = term.split()[0].lower()
        texts = []
        for _ in range(20):   # up to 5 seconds for the search to filter
            frame.wait_for_timeout(250)
            texts = _option_texts(frame, option_css())
            if texts and all(first_word in t.lower() for t in texts[:3]):
                break
        chosen = click_match(texts)
        if chosen:
            return chosen
    offered = _option_texts(frame, option_css())[:60]
    page.keyboard.press("Escape")   # close the menu; Escape never submits
    return offered


def tidy(text):
    """'Location (City)* Location (City)*' -> 'Location (City)*'."""
    text = re.sub(r"\s+", " ", text).strip()
    half = len(text) // 2
    for cut in range(half - 2, half + 3):
        if 0 < cut < len(text) and text[:cut].strip() and text[cut:].strip().startswith(text[:cut].strip()):
            return text[:cut].strip()
    return text


def dropdown_options(page, frame, loc):
    """Open a search-as-you-type dropdown just long enough to read its choices."""
    listbox = loc.get_attribute("aria-controls")
    loc.click()
    frame.wait_for_timeout(700)
    options = frame.locator(f'[id="{listbox}"] [role="option"]' if listbox else '[role="option"]:visible')
    offered = [options.nth(k).inner_text().strip() for k in range(min(options.count(), 60))]
    page.keyboard.press("Escape")
    return offered


SHOWN_VALUE = """(el) => { let n = el;
  for (let i = 0; i < 6 && n; i++) { n = n.parentElement; if (n && (n.innerText || '').trim()) return n.innerText; }
  return ''; }"""
MAX_TRIES = 3


def observe(loc, kind, expected=None):
    """Observe step (think -> act -> observe): did the action really stick?"""
    try:
        if kind == "check":
            return loc.is_checked()
        if kind == "combo":
            # a picked option closes the list; the field then shows the choice
            return bool(expected) and loc.get_attribute("aria-expanded") != "true"
        return bool(loc.input_value().strip())
    except Exception:
        return False


RETRY_SECONDS = 20   # a field that didn't take is retried at most this often (stops the page bouncing)


def _may_retry(tries, mark):
    """True if this field may be tried again now. `tries` maps mark -> [count, last_attempt_time]."""
    count, last = tries.get(mark, [0, 0.0])
    return time.time() - last >= RETRY_SECONDS


def _note_try(tries, mark):
    count, _ = tries.get(mark, [0, 0.0])
    tries[mark] = [count + 1, time.time()]


YESNO_JS = r"""() => [...document.querySelectorAll('button, [role=button]')]
  .filter(b => /^(yes|no)$/i.test((b.innerText || '').trim()) && b.offsetWidth > 0)
  .map((b, i) => {
    b.setAttribute('data-hgyn', String(i));
    let n = b.parentElement, question = '';
    for (let k = 0; k < 8 && n; k++, n = n.parentElement) {
      const t = (n.innerText || '').replace(/\s+/g, ' ').trim();
      if (t.includes('?')) { question = t.slice(0, t.indexOf('?') + 1).trim(); break; }
    }
    return { index: i, answer: b.innerText.trim(), question };
  })"""


def fill_yes_no(page, p, a, done):
    """Click Yes/No buttons whose question has a saved or known answer. Each question is answered once."""
    count = 0
    for row in page.evaluate(YESNO_JS):
        if not row["question"] or row["question"] in done:
            continue
        wanted = _answer_for({"question": row["question"], "own": row["question"], "label": row["question"]}, p, a)
        if not wanted or str(wanted).strip().lower() not in ("yes", "no"):
            continue
        if str(wanted).strip().lower() != row["answer"].lower():
            continue   # only the answer that is wanted gets clicked
        page.locator(f'[data-hgyn="{row["index"]}"]').first.click(timeout=5000)
        done.add(row["question"])
        count += 1
    return count


def open_yes_no(page, p, a, done):
    """Yes/No questions with no answer yet: they must come to you, never count as finished."""
    open_rows = []
    for row in page.evaluate(YESNO_JS):
        if not row["question"] or row["question"] in done:
            continue
        wanted = _answer_for({"question": row["question"], "own": row["question"], "label": row["question"]}, p, a)
        answered = wanted and str(wanted).strip().lower() in ("yes", "no")
        if not answered and row["question"] not in open_rows:
            open_rows.append(row["question"])
    return open_rows


def fill(page, p, a, resume_path, done, offers=None, tries=None):
    """One pass over the page: fill every empty field HomeGrok knows. Returns (filled, questions).

    `done` remembers what was already filled on this page, so anything you change yourself is left alone.
    """
    filled, questions = [], {}
    deadline = time.time() + PASS_SECONDS   # never hold the dashboard for longer than this; the next pass continues
    offers = {} if offers is None else offers   # dropdown choices seen on this page, by question
    tries = {} if tries is None else tries      # how often each answer was tried without sticking
    searched = {}
    for frame in page.frames:
        try:
            fields = frame.evaluate(FIND_FIELDS)
        except Exception:
            continue
        groups = {}
        for f in fields:
            if f["type"] in ("checkbox", "radio"):
                groups.setdefault(f["question"], []).append(f)
        for f in fields:
            if time.time() > deadline:
                break
            loc = frame.locator(f'[data-hg="{f["id"]}"]')
            choice = f["type"] in ("checkbox", "radio")
            key = question_key(f["question"] if choice else (f["own"] or f["label"]))
            try:
                if f["type"] == "file":
                    if "resume" not in done and (re.search(r"resume|cv", f["label"], re.I) or "file" not in done):
                        loc.set_input_files(str(resume_path))
                        done.update({"resume", "file"})
                        filled.append("Resume file")
                    continue
                if choice:
                    group = groups.get(f["question"], [])
                    if any(g["checked"] for g in group):
                        continue
                    value = answer_for({**f, "own": "", "label": f["question"]}, p, a)
                    wanted = value if isinstance(value, str) else (value[0] if value else None)
                    if f"{key}|{wanted}" in done:
                        continue
                    if wanted and option_matches(f["own"], wanted) and _may_retry(tries, key):
                        loc.check()
                        if observe(loc, "check") or tries.get(key, [0])[0] >= MAX_TRIES:
                            done.add(f"{key}|{wanted}")
                            filled.append(f"{f['question'][:40]}: {f['own'][:20]}")
                        else:
                            _note_try(tries, key)   # didn't stick: try again after the wait
                    elif not wanted and f["required"]:
                        questions[key] = {"key": key, "question": f["question"][:200],
                                          "options": [g["own"][:60] for g in group]}
                    continue
                if f["value"]:
                    continue
                value = answer_for(f, p, a)
                mark = f"{key}|{value}"
                if mark in done:   # already filled once (or tried): never overwrite what you changed
                    if f"failed|{mark}" in done and f["required"]:
                        questions[key] = {"key": key, "question": qtext(f),
                                          "options": offers.get(key, []), "searched": value, "partial": True}
                    continue
                if value is None and f["combo"] and key not in offers:
                    offers[key] = dropdown_options(page, frame, loc)
                if value is None:
                    if f["required"]:
                        questions[key] = {"key": key, "question": qtext(f),
                                          "options": f["options"][1:30] or offers.get(key, []),
                                          "partial": bool(f["combo"])}
                    continue
                if not _may_retry(tries, mark):
                    continue
                if f["tag"] == "select":
                    i = choose(f["options"], value)
                    if i is not None:
                        loc.select_option(index=i)
                        if observe(loc, "text") or tries.get(mark, [0])[0] >= MAX_TRIES:
                            done.add(mark)
                            filled.append(f["label"][:40])
                        else:
                            _note_try(tries, mark)
                    elif f["required"]:
                        questions[key] = {"key": key, "question": qtext(f),
                                          "options": f["options"][1:30]}
                elif f["combo"]:
                    result = pick_from_dropdown(page, frame, loc, value)
                    if result and not isinstance(result, list) and (observe(loc, "combo", result) or tries.get(mark, [0])[0] >= MAX_TRIES):
                        done.add(mark)
                        filled.append(f["label"][:40])
                    elif result and not isinstance(result, list):
                        _note_try(tries, mark)   # picked but not showing: try again after the wait
                    else:   # not in this employer's list: ask instead, showing what the list offers
                        done.update({mark, f"failed|{mark}"})
                        offers[key] = result
                        searched[key] = value
                        if f["required"]:
                            questions[key] = {"key": key, "question": qtext(f), "options": result,
                                              "searched": value, "partial": True}
                elif isinstance(value, (str, list)):
                    text_value = value if isinstance(value, str) else (value[0] if value else "")   # first spelling
                    loc.fill(text_value)
                    if observe(loc, "text") or (tries.get(mark, [0])[0] >= MAX_TRIES):
                        done.add(mark)
                        filled.append(f["label"][:40])
                    else:
                        _note_try(tries, mark)
            except Exception:
                pass
    still_empty = []
    for frame in page.frames:
        try:
            for f in frame.evaluate(FIND_FIELDS):
                if f["required"] and not f["value"] and f["type"] not in ("checkbox", "radio", "file") and not f["combo"]:
                    still_empty.append(tidy(f["own"] or f["label"])[:80])
        except Exception:
            continue
    asked = []
    for q in questions.values():
        q["question"] = tidy(q["question"])
        if len(q["question"]) > 2 and q["question"] not in {x["question"] for x in asked}:
            asked.append(q)
    return filled, asked, still_empty


def application_url(url):
    host = re.sub(r"^https?://", "", url).split("/")[0]
    if host == "jobs.lever.co" and not url.rstrip("/").endswith("/apply"):
        return url.split("?")[0].rstrip("/") + "/apply"
    if host == "jobs.ashbyhq.com" and "/application" not in url:
        return url.split("?")[0].rstrip("/") + "/application"
    return url


# -- Claude answers the questions HomeGrok doesn't know --------------------------------------
FACTS_TEXT = ("Placeholders only — replace them in homegrok/apply.py DEFAULT_ANSWERS before applying. "
              "School: YOUR_SCHOOL. Degree: YOUR_DEGREE. GPA: YOUR_GPA. "
              "Started YOUR_START_MONTH YOUR_START_YEAR, graduated YOUR_GRAD_MONTH YOUR_GRAD_YEAR. "
              "Lives in YOUR_CITY, YOUR_STATE. Check the resume before answering anything else.")
AI_SCHEMA = {"type": "object", "required": ["answers"], "properties": {"answers": {"type": "array", "items": {
    "type": "object", "required": ["key", "answer", "ask_user", "remember"],
    "properties": {"key": {"type": "string"}, "answer": {"type": "string"},
                   "ask_user": {"type": "boolean"}, "remember": {"type": "boolean"}}}}}}
AI_SYSTEM = """You answer job application questions for the user, like a careful human assistant would.
- Forms word the same question in different ways ("Will you need sponsorship?" / "Do you require a visa?"). Before anything else, check the saved answers and what the user said: if one of them answers the same thing, reuse it exactly. Learn from their previous answers.
- Use only facts from their resume, saved answers, memory note and what they said. Never invent experience, numbers, dates, awards or credentials.
- When a question lists options, answer with the exact text of one option. Never substitute a different school, employer, degree, major or place for the user's real one, even if it looks similar: if theirs isn't in the list, answer "Other" when an Other option exists, otherwise leave answer empty and set ask_user to true.
- Open questions (why this company, describe a project, and so on): write 2 to 4 sentences in the first person, specific to this job (use the posting) and grounded in the resume.
- Set ask_user to true only for important things you can't know or shouldn't guess, where a wrong answer could cost them the job or misstate something: salary expectations, willingness to relocate, references, legal attestations, signatures. Still put your best suggestion in answer.
- Set remember to true when the answer is a lasting fact about the user that other applications can reuse, false when it is specific to this job."""


def ai_answer(ws, questions, posting_text):
    """Ask Claude to answer a page's open questions. Returns [{key, answer, ask_user, remember}]."""
    from .brain import ClaudeBrain
    from .chatlog import ChatLog
    from .memory import Memory
    saved = {k: v for k, v in answers(ws).items() if k != "custom"}
    def describe(q):
        line = f"- key: {q['key']}\n  question: {q['question']}"
        if q.get("options"):
            line += f"\n  options: {' | '.join(q['options'][:60])}"
            if q.get("partial"):
                line += "\n  (searchable list: these are only the first entries, not all of them)"
        if q.get("searched"):
            line += f"\n  HomeGrok already searched this list for {q['searched']!r} and it is NOT in it."
        return line
    listed = "\n".join(describe(q) for q in questions)
    said = "\n".join(f"- {m}" for m in ChatLog(ws).user_messages(25))
    prompt = (f"<facts_always_true>\n{FACTS_TEXT}\n</facts_always_true>\n\n"
              f"<resume>\n{current_resume(ws)[:12000]}\n</resume>\n\n<saved_answers>\n{json.dumps(saved)}\n"
              f"{json.dumps(answers(ws).get('custom', {}))}\n</saved_answers>\n\n"
              f"<memory>\n{Memory(ws).note()}\n</memory>\n\n<user_said>\n{said}\n</user_said>\n\n"
              f"<job_posting>\n{posting_text[:8000]}\n</job_posting>\n\n<questions>\n{listed}\n</questions>\n\n"
              "Answer every question, using each question's key.")
    reply = ClaudeBrain(ws).ask(prompt, AI_SYSTEM, kind="chat", json_schema=AI_SCHEMA, timeout=420, effort="high")
    return [a for a in (reply["data"] or {}).get("answers", []) if isinstance(a, dict) and a.get("key")]


STUCK_SECONDS = 60
PASS_SECONDS = 8   # one pass of filling works for at most this long, so status and live view stay current
SALARY_Q = re.compile(r"salary|compensation|pay (?:expectation|range|rate)|desired pay|expected pay|hourly rate|"
                      r"\\$\\s*\\d", re.I)
SUBMITTABLE = re.compile(r"greenhouse\.io|jobs\.lever\.co|jobs\.ashbyhq\.com")
CONFIRMED = re.compile(r"thanks? (?:you )?for (?:applying|your application|your interest)|application (?:has been |was )?"
                       r"(?:received|submitted)|your application (?:has been )?(?:received|submitted)|"
                       r"we.ve received your application|successfully submitted|application submitted", re.I)
HUMAN_CHECK = re.compile(r"verify (?:that )?you(?:'| a)re (?:a )?human|are you a robot|complete the captcha", re.I)
CHALLENGE_FRAMES = 'iframe[src*="recaptcha/api2/bframe"], iframe[src*="hcaptcha.com"][src*="challenge"], iframe[title*="challenge" i]'


def human_check_showing(page):
    """A CAPTCHA challenge or 'verify you're human' step is on screen (HomeGrok never tries to pass these)."""
    try:
        for frame in page.locator(CHALLENGE_FRAMES).all():
            if frame.is_visible():
                return True
        return bool(HUMAN_CHECK.search(page.inner_text("body", timeout=3000)[:20000]))
    except Exception:
        return False


SUBMIT_NAME = re.compile(r"^\s*submit( application)?\s*$", re.I)
VALIDATION = re.compile(r"is required|please (?:fix|enter|select|complete)|invalid|must be|required field", re.I)


def submit_application(page):
    """Click Submit once, then watch what the page does. Returns a status and, when it fails, why.

    "submitted"   the employer's confirmation (or the page left the form) was seen
    "invalid"     the form reported missing or wrong fields; nothing was sent, and the fields are returned
    "needs_you"   a human check appeared, or the result could not be confirmed
    "no_button"   no Submit button was found
    """
    # Only a button named exactly "Submit" / "Submit Application": a page can have other submit-type buttons
    # (e.g. "All Jobs", "Apply with LinkedIn") that must never be clicked here.
    button = page.get_by_role("button", name=SUBMIT_NAME).first
    try:
        button.wait_for(state="visible", timeout=10000)
    except Exception:
        return "no_button", []
    before = page.url
    button.scroll_into_view_if_needed(timeout=5000)
    button.click(timeout=5000)
    body = ""
    for _ in range(45):   # up to ~45 seconds
        page.wait_for_timeout(1000)
        if human_check_showing(page):
            return "needs_you", []
        try:
            body = page.inner_text("body", timeout=3000)[:20000]
        except Exception:
            body = ""
        if CONFIRMED.search(body) or page.url != before:
            return "submitted", []
        if VALIDATION.search(body):
            errors = [line.strip() for line in body.splitlines() if VALIDATION.search(line)][:10]
            return "invalid", errors
    # Not confirmed: keep what the page said, so you can see whether it went through.
    return "needs_you", ["No confirmation was seen. The page now says: " + " ".join(body.split())[:300]]


SNAPSHOT_JS = r"""() => {
  const skip = ['hidden', 'submit', 'button', 'file'];
  const rows = [];
  for (const n of document.querySelectorAll('input, textarea, select')) {
    if (skip.includes((n.type || '').toLowerCase())) continue;
    let label = n.getAttribute('aria-label') || '';
    if (n.id) { const l = document.querySelector('label[for="' + CSS.escape(n.id) + '"]'); if (l) label += ' ' + l.innerText; }
    let shown = n.value || '';
    const box = n.closest('[class*="select__control"], [class*="select-container"]');
    if (box) {   // a dropdown: take the chosen value, never the whole list of options
      const chosen = box.querySelector('[class*="singleValue"], [class*="single-value"]');
      shown = chosen ? (chosen.innerText || '').trim() : '';
      if (!shown && n.value && n.value.length < 60) shown = n.value;
    }
    if (!shown && !box && ['checkbox', 'radio'].includes((n.type || '').toLowerCase())) shown = n.checked ? 'checked' : '';
    shown = shown.replace(/\s+/g, ' ').trim();
    if (!shown || shown.length > 160 || label.trim() === 'Search') continue;
    rows.push({label: (label.replace(/\s+/g, ' ').trim() || n.name || n.id || '(field)').slice(0, 160), value: shown.slice(0, 160)});
  }
  return rows;
}"""


def snapshot_answers(page):
    """Every field the page holds right before Submit: what was actually sent."""
    rows = []
    for frame in page.frames:
        try:
            rows += frame.evaluate(SNAPSHOT_JS)
        except Exception:
            continue
    return rows[:150]


def record_submit(ws, url, title, result, answers_sent=None):
    path = apply_dir(ws) / "submitted.json"
    items = json.loads(path.read_text()) if path.exists() else []
    items.append({"url": url, "title": title, "result": result, "time": time.time(), "answers": answers_sent or []})
    path.write_text(json.dumps(items[-500:]))


def pause_auto_mode(ws, seconds=600):
    """Auto mode waits this long before opening another window (used after a window closes or crashes)."""
    (apply_dir(ws) / "cooldown.json").write_text(json.dumps({"until": time.time() + seconds}))


RETRYABLE = {"no_button", "invalid"}
RETRY_LIMIT = 3   # a posting that was started but not submitted is tried again, at most this many times in all


def retry_urls(ws):
    """Applications started but not submitted (needs you, no button, invalid), still under the retry cap."""
    latest, tries = {}, {}
    for item in submitted_list(ws):
        tries[item["url"]] = tries.get(item["url"], 0) + 1
        latest[item["url"]] = item["result"]
    skipped = {x["url"] for x in skipped_list(ws)}
    # Only results that prove nothing was sent are retried. "needs_you" may already have been sent, so it is never
    # retried automatically: a second submission to an employer is a duplicate.
    return [u for u, result in latest.items()
            if result in RETRYABLE and tries[u] < RETRY_LIMIT and u not in skipped]


def submitted_list(ws):
    path = apply_dir(ws) / "submitted.json"
    return json.loads(path.read_text()) if path.exists() else []
WAIT_FOR_YOU_SECONDS = 300
SCHOOL_Q = re.compile(r"school|university|college|institution", re.I)


def record_skip(ws, url, title, reason):
    path = apply_dir(ws) / "skipped.json"
    skipped = json.loads(path.read_text()) if path.exists() else []
    skipped = [s for s in skipped if s["url"] != url] + [{"url": url, "title": title, "reason": reason, "time": time.time()}]
    path.write_text(json.dumps(skipped[-200:]))


def skipped_list(ws):
    path = apply_dir(ws) / "skipped.json"
    return json.loads(path.read_text()) if path.exists() else []


# -- shared state between the filler process and the HomeGrok server ---------------------------
def apply_dir(ws):
    d = ws.root / "apply"
    d.mkdir(exist_ok=True)
    return d


def read_status(ws):
    try:
        status = json.loads((apply_dir(ws) / "status.json").read_text())
    except (OSError, ValueError):
        return {"running": False}
    try:
        os.kill(status.get("pid", 0), 0)
    except OSError:
        status["running"] = False
    return status


def answers(ws):
    cfg = ws.load_config()
    return {**DEFAULT_ANSWERS, **cfg.get("apply_answers", {}), "auto_submit": bool(cfg.get("auto_submit"))}


def save_answer(ws, key, answer):
    cfg = ws.load_config()
    cfg.setdefault("apply_answers", {}).setdefault("custom", {})[key] = answer
    ws.save_config(cfg)


def opened(ws):
    path = apply_dir(ws) / "opened.json"
    return json.loads(path.read_text()) if path.exists() else []


def start(ws, url):
    """Open an application: as a new tab if the filler window is already open, else a new window."""
    seen = opened(ws)
    if url not in seen:
        (apply_dir(ws) / "opened.json").write_text(json.dumps((seen + [url])[-2000:]))
    if read_status(ws).get("running"):
        with open(apply_dir(ws) / "queue.txt", "a") as f:
            f.write(url + "\n")
        return
    from .config import PROJECT_ROOT
    with open(ws.logs / "apply.log", "a") as log_file:   # the child keeps its own copy; close ours
        subprocess.Popen([sys.executable, "-m", "homegrok", "--workspace", str(ws.root), "apply", url],
                         cwd=PROJECT_ROOT, stdout=log_file, stderr=log_file, start_new_session=True)


GLITCH_WINDOW = 20      # seconds of scroll history to judge
GLITCH_REVERSALS = 4    # direction changes in that window that count as a glitch
GLITCH_MIN_JUMP = 150   # pixels; smaller wobbles are normal


def is_glitching(samples):
    """samples: [(time, scrollY)]. True if the page keeps jumping back and forth."""
    now = time.time()
    recent = [(t, y) for t, y in samples if now - t <= GLITCH_WINDOW]
    if len(recent) < 4:
        return False
    reversals, last_dir = 0, 0
    for (t0, y0), (t1, y1) in zip(recent, recent[1:]):
        step = y1 - y0
        if abs(step) < GLITCH_MIN_JUMP:
            continue
        direction = 1 if step > 0 else -1
        if last_dir and direction != last_dir:
            reversals += 1
        last_dir = direction
    return reversals >= GLITCH_REVERSALS


def next_fresh_application(ws):
    """The best fillable job not tried yet, or None."""
    import json as _json
    from .jobs import JobScout
    tried = set(opened(ws))
    for j in JobScout(ws).open_jobs(limit=60, url_filter=FILLABLE_URL):
        if j["url"] not in tried:
            return j["url"]
    return None


FILLABLE_URL = re.compile(r"greenhouse\.io|jobs\.lever\.co|jobs\.ashbyhq\.com")


CODE_PROMPT = re.compile(r"verification code|security code|confirmation code|one[- ]time (?:code|password|passcode)|"
                         r"enter (?:the |your )?(?:\d+[- ]digit |\w+ )?code|verify your (?:email|identity)", re.I)
CODE_SENDERS = "from:(greenhouse OR lever OR ashbyhq OR smartrecruiters OR workday OR myworkday) newer_than:15m"
GMAIL_SEARCH = "https://mail.google.com/mail/u/0/#search/"
SCHOOL_MAIL = "https://outlook.office.com/mail/inbox"


def code_prompt_showing(page):
    """The application is asking for an emailed verification code."""
    try:
        if page.locator('input[autocomplete="one-time-code"]:visible').count():
            return True
        return bool(CODE_PROMPT.search(page.inner_text("body", timeout=3000)[:20000]))
    except Exception:
        return False


def mailbox_code(page):
    """Read the newest job-site message in an open mailbox. Returns the code or None."""
    try:
        page.locator('[role="option"], tr.zA').first.click(timeout=8000)
    except Exception:
        pass
    page.wait_for_timeout(2500)
    try:
        text = page.inner_text("body", timeout=5000)[:60000]
    except Exception:
        return None
    if not re.search(r"greenhouse|lever|ashby|smartrecruiters|workday", text, re.I):
        return None
    for m in re.finditer(r"(?:security|verification|confirmation) code", text, re.I):
        # the code is an 8-character token with at least one digit, shortly after the words "security code"
        for token in re.findall(r"\b[A-Za-z0-9]{4,10}\b", text[m.end():m.end() + 120]):
            if (re.search(r"\d", token) and re.search(r"[A-Za-z]", token)) or re.fullmatch(r"\d{4,8}", token):
                return token
    return None


def open_mailbox(page, name, url, login_re, ready_sel, log, until):
    """Open a mailbox fully and get it signed in. Returns True when its inbox is showing.

    Clicks "Sign in" on the landing page and waits at the login page. You sign in yourself in the
    HomeGrok window; HomeGrok never types a password or passes a two-step check.
    """
    page.goto(url, wait_until="domcontentloaded", timeout=60000)
    while time.time() < until:
        if re.search(login_re, page.url):
            log(f"Application filler: sign in to {name} in the HomeGrok window; it continues once you're in")
            page.wait_for_timeout(4000)
            return False
        try:
            if page.locator(ready_sel).count():
                return True
        except Exception:
            pass
        sign_in = page.get_by_role("link", name=re.compile(r"^\s*sign in\s*$", re.I)).or_(
            page.get_by_role("button", name=re.compile(r"^\s*sign in\s*$", re.I))).first
        try:
            if sign_in.count():
                sign_in.click(timeout=5000)   # opens the login page; the login itself stays with you
                page.wait_for_timeout(3000)
                continue
        except Exception:
            pass
        page.wait_for_timeout(2000)
    return False


MAIL_BOXES = (
    ("Gmail", GMAIL_SEARCH, r"accounts\.google\.com|ServiceLogin", "tr.zA"),
)


def emailed_code(ctx, log, timeout=600):
    """Find the code in the job site's email. Opens Gmail and your school mail fully in the HomeGrok window.

    Returns the code, or None when no code arrived within the time limit.
    """
    from urllib.parse import quote
    end = time.time() + timeout
    mail = ctx.new_page()
    mail.set_default_timeout(5000)
    try:
        while time.time() < end:
            for name, url, login_re, ready in MAIL_BOXES:
                if name == "Gmail":
                    url = GMAIL_SEARCH + quote(CODE_SENDERS)
                if not open_mailbox(mail, name, url, login_re, ready, log, min(end, time.time() + 60)):
                    continue
                found = mailbox_code(mail)
                if found:
                    return found
            mail.wait_for_timeout(15000)
        return None
    finally:
        mail.close()


def enter_emailed_code(ctx, page, log):
    """Find the code in your mail, type it into the boxes and press the button. Returns a note for you, or None."""
    got = emailed_code(ctx, log)
    if not got:
        log("Application filler: no code arrived in 10 minutes")
        return "The code didn't arrive (or your mail needs a sign-in in the HomeGrok window): enter it yourself"
    boxes = page.locator('input[aria-label*="ecurity" i]:visible, input[id*="security" i]:visible, '
                         'input[autocomplete="one-time-code"]:visible')
    if boxes.count() >= len(got):      # one box per character
        for i, ch in enumerate(got):
            boxes.nth(i).fill(ch)
    else:                              # a single box
        boxes.first.fill(got)
    page.get_by_role("button", name=re.compile(r"^\s*(verify|submit|continue|confirm)\s*$", re.I)).first.click()
    log("Application filler: entered the emailed code")
    return None


def run(ws, url, log=print):
    """Fill applications until you close the window. Claude answers what HomeGrok doesn't know;
    only important questions go to you; the dashboard tells you when one is ready to submit."""
    import threading
    from playwright.sync_api import sync_playwright
    from .brain import BrainUnavailable
    text, info = current_resume(ws), current_resume_info(ws)
    if not text or not info:
        raise SystemExit("Give HomeGrok your resume first (paste it or drop the file on the page).")
    p = profile_from_resume(text)
    folder = apply_dir(ws)
    queue, focus, live = folder / "queue.txt", folder / "focus", folder / "live.jpg"
    queue.write_text(url + "\n")
    # Mark this window as running before Chrome starts, so auto mode never opens a second one on top of it.
    (folder / "status.json").write_text(json.dumps({"running": True, "pid": os.getpid(), "updated": time.time(), "pages": []}))
    entries = []
    started, any_filled = time.time(), False

    def think(entry, questions, posting_text):
        try:
            entry["ai_results"] = ai_answer(ws, questions, posting_text)
        except BrainUnavailable as e:
            entry["ai_results"] = []
            log(f"Application filler: Claude couldn't answer ({e}); asking you instead")
        except Exception as e:
            entry["ai_results"] = []
            log(f"Application filler: answering failed ({e!r}); asking you instead")

    profile = str(ws.root / "browser" / "profile")
    subprocess.run(["pkill", "-f", f"user-data-dir={profile}"], check=False)   # a leftover window would block the launch
    time.sleep(2)
    with sync_playwright() as pw:
        ctx = pw.chromium.launch_persistent_context(profile, channel="chrome",
                                                    headless=False, viewport=None,
                                                    ignore_default_args=["--no-sandbox"], args=["--start-maximized"],
                                                    accept_downloads=False)   # nothing a page offers gets downloaded
        for extra in ctx.pages[1:]:   # Chrome may restore tabs from last time; start clean
            extra.close()
        first = ctx.pages[0] if ctx.pages else None
        if first:
            first.set_default_timeout(5000)
        last_fill = 0.0
        window_gone = False
        while True:
            # New applications open as tabs.
            if queue.exists() and queue.read_text().strip():
                for new_url in dict.fromkeys(queue.read_text().split()):
                    if any(e["url"] == new_url for e in entries):
                        continue
                    try:
                        page = first if first else ctx.new_page()
                    except Exception:   # you closed the filler window: finish quietly, don't log a crash
                        window_gone = True
                        break
                    first = None
                    # pop-up windows and browser dialogs from job pages are closed, never interacted with
                    page.set_default_timeout(5000)   # no single browser action may stall the filler for 30 s
                    page.on("popup", lambda popup: popup.close())
                    page.on("dialog", lambda dialog: dialog.dismiss())
                    try:
                        page.goto(application_url(new_url), wait_until="domcontentloaded", timeout=60000)
                        page.wait_for_timeout(3000)
                    except Exception:
                        pass
                    entries.append({"page": page, "url": new_url, "done": set(), "offers": {}, "filled": [],
                                    "last_progress": time.time(), "asked_at": {}, "auto_answered": [], "tries": {},
                                    "questions": [], "page_answers": {}, "important": {}, "suggested": {},
                                    "ai_asked": set(), "thread": None, "ai_results": None, "opened": time.time()})
                    log(f"Application filler: opened {new_url}")
                    # Say why a tab goes away, so a window that opens and closes is explained in the log.
                    page.on("close", lambda _p, u=new_url, t=time.time(): log(
                        f"Application filler: tab closed after {time.time() - t:.0f} s: {u}"))
                    page.on("crash", lambda _p, u=new_url: log(f"Application filler: the page crashed: {u}"))
                queue.write_text("")
            if window_gone:
                log("Application filler: the window was closed; finishing")
                break
            entries = [e for e in entries if not e["page"].is_closed()]
            if not entries and not (queue.exists() and queue.read_text().strip()):
                log("Application filler: every tab is closed; finishing")
                break   # nothing open and nothing queued: finished
            for e in entries:   # watch each page for glitching
                if e["page"].is_closed():
                    continue
                try:
                    y = e["page"].evaluate("window.scrollY")
                except Exception:
                    continue
                e.setdefault("scroll_samples", []).append((time.time(), y))
                e["scroll_samples"] = e["scroll_samples"][-40:]
                if is_glitching(e["scroll_samples"]):
                    title = e["page"].title() if not e["page"].is_closed() else ""
                    record_skip(ws, e["url"], title, "glitched (kept jumping up and down), so it was abandoned")
                    log(f"Application filler: {e['url']} kept glitching; closed it and opening a new application")
                    e["page"].close()
                    nxt = next_fresh_application(ws)
                    if nxt:
                        queue.write_text(nxt + "\n")
                    e["scroll_samples"] = []
            entries = [e for e in entries if not e["page"].is_closed()]
            if time.time() - last_fill > 4:
                a = answers(ws)
                for e in entries:
                    # Take in Claude's answers when they arrive.
                    if e["ai_results"] is not None:
                        for r in e["ai_results"]:
                            if r["ask_user"]:
                                e["important"][r["key"]] = r["answer"]
                            else:
                                e["page_answers"][r["key"]] = r["answer"]
                                if r["remember"]:
                                    save_answer(ws, r["key"], r["answer"])
                            e["suggested"][r["key"]] = r["answer"]
                        e["ai_results"], e["thread"] = None, None
                        e["last_progress"] = time.time()
                    # A page that filled nothing last time waits longer before the next pass (4 s up to 15 s),
                    # so a stuck form isn't rescanned and scrolled every few seconds.
                    wait = min(15.0, 4.0 + 2.0 * e.get("idle", 0))
                    if time.time() - e.get("last_pass", 0.0) < wait:
                        continue
                    e["last_pass"] = time.time()
                    if code_prompt_showing(e["page"]) and time.time() - e.get("code_at", 0.0) > 60:
                        # The site emailed a code: HomeGrok fetches it itself and enters it.
                        e["code_at"] = time.time()
                        try:
                            note = enter_emailed_code(ctx, e["page"], log)
                        except Exception as err:
                            note = "HomeGrok couldn't read the code: enter it yourself"
                            log(f"Application filler: code step failed ({err!r})")
                        if note:
                            e["important"]["code"] = note
                        continue
                    merged = {**a, "custom": {**e["page_answers"], **a.get("custom", {})}}
                    try:
                        yes_no = fill_yes_no(e["page"], p, merged, e.setdefault("yes_no_done", set()))
                        e["yes_no_open"] = open_yes_no(e["page"], p, merged, e["yes_no_done"])
                        if yes_no:
                            e["filled"] += [f"{yes_no} Yes/No answer(s)"]
                            e["last_progress"] = time.time()
                    except Exception as err:
                        log(f"Application filler: Yes/No step failed on {e['url']} ({err!r})")
                    try:
                        filled, questions, still_empty = fill(e["page"], p, merged, info["path"], e["done"],
                                                              e["offers"], e["tries"])
                    except Exception as err:   # never silent: a page that can't be filled says why, once
                        if not e.get("fill_error_logged"):
                            e["fill_error_logged"] = True
                            log(f"Application filler: couldn't fill {e['url']} ({err!r}); trying again")
                        continue
                    e["idle"] = 0 if filled else e.get("idle", 0) + 1
                    e["filled"] += filled
                    any_filled = any_filled or bool(filled)
                    if filled:
                        e["last_progress"] = time.time()
                    stuck_for = time.time() - e["last_progress"]
                    if not e["filled"] and e["thread"] is None and stuck_for > STUCK_SECONDS:
                        record_skip(ws, e["url"], e["page"].title() if not e["page"].is_closed() else "",
                                    "nothing HomeGrok could fill after a minute (it may need an account first)")
                        log(f"Application filler: moved on from {e['url']} (stuck for a minute)")
                        e["page"].close()
                        continue
                    try:
                        e["page"].keyboard.press("Escape")   # close any menu left open (Escape never submits)
                    except Exception:
                        pass
                    # only skip on a list that really loaded and really lacks the school (never on a timing miss)
                    missing = [q for q in questions if q.get("searched") and SCHOOL_Q.search(q["question"])
                               and len(q.get("options") or []) >= 3]
                    if missing:
                        school_names = merged.get("school") or ["YOUR_SCHOOL"]
                        school_label = school_names[0] if isinstance(school_names, list) else school_names
                        record_skip(ws, e["url"], e["page"].title() if not e["page"].is_closed() else "",
                                    f"{school_label} isn't in this employer's school list")
                        log(f"Application filler: skipped {e['url']} ({school_label} isn't in their school list)")
                        e["page"].close()
                        continue
                    # Questions nobody has answered yet go to Claude first (one batch at a time).
                    fresh = [q for q in questions if q["key"] not in e["ai_asked"]]
                    if fresh and e["thread"] is None:
                        try:
                            posting = e["page"].inner_text("body", timeout=5000)
                        except Exception:
                            posting = ""
                        e["ai_asked"].update(q["key"] for q in fresh)
                        e["thread"] = threading.Thread(target=think, args=(e, fresh, posting), daemon=True)
                        e["thread"].start()
                    # You only see what Claude flagged as important, or what still couldn't be filled.
                    thinking = e["thread"] is not None
                    shown = [dict(q, suggestion=e["suggested"].get(q["key"]), important=q["key"] in e["important"])
                             for q in questions if q["key"] in e["ai_asked"] and not thinking]
                    for q in shown:   # when each question was first put to you
                        e["asked_at"].setdefault(q["key"], time.time())
                    for q in shown:   # no answer from you in time: use the best answer from past data and keep going
                        waited = time.time() - e["asked_at"][q["key"]]
                        if SALARY_Q.search(q["question"]):   # pay is your decision: never a past-data guess
                            continue
                        if q.get("suggestion") and waited > WAIT_FOR_YOU_SECONDS and q["key"] not in e["page_answers"]:
                            e["page_answers"][q["key"]] = guard(q["question"], q["suggestion"])
                            e["auto_answered"].append(q["question"][:80])
                            log(f"Application filler: no answer from you in 5 minutes; used the best past answer for "
                                f"\"{q['question'][:60]}\"")
                    shown = [q for q in shown if q["key"] not in e["page_answers"]]
                    e["questions"] = sorted(shown, key=lambda q: not q["important"])
                    e["thinking"] = thinking
                    if not thinking:   # required but still empty after everything: ask you rather than stall
                        asked_keys = {q["key"] for q in e["questions"]}
                        for label in still_empty:
                            k = question_key(label)
                            if k not in asked_keys:
                                e["questions"].append({"key": k, "question": label, "options": [], "important": True,
                                                       "suggestion": None})
                    e["still_empty"] = still_empty
                    # Opt-in auto-submit: only a fully verified, guess-free application on a tested site,
                    # with no human check on screen, and only ever once.
                    if (a.get("auto_submit") and not e.get("submit_tried") and not thinking and not e["questions"]
                            and not still_empty
                            and SUBMITTABLE.search(e["url"]) and time.time() - e["opened"] > 20):
                        if human_check_showing(e["page"]):   # never attempted: leave it for you, visibly
                            e["submit_tried"] = True
                            record_submit(ws, e["url"], e["page"].title(), "needs_you")
                            e["important"]["submit"] = "A CAPTCHA is on this page: finish and submit it yourself"
                            log(f"Application filler: CAPTCHA on {e['url']}; left for you")
                            continue
                        e["submit_tried"] = True
                        title = e["page"].title()   # no human check on screen: submit
                        sent = snapshot_answers(e["page"])   # keep an exact record of what is sent
                        result, problems = submit_application(e["page"])
                        record_submit(ws, e["url"], title, result, sent)
                        if problems:
                            e["important"]["submit"] = "The form says: " + "; ".join(problems[:3])
                        log(f"Application filler: auto-submit {result} for {e['url']}")
                        if result == "submitted":
                            e["submitted"] = True
                            e["page"].wait_for_timeout(3000)
                            e["page"].close()
                            continue
                        e["important"]["submit"] = "Auto-submit stopped: please finish and submit this one yourself"
                    for q_text in e.get("yes_no_open", []):   # an open Yes/No question is yours to answer
                        if not any(x["question"] == q_text for x in e["questions"]):
                            e["questions"].append({"key": question_key(q_text), "question": q_text,
                                                   "options": ["Yes", "No"], "important": True, "suggestion": None})
                    e["ready"] = (not thinking and not e["questions"] and not still_empty   # answer only when observed complete
                                  and time.time() - e["opened"] > 10)
                    # waiting only on you for over a minute: auto mode moves on to the next application meanwhile
                    e["waiting_for_you"] = bool(e["questions"]) and time.time() - e["last_progress"] > STUCK_SECONDS
                    banner = ("HomeGrok is answering the remaining questions… " if thinking else
                              f"{len(e['questions'])} question(s) need you on the HomeGrok dashboard. " if e["questions"] else
                              "Ready: review everything, then click Submit yourself. ")
                    try:
                        e["page"].evaluate(BANNER, f"HomeGrok filled {len(e['filled'])} fields. {banner}")
                    except Exception:
                        pass
                last_fill = time.time()
            # Live picture for the dashboard; "take control" brings the right tab forward.
            if not entries:   # every tab closed while the queue was being read: nothing to show
                continue
            active = entries[-1]["page"]
            if focus.exists():
                wanted = focus.read_text().strip()
                focus.unlink()
                for e in entries:
                    if not wanted or e["url"] == wanted:
                        active = e["page"]
                try:
                    active.bring_to_front()
                except Exception:
                    pass
                subprocess.run(["osascript", "-e", 'tell application "Google Chrome" to activate'], check=False)
            try:
                active.screenshot(path=str(live), type="jpeg", quality=55, timeout=5000)
            except Exception:
                pass
            status = {"running": True, "pid": os.getpid(), "updated": time.time(),
                      "pages": [{"url": e["url"], "title": (e["page"].title() if not e["page"].is_closed() else ""),
                                 "filled": e["filled"][-40:], "questions": e["questions"],
                                 "thinking": e.get("thinking", False), "ready": e.get("ready", False),
                                 "waiting_for_you": e.get("waiting_for_you", False),
                                 "auto_answered": e.get("auto_answered", []),
                                 "still_empty": e.get("still_empty", [])} for e in entries]}
            (folder / "status.json").write_text(json.dumps(status))
            try:
                active.wait_for_timeout(1500)
            except Exception:
                time.sleep(1.5)
        ctx.close()
    # A window that closed within two minutes without filling anything is not retried by auto mode for 10 minutes,
    # so it can't keep opening and closing on its own (you can still open any job yourself).
    if not any_filled and time.time() - started < 120:
        (folder / "cooldown.json").write_text(json.dumps({"until": time.time() + 600}))
        log("Application filler: closed quickly without filling anything; auto mode pauses for 10 minutes")
    (folder / "status.json").write_text(json.dumps({"running": False, "updated": time.time()}))
    live.unlink(missing_ok=True)
