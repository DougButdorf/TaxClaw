# Releasing TaxClaw

Maintainer checklist for TaxClaw 1.0.0. The release is gated on the accuracy
benchmark (PR #5). Do none of this until the gate passes.

All commands run from a clone of `DougButdorf/TaxClaw` with `gh` and `clawhub`
logged in as the maintainer. `REL_PR` is the release pull request number.

```bash
REPO=DougButdorf/TaxClaw
REL_PR=<release PR number>
VERSION=1.0.0
```

## 0. Confirm the gate

```bash
gh pr view 5 -R "$REPO" --json state,mergedAt,title    # must be MERGED, results accepted on #3
gh pr checks "$REL_PR" -R "$REPO"                      # all green
```

Then, on the release branch:

- Replace `## 1.0.0 - TBD` in `CHANGELOG.md` with the release date (`## 1.0.0 - YYYY-MM-DD`).
- Update "Known limitations" and `src/model_catalog.yaml` (`as_of`, local picks) with the benchmark results if they change the recommendations.
- Commit, push, and wait for CI to pass again.

## 1. Merge, tag, GitHub release

```bash
gh pr ready "$REL_PR" -R "$REPO"
gh pr merge "$REL_PR" -R "$REPO" --merge

git fetch origin
git checkout main && git pull --ff-only origin main
grep -q "^__version__ = \"$VERSION\"" src/__init__.py      # sanity check
git tag -a "v$VERSION" -m "TaxClaw $VERSION" origin/main
git push origin "v$VERSION"

# Release notes = the 1.0.0 section of CHANGELOG.md
awk '/^## 1\.0\.0 /{f=1; next} /^## /{f=0} f' CHANGELOG.md > /tmp/taxclaw-$VERSION-notes.md
gh release create "v$VERSION" -R "$REPO" --verify-tag \
  --title "TaxClaw $VERSION" --notes-file /tmp/taxclaw-$VERSION-notes.md
```

## 2. Publish to ClawHub

Publish from a clean export of the tag (no `venv/`, no `.git`). The folder name
doesn't set the slug here because `--slug` is passed, but name it `taxclaw`
anyway so the export matches an install.

```bash
SHA=$(git rev-parse "v$VERSION^{commit}")
PUB=$(mktemp -d)/taxclaw && mkdir -p "$PUB"
git archive "v$VERSION" | tar -x -C "$PUB"

clawhub whoami                                    # must be dougbutdorf

# Dry run first: expect status "would-publish", version 1.0.0, latestVersion 0.1.1
clawhub publish "$PUB" --dry-run --json \
  --slug taxclaw --name TaxClaw --owner dougbutdorf --version "$VERSION" \
  --source-repo "$REPO" --source-commit "$SHA" --source-ref "refs/tags/v$VERSION"

clawhub publish "$PUB" \
  --slug taxclaw --name TaxClaw --owner dougbutdorf --version "$VERSION" \
  --tags latest \
  --changelog "1.0.0: Agent Skills portability, three model tiers (local Ollama, configured cloud, Cloudflare Clairic), local MCP server, Form 8949 CSV and TXF exports, web UI hardening (loopback Host/Origin on every request, CSP, no CDN scripts), full cloud-mode disclosure. See CHANGELOG.md." \
  --source-repo "$REPO" --source-commit "$SHA" --source-ref "refs/tags/v$VERSION"
```

Check the listing and the security scan (the scan can take a few minutes):

```bash
clawhub inspect taxclaw --version "$VERSION" --files          # bin/, src/, templates/, scripts/, setup.sh, start.sh, config.example.yaml present
clawhub inspect taxclaw --version "$VERSION" --json | python3 -c 'import json,sys; s=json.load(sys.stdin)["version"]["security"]; print(s["status"], s.get("hasWarnings"))'
```

Also read https://clawhub.ai/dougbutdorf/skills/taxclaw/security-audit and
record any remaining findings on #3.

## 3. Verify the install in a scratch agent workspace

Use a throwaway HOME and a clean environment so nothing touches a real agent
workspace, OpenClaw profile, or TaxClaw config.

```bash
SCRATCH=$(mktemp -d)
oc() { env -i PATH="$PATH" HOME="$SCRATCH" TMPDIR="$SCRATCH" openclaw "$@"; }

oc skills install @dougbutdorf/taxclaw --version "$VERSION"
oc skills info taxclaw                    # expect "taxclaw ✓ Ready", homepage github.com/DougButdorf/TaxClaw
oc skills info taxclaw --json             # note "baseDir"

BASE=$(oc skills info taxclaw --json | python3 -c 'import json,sys; print(json.load(sys.stdin)["baseDir"])')
grep -q "version: \"$VERSION\"" "$BASE/SKILL.md"
ls "$BASE/bin/taxclaw" "$BASE/config.example.yaml" "$BASE/setup.sh" "$BASE/start.sh"
env -i PATH="$PATH" HOME="$SCRATCH" bash "$BASE/setup.sh"
env -i PATH="$PATH" HOME="$SCRATCH" "$BASE/bin/taxclaw" --version   # taxclaw 1.0.0
env -i PATH="$PATH" HOME="$SCRATCH" bash "$BASE/scripts/smoke.sh"

rm -rf "$SCRATCH"
```

## 4. Close the loop

```bash
gh issue list -R "$REPO" --state open
```

Reply on every open issue that 1.0.0 touches, then close the tracking issue:

```bash
gh issue comment 3 -R "$REPO" --body-file /tmp/taxclaw-3-release-comment.md   # links: release, ClawHub version, scan status
gh issue close 3 -R "$REPO" --reason completed
```

Website and announcement updates (taxclaw.net) happen only after steps 1–3 pass.
