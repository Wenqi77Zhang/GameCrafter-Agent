# M1-C C2.4b Knowledge workspace

## Outcome

C2.4b turns the C2.4a delivery API into one usable local Knowledge workflow. A user can choose or
create a game identity, correct its human-facing label without rewriting lineage, select an
immutable evidence version, inspect the exact zero-cost capability state, start extraction, follow
persisted progress, and inspect candidate claims beside their exact evidence.

The interface does not implement conflict resolution, human claim review, snapshot publication,
or live model execution. Those controls remain absent until their backend invariants exist.

## Interaction contract

- Simplified Chinese is the default; English uses the existing remembered language preference.
- The latest available source version is selected by default, while every historical version stays
  selectable for exact replay.
- A disabled or mismatched replay state displays the server reason and disables extraction. No paid
  or approximate fallback exists.
- Starting extraction remains on the Knowledge page. Four stages are derived from durable run and
  audit state, and the complete event history is one action away in Runs.
- If no source version exists, the empty state links directly to Sources. If no game identity
  exists, a small creation form is available in place.
- Claims are grouped by controlled predicate and labelled `candidate_unreviewed`. Selecting one
  shows the persisted quote, source URL/title, version, locale, region, capture time, and text
  offsets returned by the server.
- Corrections append a reasoned entity revision. Archival requires confirmation and never deletes
  old claims or evidence.

## Privacy and trust boundary

The browser receives normalized read models only. It does not receive a fixture path, local object
path, prompt body, source body, response body, credential, or private raw asset. Evidence quotes are
rendered exactly as returned by the API so JavaScript UTF-16 indexing cannot corrupt Python Unicode
offsets. Candidate status is never presented as human approval.

## Verification

- nine React tests cover existing Sources/Runs behavior plus exact-replay start, evidence lineage,
  generic entity creation/correction, and the missing-source shortcut;
- TypeScript checking and production bundling cover the split shared client and Knowledge module;
- a real headless Chromium smoke check covers Simplified Chinese desktop, English mobile at 390 px,
  exact evidence visibility, capability visibility, console errors, and horizontal overflow;
- the existing Python and PostgreSQL suites continue to guard the C2.4a command and persistence
  boundary.
