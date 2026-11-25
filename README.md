# CIDRwright

Network-as-code CLI: describe a network in one YAML file, and CIDRwright
generates the subnet plan, firewall rules, WireGuard VPN configs, and
Terraform to build it.

**Status:** early development, built as a learning project with aider.

How design decisions are made and reviewed:
[`docs/process/design-review.md`](docs/process/design-review.md); the
decisions themselves are in [`docs/adr/`](docs/adr/README.md).

## Safety

- Secrets and Terraform state are excluded via `.gitignore` and `.aiderignore`.
- A gitleaks pre-commit hook blocks commits containing secrets
  (run `pre-commit install` after cloning).
- CI rescans the full git history on every pull request.

## Contributing

Contributions are welcome. See [CONTRIBUTING.md](CONTRIBUTING.md): every
commit needs a DCO sign-off (`git commit -s`).

## License

[Apache License 2.0](LICENSE). See [NOTICE](NOTICE). Versions released
before 2026-11-26 were MIT-licensed.
