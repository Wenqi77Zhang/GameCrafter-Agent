# Readable marketing strategy brief

Status: implemented in M17.

## Product outcome

The Marketing workspace must answer four questions before the user enters script creation:

1. What marketing direction should the team take?
2. What exact English TikTok topic should the video use?
3. Why is this direction supported by the current trend and approved game knowledge?
4. What should happen across the 30-second video?

Campaign Strategist 1.1 exposes those answers as `marketing-strategy-brief-v1`. It is a deterministic
read model over an immutable marketing task, a ranked trend candidate, its source observation, and an
approved knowledge snapshot. It does not invoke a paid model and does not create new game facts.

## Visible contract

The primary result card contains:

- one localized direction category;
- one recommended English video topic and one core communication message;
- audience, platform, markets, language, duration, and fit score;
- four timed beats: hook, proof, payoff, and interaction;
- up to three exact approved proof facts from the frozen snapshot;
- trend source, region, observation lineage, disclosed risks, and rule version;
- draft or approved state, the human approval reason, and up to two alternatives;
- a direct transition to topic review or Script Writer, according to approval state.

Technical score dimensions and the append-only decision ledger remain available below the conclusion
for audit. They no longer substitute for the conclusion itself.

## Beginner acceptance

1. Complete or reuse a published knowledge snapshot.
2. In Marketing, create a task, add or sync at least one trend, and run zero-cost fit.
3. Confirm that “营销策略结论” appears above setup controls and can be understood without opening
   score details.
4. Confirm that the result visibly names a direction, a recommended English topic, a 30-second plan,
   usable facts, and a trend source.
5. Before approval, the primary action reads “审核这个方向” and moves to the topic gate.
6. Approve the topic with a reason. The result changes to “已确认 · 可直接生成脚本”.
7. Select “按此方向生成脚本” and confirm that the Creation workspace opens.
8. Switch to English and repeat the visual review. At desktop and mobile widths, no horizontal page
   overflow or browser-console error is acceptable.

