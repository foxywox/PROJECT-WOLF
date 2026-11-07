Tools and services used outside the repo. Scripts inside the repo are in `claude/tools/`.

- **Build progress**: `python3 claude/tools/progress.py PERCENT ACTIVE_STEP "now" ["note"]`
  (`--steps "a|b|c" --title T` starts a new build) writes `hub/progress.json`, which WOLF's
  Project tab shows with the wolf pup. Commit it with your work. Percent 100 makes the pup sit
  and howl; no update for 20 minutes makes it nap.
- **Live progress window** (artifact "WOLF Build Tracker", owned by the WOLF owner; URL in the
  owner's Claude artifact list): mirrors the same JSON while you work, for the owner to watch
  without running WOLF. Write `hub/progress.json` with the `ArtifactData` tool: `action: set`,
  `collection: progress`, `doc_id: build`, plus `if_version` from the previous write.
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
