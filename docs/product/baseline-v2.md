# GameCrafter v2 product baseline

Status: confirmed on 2026-07-27.

GameCrafter is a long-term personal product, portfolio project, and potential commercial product. It is no longer a four-day team assignment.

## Product

GameCrafter is an evidence-aware game knowledge and marketing workspace for independent game developers.

The first complete slice:

1. imports public game evidence;
2. builds a human-reviewed Game Knowledge Hub;
3. retrieves real trend signals;
4. explains game, platform, market, audience, and goal fit;
5. requires human topic approval;
6. creates a structured marketing brief and TikTok script;
7. evaluates and revises low-score sections;
8. preserves versions and requires final human approval.

## First validation case

- Game: NTE: Neverness to Everness (《异环》)
- Developer: Hotta Studio, part of Perfect World
- Target platform: TikTok
- Markets: United States, United Kingdom, Canada, Australia, and New Zealand
- Audience: potential new players in English-speaking markets
- Output: a 25–35 second English vertical-video marketing script

## First-release boundaries

The first release is local and single-user. It does not include accounts, multi-tenancy, team collaboration, billing, a complete GDD Studio, video rendering, or unauthorized TikTok scraping.

Public sources must not be described as an internal GDD. For existing games, the Knowledge Hub creates a sourced Public Game Intelligence Profile. User-owned internal documents may be supported locally, but online private uploads require later authentication and isolation work.

## M1 official-source policy

- The NTE validation profile supports the global official site's English, Simplified Chinese, and
  Japanese sections plus the separate mainland-China official site.
- Discovery is bounded and human-triggered. It offers quick discovery, filtered historical
  discovery, and direct official-URL import; there is no silent scheduled crawling in the first
  release.
- Candidates require human selection before full capture. Original HTML, normalized text,
  provenance metadata, and bounded relevant images form an immutable local evidence bundle.
- HTTP is the primary capture mechanism. A site adapter may permit one controlled Playwright
  fallback for pages that require JavaScript.
- Official-language variants remain separate evidence and may be linked as one content family;
  they are never silently merged into one fact.
- The local filesystem implements the first `ObjectStorage` adapter. Raw evidence and private local
  data remain gitignored; later storage providers stay behind the same application port.

## M1 knowledge-review policy

- A model-produced claim is never an approved fact. Every new claim requires an exact evidence
  span and an explicit human decision.
- M1-C uses controlled entity and predicate vocabularies. Unsupported claims remain unclassified
  rather than allowing a model to silently expand the ontology.
- Human decisions are approve, approve with edit, reject, or defer. The original model value and
  every review decision remain immutable and attributable.
- Conflict detection is deterministic over subject, predicate, normalized value, region, locale,
  effective time, and game version. A model confidence score cannot resolve a conflict.
- Approved facts affect later workflows only after the user explicitly publishes an immutable
  knowledge snapshot. Open conflicts block publication.
- The first model adapter uses the OpenAI Responses API behind a provider-neutral `ModelGateway`
  and stays disabled without local configuration. Only normalized public source text and minimum
  provenance metadata may leave the machine in M1-C; raw HTML, images, secrets, object paths,
  private documents, and unrelated logs are excluded.
- Model calls use minimized logging and `store: false`, while product copy must still disclose that
  provider abuse-monitoring retention can apply unless the organization has eligible data-retention
  controls.

## Architecture policy

- modular monolith before microservices;
- deterministic state graphs around constrained specialist nodes;
- local ReAct only where research tools are needed;
- evaluator–optimizer loops with explicit limits;
- human approval before topic selection and final export;
- versioned skills, prompts, rules, sources, and outputs;
- provider adapters instead of vendor coupling;
- no MCP service unless cross-application reuse or independent permissions justify it.

## Change control

Changes to the product positioning, first complete slice, default validation case, data boundary, agent pattern, main technology stack, or milestone order require explicit approval from the project owner and synchronized documentation updates.
