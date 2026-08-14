# M1-C C3b explainable conflict workspace

C3b exposes the deterministic C3a service in the existing Knowledge workspace without adding a
second decision engine or implying that an AI-selected value is approved truth.

## Delivered interaction

- Conflict reconciliation runs only after an explicit human click.
- The workspace reloads project- and entity-scoped groups after reconciliation and after a
  successful extraction run.
- `conflicting` and `possibly_coexisting` use distinct visual and bilingual labels.
- Every card shows localized status, distinct-value and candidate counts, policy version, and the
  server-provided deterministic basis.
- Selecting a member selects its immutable Claim and reveals the existing exact quote, offsets,
  source, immutable version, and capture time in the evidence inspector.
- Desktop and narrow mobile layouts preserve the evidence path without horizontal overflow.

## Safety boundary

The interface cannot select a winner, edit or approve a Claim, resolve or dismiss a group, or
publish a knowledge snapshot. Confidence remains visible as model provenance but is never used to
classify or resolve a conflict. These human decisions belong to C4 and C5.

## Verification

- Frontend unit coverage exercises conflict reads, reconciliation, relation rendering, policy
  disclosure, and member-to-evidence navigation.
- Type checking, production build, and browser smoke checks cover Simplified Chinese desktop and
  English mobile layouts.
- The C3a backend unit, SQLite, API/OpenAPI, and PostgreSQL acceptance suites remain the service
  evidence behind this presentation layer.
- Regression hardening makes application-generated timestamps process-monotonic, preventing
  coarse Windows clock resolution from letting random UUID order scramble same-process audit
  events that share one wall-clock reading.
