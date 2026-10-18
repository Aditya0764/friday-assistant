# P7-09 security sweep

Date: 18 Oct 2026. Local HEAD at sweep time: `a37b1c5`. Run from the repo root with git and a POSIX shell.

**Hard rule followed:** no secret value was printed by any command or written here. Every command output was a file name, commit hash, count or pattern name. Hits are reported as pattern name, path, short hash, `[REDACTED]`. No email address appears in this report.

## Scope

- Commits scanned: 114, from `git rev-list --all --reflog` (all branches, remotes, tags, reflog). Refs: 10 (3 branch/remote refs, 7 tags).
- Tags: `g0-site-clearing`, `g1-foundation`, `g2-voice-loop`, `g3-frame`, `g4-rooms`, `g5-doors`, `g6-wiring`.
- Stashes: 0.
- Large batches were fed to `git grep` through `xargs -n 100` with a wrapper that treats exit 1 (no match) as fine and any exit above 1 as **SWEEP FAILED**. No batch failed.
- Positive controls: the scanner returned hits for `import` (110 commits, 13 files), for `C:/` or `C:\` (2 files) and for `git log -G import` (70 commits), so zero results elsewhere are not a broken scanner.

## Pushed state (owner-verified)

The repo is **public and pushed**. The owner checked GitHub in the browser: 83 commits, newest `209c78d`, 7 tags. Treat everything in this report as already visible to the world.

My local count ("30 commits ahead of `origin/main`") comes from the local `origin/main` tracking ref, which may be stale. It is not evidence of GitHub's real state. The local 114 commits include reflog-only commits, so it is not comparable with GitHub's 83 either. The remote URL was printed with credentials stripped; it carried none.

## Verdict table

| # | Check | Result | Verdict |
|---|---|---|---|
| 1 | Tracked files with secret-like or heavy names | only `.env.example` | PASS |
| 2 | `.env.example` values | 5 variables, all `empty` | PASS |
| 3 | `.gitignore` coverage | `.env`, `.secrets/`, `data/`, `models/`, `*.onnx`, `credentials.json`, `token.json`, `.cache` ignored. **`.env.local` is NOT ignored** | NEEDS-YOUR-JUDGMENT (gap, see below) |
| 4 | Secret-like file names in all history | `.env.example` only (3 commits, still present) | PASS |
| 5 | Secret patterns, all history | 0 hits for 8 key-format patterns | PASS |
| 6 | Generic key/secret assignment pattern | 2 hits, 1 file | NEEDS-YOUR-JUDGMENT |
| 7 | 32-hex strings | 0 with word boundaries (see note) | PASS, noisy by nature |
| 8 | Personal data in tracked files and history | 0 files for every category | PASS |
| 9 | Author/committer identity in history | personal email on 227 of 228 entries | NEEDS-YOUR-JUDGMENT, accepted by owner, no history rewrite |
| 10 | Large or binary files | none over 1 MB, ever; no recordings, DBs, model weights | PASS |
| 11 | `.claude/settings.json` | no secrets, no username | PASS (untracked, see below) |
| 12 | Unreachable objects | 4, counted, not read | NEEDS-YOUR-JUDGMENT (low) |

## Secret-pattern scans

Command shape (per pattern): `xargs -n 100 sh -c 'git grep -I -l -E -e "$PAT" "$@"; rc=$?; [ $rc -le 1 ] || exit 255' _ < commits.txt`, and `git log --all --reflog -G"$PAT" --name-only --format=%h` as cross-check. Placeholder exclusion was done with `git grep -P` and a negative lookahead applied to the matched value only (xxx, your_, example, dummy, fake, test, changeme).

| Pattern | Files | Commits | After value-level placeholder exclusion |
|---|---|---|---|
| Groq key (`gsk_` + 20 or more) | 0 | 0 | 0 |
| Google/Gemini key (`AIza` + 35) | 0 | 0 | 0 |
| Telegram bot token (8-10 digits, colon, 35 chars) | 0 | 0 | 0 |
| OpenAI-style (`sk-` + 20 or more) | 0 | 0 | 0 |
| GitHub `ghp_` | 0 | 0 | 0 |
| GitHub `github_pat_` | 0 | 0 | 0 |
| AWS access key id (`AKIA` + 16) | 0 | 0 | 0 |
| Private key header | 0 | 0 | 0 |
| Generic assignment (api key, secret, token, password, client_secret, refresh_token, quoted value of 12 or more) | 1 | 2 | 1 file, 2 commits (nothing excluded) |
| 32 hex chars, word-bounded | 0 | 0 | not applicable |

Note on the 32-hex scan: without word boundaries the same scan hits `training/train_wakeword.py` (55 commits) and three `evals/results/*.json` files (4 commits each). These are 32-hex runs inside longer hex strings, i.e. hashes, as expected. They were not opened or printed.

### Generic-assignment hits: NEEDS-YOUR-JUDGMENT

| Pattern | File | Short hashes | Value |
|---|---|---|---|
| generic assignment | `tests/test_telegram_bot.py` | `4d66a5f`, `5d25243` | [REDACTED] |

Shape checks by count only (no value printed): the value looks like digits, colon, letters/digits; length 12-20 characters; contains a fake-looking word. A real Telegram bot token has a 35-character suffix, and the Telegram token pattern did not match in any commit. Assessment: very likely a test fake. **The owner is checking this file by eye; verdict is theirs.**

## File-name and ignore checks

- `git ls-files` filtered for `.env`, credential, token, secret, `.pem`, `.key`, `.db`, `.sqlite*`, `.wav`, `.onnx`, `.pkl`, `.joblib`, `.session`, `.cache*`, `.spotify*`, `models/`, `data/`: one match, `.env.example`.
- Same filter over `git log --all --reflog --name-only --diff-filter=AMD`: one file, `.env.example`, 3 commits, still present. Nothing secret-named was ever added and later deleted.
- `.env.example` (variable names only): `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`, `GROQ_API_KEY`, `GEMINI_API_KEY`, `SPOTIFY_CLIENT_ID`. All `empty`.
- Tracked recordings, DBs, model weights, sessions (extension tally): 0.

### Gap: `.env.local` is not ignored

`git check-ignore -v .env.local` returned nothing: `.gitignore` line 222 ignores `.env` only. No `.env.local` was ever committed, so this is a hardening gap, not a leak. Same for the Claude deny rules, which cover `./.env` and `./.env.*.local` but not `./.env.local`. Suggested follow-up (not done here): add `.env.*` and `!.env.example` to `.gitignore`.

## Personal data

| Category | Tracked files at HEAD | History (pickaxe, `--all --reflog`) |
|---|---|---|
| Email addresses in file content | 0 | 0 files, 0 commits |
| `C:\Users\...` absolute paths | 0 | 0 files, 0 commits |
| Owner's name (two spellings) in content | 0 | 0 files, 0 commits |
| Owner's name in file names | 0 | not separately scanned (names covered by step 2: none) |
| Phone-number-like strings | 0 | not scanned in history |

### Commit identity: NEEDS-YOUR-JUDGMENT, accepted by owner

`git log --all --reflog --format='%ae%n%ce'` gave 228 author/committer entries: 227 are the owner's personal (non-noreply) address, 1 is GitHub's own noreply committer identity (a web-UI commit). **Decision by the owner: accepted, no history rewrite, no change to git config.** The address is therefore public in a public repo. Addresses are deliberately not listed here.

## Other state

- Remote: one, `origin`, HTTPS, no credentials in the URL.
- Working tree at sweep time: 21 untracked or modified entries (the `.claude/` folder and `evals/results/*` run files). None committed.
- Objects: `git count-objects -v`: 763 loose (897 KB), 4 in pack (1 pack, 3 KB), 0 garbage.
- Unreachable objects: `git fsck --unreachable --no-reflogs --no-progress | wc -l` = **4**. Counted only, contents not read (the command writes nothing to `.git`). They are not reachable from any ref, so they are not in the public repo, but their content was not checked. Running `git gc --prune=now` would remove them; not done.
- Files over 1 MB: none at HEAD and none in any blob in history (`git rev-list --objects --all --reflog` piped to `git cat-file --batch-check`).

## `.claude/`

- `.claude/` is **untracked and not ignored** (`git ls-files .claude` = 0; `git check-ignore` printed nothing). Contents: `settings.json` only; `settings.local.json` does not exist.
- A Python reader printed key names and rule strings only (each rule redacted: runs of 16 or more `[A-Za-z0-9_-]` replaced with `[LONG]`, then cut to 80 chars; no rule needed redaction).
- Top-level keys: `permissions` only. `env`, `mcpServers`, `hooks`: absent.
- `permissions.deny` (7): `Read(./.env)`, `Read(./.env.*.local)`, `Read(./.secrets/**)`, `Bash(git push:*)`, `Bash(git tag:*)`, `Bash(git add .:*)`, `Bash(git add -A:*)`. `allow`: 0. `ask`: 0.
- Grep counts against the file: username or `C:\Users` = 0; all eight key-format patterns, 32-hex and the generic assignment = 0.
- Verdict: safe to commit as it stands (no secrets, no username, no machine paths). Not committed by this task. If it is added later, keep `settings.local.json` ignored.

## What this sweep cannot prove

- A pattern search is not proof of absence. It matches known formats only. Keys with custom prefixes, split strings, base64 or otherwise encoded values, and low-entropy passwords are missed. The generic pattern needs a quoted value, so unquoted `NAME=value` lines are missed.
- `git grep -I` skips binary files; anything inside archives, audio, databases or model files was not read.
- Placeholder exclusion was by value text; a real key that happens to contain a word like "test" would be hidden in the "after" column (the "before" column is shown for that reason).
- Unreachable objects were only counted. Objects already pruned, other clones, forks and the GitHub-side caches or pull-request refs were not examined. GitHub's actual state was checked only by the owner in a browser (commit count, newest hash, tags), not by this sweep.
- Phone-number-like strings were scanned at HEAD only, not in history.
- It says nothing about leaks outside git: shell history, logs, chat transcripts, backups, the untracked `evals/results/*` files, or `.env` itself (never opened, by rule).
- A zero count means "no match for these patterns", not "no secret".

## Second opinion: recommended

A dedicated scanner is worth one run because it uses entropy rules and many vendor formats. Not run in this task.

- Install: `winget install Gitleaks.Gitleaks` (or `scoop install gitleaks`).
- Run from the repo root, report outside the repo: `gitleaks git --redact --no-banner --report-format json --report-path <folder-outside-repo>\gl.json .` (older versions: `gitleaks detect --redact`). `--redact` keeps values out of the output; delete the report afterwards.
- Optional: `winget install trufflesecurity.trufflehog`, then `trufflehog git file://. --no-verification --no-update`. `--no-verification` avoids live-testing any key over the network.
- Review hits by file and commit only.

## Addendum (18 Oct 2026, ~02:40 IST): gitleaks and owner verdicts

- gitleaks 8.30.1 (installed with `winget install Gitleaks.Gitleaks`).
- Command: `gitleaks git --redact --no-banner -v --report-format json --report-path <temp folder> .`
- Output: "115 commits scanned, about 2.13 MB in 1.24 s, no leaks found".
- gitleaks counted 115 commits; the sweep above counted 114. The cause of the difference of one was not checked.
- The temp report file was deleted afterwards.
- The two generic-pattern hits in `tests/test_telegram_bot.py`: the owner checked the file by eye. The values are made-up test strings (an owner id, a stranger id and a short fake secret). Verdict: test fake. The values are not written here.
