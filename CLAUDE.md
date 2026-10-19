# This repo

A vendored copy of [sergebulaev/linkedin-skills](https://github.com/sergebulaev/linkedin-skills)
(MIT, upstream commit `261240ac5c4da8b4465cbd364d14ce52ffed12ce`), set up so its 12 LinkedIn
skills load automatically when Claude Code opens this repo.

- Skills live in `skills/`; `.claude/skills/<name>` are relative symlinks to them, which is
  how Claude Code discovers them. Run Python helpers (`from lib import ...`) from the repo root.
- Optional credentials go in `.env` (copy `.env.example`; `.env` is gitignored). With none set,
  every skill still works in manual mode: drafts only, you paste post text and publish by hand.
  - `APIFY_TOKEN`: read posts/comments/engagers from a URL
  - `PUBLORA_API_KEY` + `LINKEDIN_PLATFORM_ID`: publish after approval
  - `PIXFARO_TOKEN`: generate images
- Check the setup: `python3 scripts/check_config.py --offline` and
  `python3 -m unittest discover -s tests`.
- Upstream's maintainer conventions are in `docs/upstream-CLAUDE.md`. They apply to
  contributions sent upstream, not to commits in this repo.
- To update: re-clone upstream and copy it over (excluding `.git`), keeping this file.
