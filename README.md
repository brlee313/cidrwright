# CIDRwright

Network-as-code CLI: describe a network in one YAML file, and CIDRwright
generates the subnet plan, firewall rules, WireGuard VPN configs, and
Terraform to build it.

**Status:** early development, built as a learning project with aider.

## Safety

- Secrets and Terraform state are excluded via `.gitignore` and `.aiderignore`.
- A gitleaks pre-commit hook blocks commits containing secrets
  (run `pre-commit install` after cloning).
- CI rescans the full git history on every pull request.
