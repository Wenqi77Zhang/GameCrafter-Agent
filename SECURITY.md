# Security policy

## Supported release

GameCrafter `1.0.x` is the supported local-product line. Security fixes are applied to the latest
release; historical milestone branches are evidence, not maintained deployments.

## Reporting a vulnerability

Do not disclose exploitable details, private source material, credentials or personal data in a
public issue. Use the repository's **Security** tab and select **Report a vulnerability** to open a
private GitHub security advisory with:

- the affected version and local configuration;
- reproducible steps using synthetic data;
- expected and observed behavior;
- the likely impact and any known workaround.

If private vulnerability reporting is unavailable, contact the repository owner through their
GitHub profile without attaching secrets or user data. A public issue may describe a non-sensitive
symptom only after the maintainer confirms that doing so is safe.

## Product boundary

GameCrafter is a local-first, zero-paid-API release. It is not hardened for anonymous Internet
exposure. Do not publish port 8080, the API, PostgreSQL, Ollama or object storage to an untrusted
network. Optional accounts provide local/team isolation; they do not replace TLS, managed secrets,
network controls, monitoring and incident response required by a public SaaS.

Never commit `.env`, cookies, tokens, private GDDs, captured source contents, exports, backups or
the `data/` directory. Reports must use synthetic evidence and redact request IDs only when their
surrounding logs could reveal private operational context.

## Maintainer response

The maintainer will acknowledge a private report, reproduce it, assess affected data and versions,
prepare a tested fix, and coordinate disclosure. No fixed response-time promise is made for this
independent project; high-impact data exposure or code execution reports take priority.
