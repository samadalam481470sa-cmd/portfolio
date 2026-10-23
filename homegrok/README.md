HomeGrok fully runs an AI trainer on your own GPU — you can teach it anything.

<small><em>(Uses Apple Metal or NVIDIA CUDA when available; falls back to CPU otherwise.)</em></small>

# HomeGrok

Your own AI platform, running on your machine. Claude is the brain (through your Claude subscription),
your files are its knowledge, and it keeps working in the background around the clock.

Open **http://127.0.0.1:8000**. The page updates live; there is nothing to refresh, start or pause.

## What it does

- **Chat** with Claude, which already knows what is in your files and what you have told it. Replies
  stream in as they are written, and the conversation is saved, so it is there whenever you open the page.
- **Standing tasks.** Ask for ongoing work in plain words ("find internships that fit me and write a
  tailored resume and cover letter for each, never stop") and HomeGrok keeps doing it: one step about
  every 10 minutes, 24/7, whenever the Mac is online. Claude searches the web itself and the results are
  saved as Markdown and Word files in `~/HomeGrok Results/<task>/`, shown under **Working on**.
  Say "stop the internship task" to stop one.
- **Memory.** Claude reads new and changed files in your folders, plus what you tell it in chat, and
  keeps a memory note about you (school, skills, experience, preferences). Tell it your major, GPA,
  contact details and experience once, and every resume after that uses them.
- **Its own model.** A small transformer (the second diagram) trains on your files locally. `./hg learn`,
  `train`, `evolve`, and `pipeline` use a GPU when Apple Metal or CUDA is available, and otherwise the CPU.
  It improves itself with a genetic algorithm and answers when Claude can't, for example when your usage
  limit is reached. It rests on battery and once it stops improving, until your files change.

HomeGrok **prepares** applications; it never submits them, sends messages or signs in anywhere. You
review each resume, fill in any `[fill in]` placeholders, and apply.

## How it fits the diagrams

| Diagram box | Where it lives |
|---|---|
| Users and apps | `homegrok/web/index.html` (web app), `./hg chat` (terminal) |
| API gateway | `homegrok/server.py`: localhost only, API key, rate limiting, live event stream |
| Orchestrator | `homegrok/orchestrator.py`: Claude or local model, file retrieval, starting/stopping tasks |
| Model server | `orchestrator.ModelServer` (local model, hot-swapped) and `homegrok/brain.py` (Claude) |
| Vector database / Your documents | `homegrok/vectordb.py`, `homegrok/memory.py` |
| Collect data / Clean data | `homegrok/collect.py` (text, Word, PowerPoint, PDF; skips secrets and logs), `homegrok/clean.py` (redacts keys, passwords, SSNs, card numbers) |
| Train the model / Test quality / Model storage | `homegrok/model.py`, `train.py`, `evolve.py`, `storage.py` |
| Monitoring, logging, billing, security | `server.Monitor`, `workspace/logs/`, Claude usage bars on the page |
| Running by itself | `homegrok/learner.py` (autopilot) + `homegrok/tasks.py` (standing tasks), kept alive by launchd |

## Claude usage

Every Claude call goes through the Claude Code CLI signed in to your account, so it uses your
subscription, not an API bill. The page shows your 5-hour and weekly usage. Background work (tasks and
memory) stops at **90%** of either limit so the rest stays available for you, and resumes on its own when
the limit resets. Your own chat messages can use all of it.

```sh
./hg claude                                   # settings and current usage
./hg claude --background-model sonnet         # make background work use less of your limit
./hg claude --background-calls-per-day 40     # hard daily cap on background calls
./hg claude --disable                         # local model only
```

Anthropic's terms don't allow using Claude's outputs to train other AI models, so the local model
learns only from your own files. HomeGrok never reads `~/HomeGrok Results` or its own workspace back in.

## Commands

```sh
./service.sh install     # (re)start the web server and autopilot in the background (also at login)
./service.sh status      # are they running?
./service.sh logs        # follow what they are doing
./service.sh uninstall   # stop everything

./hg tasks                       # list tasks;  --stop "internship"  or  --start TITLE GOAL
./hg memory                      # what HomeGrok knows about you
./hg setup --folders ~/Documents ~/Desktop   # which folders it may learn from
./hg chat                        # chat in the terminal
```

## Put your own details here

The contact fields committed in this copy are placeholders, not a real person. Before you use the
application filler, edit `homegrok/apply.py` and replace the values in `DEFAULT_ANSWERS`:

- `street` — `YOUR_STREET_ADDRESS`
- `address_city`, `current_city`, and `state` — `YOUR_CITY` / `YOUR_STATE`
- `zip` — `YOUR_ZIP`
- `phone` — `YOUR_PHONE`
- `email` — `you@example.com`
- `school`, `degree`, and `gpa` — `YOUR_SCHOOL`, `YOUR_DEGREE`, `YOUR_GPA`
- `gender`, `race`, and the other form answers — `YOUR_GENDER`, `YOUR_RACE`, `YOUR_ANSWER`

Paste your resume on the HomeGrok page as well. A phone number or email on the resume is used when
it is present. Do not commit a real street address, phone number, email address, birth date, or password.

## Privacy

Everything runs and is stored on this Mac in `./workspace` and `~/HomeGrok Results`. With Claude turned
on, the text Claude needs (your message, matching excerpts from your files, the memory note) is sent to
Anthropic under your Claude account, the same as pasting it into claude.ai. Delete `./workspace` to erase
everything HomeGrok learned.
