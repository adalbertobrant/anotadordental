# Security and data policy — DentaNote

> 🇧🇷 [Versão em português](SECURITY.md).

## Rule number one: never with real patient data

**Do not open issues, pull requests, discussions, logs, screenshots or
attachments containing real patient data (PHI).** In healthcare this is
sensitive data protected by LGPD (Brazil's data protection law); here it is
also a project rule: the repository may only contain 100% synthetic data
(`data/synthetic/`, "Sample Patient 01", fictional scenarios).

If you accidentally expose real data:

1. Don't try to "overwrite it" with a new commit — report it immediately.
2. Open an issue **without repeating the data** or contact the maintainers
   directly (repository **Security** tab → *Report a vulnerability* on GitHub).
3. Maintenance will *rewrite* history if needed and ask you to run
   `git fetch && git reset --hard` (coordination happens in the private
   channel).

## Scope

DentaNote is a **local** program: no server, no account, no telemetry, no
external API calls at runtime. The only network communications are:

| Communication | When | External networks? |
| --- | --- | --- |
| `http://localhost:11434` (Ollama) | extraction | no — always localhost |
| Model downloads (Ollama/HuggingFace) | first install | yes, once; everything offline after |
| Anything else | never | — |

Vulnerabilities that break these principles (e.g. an HTTP request leaving the
machine with clinical text) are considered **critical**.

## How to report

- Use the repository's GitHub security advisory form (or, if unavailable, an
  issue with the word `[security]` and **no** real data).
- Include: version (`dentanote version`), operating system, reproduction steps
  with **synthetic data**, and the expected behavior.

## Supported versions

| Version | Support |
| --- | --- |
| 0.1.x | active |

Fixes are published on the `main` branch; tagged releases when there is a
change relevant to the data policy.
