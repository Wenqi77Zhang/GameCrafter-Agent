# System architecture and workflow DAGs

GameCrafter v2 uses a modular monolith with explicit domain and adapter boundaries. The design prioritizes traceability, local development, testability, and a path to future multi-tenant operation without prematurely creating distributed services.

## System context

```mermaid
flowchart LR
    USER["Independent game developer"]
    WEB["GameCrafter web workspace"]
    API["GameCrafter API"]
    MODEL["Configured model provider"]
    OFFICIAL["Official game sources"]
    TREND["Public trend sources"]
    FILES["User-owned local documents"]
    DB[("Local PostgreSQL and object storage")]

    USER --> WEB --> API
    API --> OFFICIAL
    API --> TREND
    API --> FILES
    API --> MODEL
    API --> DB
    API -. "progress and evidence" .-> WEB
```

External pages, trend responses, model responses, and uploaded documents cross a trust boundary. They are treated as untrusted data, validated, versioned, and prevented from directly controlling tools.

## Knowledge-ingestion state graph

```mermaid
stateDiagram-v2
    [*] --> SourceSubmitted
    SourceSubmitted --> PolicyCheck
    PolicyCheck --> Rejected: disallowed scheme, host, or type
    PolicyCheck --> SnapshotCaptured: accepted
    SnapshotCaptured --> ContentParsed
    ContentParsed --> ClaimsExtracted
    ClaimsExtracted --> EvidenceLinked
    EvidenceLinked --> ConflictCheck
    ConflictCheck --> HumanReview: new, uncertain, or conflicting claims
    HumanReview --> ClaimsExtracted: edit and re-extract
    HumanReview --> Rejected: reject
    HumanReview --> SnapshotPublished: approve
    SnapshotPublished --> [*]
    Rejected --> [*]
```

Key rules:

- raw snapshots are immutable;
- processed documents record parser and schema versions;
- claims preserve source, time, region, version, and evidence spans;
- uncertain or conflicting claims do not become approved facts automatically;
- marketing runs reference a frozen knowledge snapshot, not mutable live records.

## Marketing workflow state graph

```mermaid
stateDiagram-v2
    [*] --> TaskDefined
    TaskDefined --> TrendCollection
    TrendCollection --> CandidateProcessing
    CandidateProcessing --> FitAnalysis
    FitAnalysis --> TopicApproval
    TopicApproval --> TrendCollection: reject or change filters
    TopicApproval --> BriefCreated: approve
    BriefCreated --> ScriptGenerated
    ScriptGenerated --> ScriptEvaluated
    ScriptEvaluated --> ScriptRevised: below threshold and revision budget remains
    ScriptRevised --> ScriptEvaluated
    ScriptEvaluated --> FinalReview: accepted or revision budget exhausted
    FinalReview --> ScriptGenerated: request larger revision
    FinalReview --> Exported: approve
    Exported --> [*]
```

The revision loop has a fixed budget. A model score never replaces topic or final-output approval.

## Component relationships

```mermaid
flowchart TB
    subgraph Delivery["Delivery"]
        WEB["apps/web"]
        FASTAPI["apps/api and gamecrafter.api"]
    end

    subgraph Application["Application layer"]
        COMMANDS["Commands"]
        QUERIES["Queries"]
        SERVICES["Orchestration services"]
    end

    subgraph Domain["Domain layer"]
        PROJECTS["Projects"]
        KNOWLEDGE["Knowledge"]
        TRENDS["Trends"]
        CAMPAIGNS["Campaigns"]
        SCRIPTS["Scripts"]
        RUNS["Runs"]
    end

    subgraph Runtime["Constrained agent runtime"]
        GRAPHS["LangGraph graphs"]
        NODES["Specialist nodes"]
        SKILLS["Skills and prompts"]
        GATES["Human gates"]
    end

    subgraph Infrastructure["Infrastructure"]
        DATABASE["Database repositories"]
        INGESTION["Source connectors and parsers"]
        SEARCH["Hybrid search"]
        MODELS["ModelGateway"]
        TOOLS["ToolProvider"]
        STORAGE["ObjectStorage"]
        OBS["RunTracer"]
    end

    WEB --> FASTAPI
    FASTAPI --> Application
    Application --> Domain
    Application --> Runtime
    Runtime --> Infrastructure
    Domain --> Infrastructure
```

Dependency direction is enforced by convention and tests: domain modules must not import FastAPI, model SDKs, or source-specific clients.

## Planned specialist nodes

- Knowledge Curator: structures evidence-backed game claims.
- Trend Analyst: clusters trends and explains task fit.
- Script Writer: produces structured script versions from approved inputs.
- Quality Critic: evaluates explicit dimensions and proposes bounded revisions.

These are workflow roles, not simulated employees. Parallelism is used for independent source fetches, candidate analyses, and evaluation dimensions; human decisions remain sequential gates.

## Storage direction

The target persistence layer is PostgreSQL with full-text search and pgvector. Raw pages, documents, and large responses use an object-storage interface. M0 does not yet implement persistence; this diagram records the intended boundary for later milestones.

## Observability

Each future run will record:

- run and trace identifiers;
- node state and checkpoint;
- source, model, prompt, skill, and rule versions;
- tool calls, latency, retries, token usage, and estimated cost;
- human approvals, edits, rejections, and reasons;
- script version lineage and export state.
