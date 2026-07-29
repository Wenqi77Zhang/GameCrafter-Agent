# M1-C C2.1 zero-cost ModelGateway

Status: C2.1 implemented and locally verified on 2026-07-30.

## Implemented

- a framework-independent `ModelGateway` application port;
- immutable extraction requests fingerprinted over the exact source version, text, offset, subject,
  locale, region, prompt version, and schema version;
- safe disabled, replay-miss, invalid-output, and redacted provider failure types;
- a disabled gateway that fails closed without inspecting configuration;
- an offline replay gateway that accepts only an exact fingerprint fixture;
- an OpenAI Responses request adapter with injected client ownership;
- strict structured claim JSON Schema with undeclared properties forbidden;
- exact evidence quote and range verification before a candidate can leave an adapter;
- conversion from chunk-relative evidence offsets to source-version absolute offsets;
- value-kind validation through the existing controlled claim domain contract;
- provider, model, response ID, fingerprint, and nonnegative token-usage result metadata;
- architecture tests preventing domain or application code from importing a model SDK.

## Strict zero-cost boundary

C2.1 does not install the OpenAI SDK, read an API key, construct an HTTP client, or perform a live
model call. The OpenAI adapter is tested with a local object that records the request and returns a
simulated response. The runnable application remains configured as `disabled`.

The future live request shape is implemented now so vendor-specific details stay outside the
application layer. It uses:

- the Responses API;
- strict JSON Schema structured output;
- `store: false`;
- explicit model and reasoning effort;
- bounded output tokens;
- normalized text and minimum semantic metadata only.

The adapter deliberately excludes source-version IDs, URLs, filesystem paths, raw HTML, images,
secrets, and logs from the model input.

## Evidence validation

Structured output is not trusted merely because it matches JSON Schema. For every evidence span:

1. offsets must be nonnegative and stay inside the supplied chunk;
2. the returned quote must exactly equal the text slice at those offsets;
3. range length must equal quote length;
4. the claim value must match its declared controlled value kind;
5. the predicate must belong to the controlled vocabulary.

Failure rejects the candidate rather than attempting fuzzy repair.

## Deliberately not implemented

- no deterministic chunker or extraction orchestration;
- no durable `knowledge.extract` job;
- no model-invocation database record;
- no preflight or extraction API;
- no NTE source fixture or replay loader;
- no extraction frontend;
- no real OpenAI SDK/client/API call;
- no conflict processing, review action, or snapshot publication.

These are C2.2 and later steps.
