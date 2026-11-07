Tools and services used outside the repo. Scripts inside the repo are in `claude/tools/`.

- **Progress window** (artifact "WOLF Build Tracker", owned by the WOLF owner; the URL is in the
  owner's Claude artifact list): a small live page with a wolf pup that runs along a track as
  work progresses. To update it, build the JSON with `python3 claude/tools/progress.py ...`
  (`--steps "a|b|c"` starts a new plan), then write that file with the `ArtifactData` tool:
  `action: set`, `collection: progress`, `doc_id: build`, `file_path: claude/.progress.json`,
  plus `if_version` from the previous write. Percent 100 makes the pup sit and howl; no update
  for 20 minutes makes it nap.
- **Claude API**: WOLF uses `claude-opus-5-5` through the `anthropic` Python SDK. The API is
  reachable from the cloud sandbox, but there is no API key there, so live calls can't be tested
  (`wolf.config.check_key` can still verify that a bad key is rejected).
- **Playwright + Chromium**: pre-installed in the cloud sandbox; used by `tools/ui_smoke.py`.
- **Docker**: installed in the cloud sandbox but the daemon must be started (`dockerd &`). Builds
  need the sandbox proxy's certificate: use a throwaway copy of the Dockerfile with
  `COPY --from=ca ca-bundle.crt /tmp/ca.crt` + `ENV PIP_CERT=/tmp/ca.crt` and
  `docker build --build-context ca=/root/.ccr`. Never commit that copy.
- **GitHub**: through the GitHub MCP tools (no `gh` CLI except for search). Only push to the
  session's assigned branch.
- **Owner's connected accounts** (available in some sessions): use them only when the owner
  asks. This repo is public: never copy anything learned from them into it.
