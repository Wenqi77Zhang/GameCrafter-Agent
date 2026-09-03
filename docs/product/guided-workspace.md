# Guided production workspace

## Purpose

M16 changes GameCrafter from a collection of workspaces into a guided production experience for a
first-time user. It does not remove evidence, audit, GDD, or operations capabilities. It changes
their information hierarchy so the user always sees what they are doing, why it matters, and what
observable result completes the step.

## Interaction contract

1. The project overview remains the source of truth for the current stage.
2. On first load, the web app automatically opens the server-recommended task. If the server later
   advances the stage while the user is still on the previous task, the matching next workspace is
   opened automatically.
3. The five-step production route is always visible on desktop and horizontally scrollable on a
   narrow mobile screen. Completed steps remain reversible navigation, not mutable history.
4. Every task workspace starts with three plain-language facts: the task name, why it is needed,
   and the completion signal.
5. GDD, Runs, Account, and Refresh are secondary tools. They never compete visually with the five
   production stages.
6. Starting a durable job no longer redirects the user into Runs. An inline background banner says
   that processing is continuing and offers technical details only on demand.
7. When the NTE project has evidence but no game entity, Knowledge offers a one-click creation path
   using the current project name and the prepared `NTE: Neverness to Everness` alias. The generic
   auditable creation form remains available for other games or corrections.
8. Simplified Chinese remains the default product language. English is a reversible preference.

## Beginner acceptance route

1. Start the production preview and open `http://127.0.0.1:8080`.
2. Confirm that **Your production route** says which numbered step is current and that the right
   task matches it without a manual tab switch.
3. If the current task is Knowledge and no entity exists, click **Use current project: NTE** (the
   Chinese interface displays the localized equivalent). Confirm that the entity selector appears
   and extraction capability is checked.
4. Start extraction. Confirm that the page stays in Knowledge and shows background progress; open
   Runs only if technical detail is desired.
5. Complete automatic pre-review and the remaining human decisions. Publish the immutable snapshot.
   Confirm that the route advances to Marketing.
6. Approve one TikTok topic, create and evaluate the English script, then complete final approval
   and export. Confirm that all five route cards are complete.
7. Switch to English and back to Simplified Chinese. Resize to a narrow phone view and confirm the
   current route card, current-task button, and task content remain usable without page-level
   horizontal overflow.

## Safety and provenance boundary

The route is presentation logic over the existing deterministic overview. It cannot approve facts,
topics, or exports; bypass evidence requirements; rewrite Agent prompts; or hide terminal failures.
Professional diagnostics remain available through Runs and the expandable route metrics.
