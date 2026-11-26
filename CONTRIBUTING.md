# Contributing to CIDRwright

Thanks for helping. This page covers the legal sign-off, the workflow,
and the checks a pull request must pass.

## License and sign-off (DCO)

CIDRwright is licensed under the [Apache License 2.0](LICENSE). By
contributing, you agree that your contribution is licensed under the
same terms (Apache-2.0 section 5). There is no CLA.

Every commit must carry a `Signed-off-by` line certifying the
[Developer Certificate of Origin 1.1](https://developercertificate.org/):
that you wrote the change, or otherwise have the right to submit it under
this project's license.

```
Signed-off-by: Your Name <you@example.com>
```

Use your real name, and the same email as the commit author. `git commit -s`
adds the line for you. To sign off commits already on your branch:

```bash
git rebase --signoff main      # adds the line to every commit since main
git push --force-with-lease
```

AI coding tools that commit for you (for example aider) don't add the
line; run the rebase above before opening the pull request. You remain
responsible for what an AI tool wrote under your sign-off.

The DCO check on each pull request fails until every commit is signed
off.

## Workflow

1. Open or pick an issue, and say in it that you're working on it.
2. Branch from `main`: one issue, one branch, one pull request.
3. Put `Closes #N` in the pull request description.
4. Pull requests are squash-merged.

Large or design-level changes: discuss in the issue first. Decisions
that are hard to reverse are recorded as ADRs in [`docs/adr/`](docs/adr/).

## Checks

Set up once:

```bash
python -m venv .venv
.venv/bin/pip install -e ".[dev]"
pre-commit install            # gitleaks blocks commits containing secrets
```

Before pushing:

```bash
.venv/bin/pyright
.venv/bin/python -m pytest -q
```

CI runs the same type check and tests, scans the full git history for
secrets, and checks DCO sign-off. New tests follow
[`docs/testing-guidelines.md`](docs/testing-guidelines.md).

## Security issues

Don't open a public issue for a vulnerability. Use GitHub's private
vulnerability reporting (repository **Security** tab → **Report a
vulnerability**).
