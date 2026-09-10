# Guided production workspace

## M19 additions

Marketing now separates actual model suggestions from rule-fit references. Topic and final-script
decisions require an explicit preset selection, collapse after submission, and reopen only with
"Change decision". Creation has an inline durable progress panel, real evidence beside each beat,
an ordinary storyboard editor, version differences, and a visible re-review requirement after edits.
Existing workflow setup is collapsed once a script exists. See the Chinese
[acceptance walkthrough](real-creative-workflow.md#如何验收) for the current route.

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
5. Complete automatic pre-review. In **Human review tasks**, confirm that project and current-entity
   remaining counts are visible. Select **Review the next pending candidate**; the exact evidence and
   required decision must open without searching through batches. Choose a decision and preset reason.
   Free text appears only after choosing **Other reason**.
6. Submit the decision. Confirm that the candidate moves into collapsed **Completed (no action
   needed)**, receives a submitted check mark, and the next pending candidate opens automatically.
   If a blocker belongs to another game entity, its action switches the entity and opens that Claim.
7. Publish the immutable snapshot after all review and conflict blockers are closed. Confirm that the
   route advances to Marketing.
8. Approve one TikTok topic, create and evaluate the English script, then complete final approval
   and export. Confirm that all five route cards are complete.
9. Switch to English and back to Simplified Chinese. Resize to a narrow phone view and confirm the
   current route card, current-task button, and task content remain usable without page-level
   horizontal overflow.

## Safety and provenance boundary

The route is presentation logic over the existing deterministic overview. It cannot approve facts,
topics, or exports; bypass evidence requirements; rewrite Agent prompts; or hide terminal failures.
Professional diagnostics remain available through Runs and the expandable route metrics.
