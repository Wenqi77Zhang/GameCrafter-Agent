import { useEffect, useState } from "react";

type Health = {
  status: "ok";
  service: "gamecrafter-api";
  version: string;
  environment: string;
  phase: "M0";
  timestamp: string;
};

type HealthState =
  | { kind: "loading" }
  | { kind: "ready"; data: Health; checkedAt: Date }
  | { kind: "error"; message: string; checkedAt: Date };

const healthTimeoutMs = 5_000;

const milestones = [
  {
    id: "M0",
    title: "Engineering foundation",
    detail: "Repository, API, web shell, tests, CI, and architecture decisions.",
    state: "active",
  },
  {
    id: "M1",
    title: "Game Knowledge Hub",
    detail: "Traceable sources, claims, conflicts, human review, and snapshots.",
    state: "next",
  },
  {
    id: "M2–M4",
    title: "Marketing workflow",
    detail: "Real trends, fit analysis, script generation, evaluation, and approval.",
    state: "planned",
  },
] as const;

function parseHealth(payload: unknown): Health {
  if (
    typeof payload !== "object" ||
    payload === null ||
    !("status" in payload) ||
    payload.status !== "ok" ||
    !("service" in payload) ||
    payload.service !== "gamecrafter-api" ||
    !("version" in payload) ||
    typeof payload.version !== "string" ||
    payload.version.length === 0 ||
    !("environment" in payload) ||
    typeof payload.environment !== "string" ||
    payload.environment.length === 0 ||
    !("phase" in payload) ||
    payload.phase !== "M0" ||
    !("timestamp" in payload) ||
    typeof payload.timestamp !== "string"
  ) {
    throw new Error("API returned an invalid health payload");
  }

  return payload as Health;
}

async function fetchHealth(signal: AbortSignal): Promise<Health> {
  const response = await fetch("/api/health", { signal });
  if (!response.ok) {
    throw new Error(`API returned ${response.status}`);
  }
  return parseHealth(await response.json());
}

function formatCheckedAt(value: Date): string {
  return new Intl.DateTimeFormat("en-GB", {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  }).format(value);
}

export function App() {
  const [health, setHealth] = useState<HealthState>({ kind: "loading" });
  const [healthAttempt, setHealthAttempt] = useState(0);

  useEffect(() => {
    const controller = new AbortController();
    let disposed = false;
    const timeout = window.setTimeout(() => controller.abort(), healthTimeoutMs);

    setHealth({ kind: "loading" });

    fetchHealth(controller.signal)
      .then((data) => {
        if (!disposed) {
          setHealth({ kind: "ready", data, checkedAt: new Date() });
        }
      })
      .catch((error: unknown) => {
        if (disposed) {
          return;
        }
        const message = controller.signal.aborted
          ? "API health check timed out after 5 seconds"
          : error instanceof Error
            ? error.message
            : "Unknown API error";
        setHealth({ kind: "error", message, checkedAt: new Date() });
      })
      .finally(() => window.clearTimeout(timeout));

    return () => {
      disposed = true;
      window.clearTimeout(timeout);
      controller.abort();
    };
  }, [healthAttempt]);

  const retryHealth = () => setHealthAttempt((attempt) => attempt + 1);

  return (
    <main className="app-shell">
      <header className="topbar">
        <a className="brand" href="/" aria-label="GameCrafter home">
          <span className="brand-mark" aria-hidden="true">
            G
          </span>
          <span>GameCrafter</span>
        </a>
        <span className="phase-badge">M0 · Foundation</span>
      </header>

      <section className="hero">
        <div className="eyebrow">Evidence-aware game intelligence</div>
        <h1>
          Turn scattered game knowledge into
          <span> marketing decisions you can defend.</span>
        </h1>
        <p>
          GameCrafter is evolving into a traceable workspace for independent developers:
          verified game facts, real market signals, constrained AI workflows, and explicit human
          approval.
        </p>
        <div className="hero-actions">
          <a className="primary-action" href="#roadmap">
            View build roadmap
          </a>
          <a
            className="secondary-action"
            href="https://github.com/Wenqi77Zhang/GameCrafter-Agent"
          >
            GitHub repository
          </a>
        </div>
      </section>

      <section className="status-grid" aria-label="System status">
        <article className="status-card status-card--wide" aria-live="polite">
          <div className="card-label">Local system health</div>
          {health.kind === "loading" && <p className="health loading">Checking API…</p>}
          {health.kind === "error" && (
            <div>
              <p className="health error">API unavailable</p>
              <p className="status-detail">{health.message}</p>
              <div className="health-actions">
                <span>Checked {formatCheckedAt(health.checkedAt)}</span>
                <button className="retry-action" type="button" onClick={retryHealth}>
                  Check again
                </button>
              </div>
            </div>
          )}
          {health.kind === "ready" && (
            <div>
              <p className="health healthy">
                <span className="pulse" aria-hidden="true" />
                API connected
              </p>
              <p className="status-detail">
                {health.data.service} · v{health.data.version} · {health.data.environment}
              </p>
              <div className="health-actions">
                <span>Checked {formatCheckedAt(health.checkedAt)}</span>
                <button className="retry-action" type="button" onClick={retryHealth}>
                  Check again
                </button>
              </div>
            </div>
          )}
        </article>

        <article className="status-card">
          <div className="card-label">Validation case</div>
          <strong>NTE: Neverness to Everness</strong>
          <p className="status-detail">TikTok · English-speaking markets</p>
        </article>

        <article className="status-card">
          <div className="card-label">Privacy mode</div>
          <strong>Local single-user</strong>
          <p className="status-detail">No account system in the first release</p>
        </article>
      </section>

      <section className="roadmap" id="roadmap">
        <div className="section-heading">
          <div>
            <div className="eyebrow">Build sequence</div>
            <h2>One verified vertical slice at a time.</h2>
          </div>
          <p>
            The architecture is extensible, but features are only presented as complete after code,
            tests, and user-visible evidence exist.
          </p>
        </div>

        <div className="milestone-list">
          {milestones.map((milestone) => (
            <article className={`milestone milestone--${milestone.state}`} key={milestone.id}>
              <span className="milestone-id">{milestone.id}</span>
              <div>
                <h3>{milestone.title}</h3>
                <p>{milestone.detail}</p>
              </div>
              <span className="milestone-state">{milestone.state}</span>
            </article>
          ))}
        </div>
      </section>

      <footer>
        <span>GameCrafter v2</span>
        <span>Facts · Evidence · Human control</span>
      </footer>
    </main>
  );
}
