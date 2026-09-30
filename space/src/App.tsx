import "./App.css"
import { publicEvidence } from "./data/publicEvidence.generated"

const pct = (ratio: number, digits = 1) => `${(ratio * 100).toFixed(digits)}%`

function EvidenceRail() {
  const { fixedReference, challenger, deterministicFaults, decision } =
    publicEvidence.metrics

  const items = [
    {
      value: `${fixedReference.passes} / ${fixedReference.cases}`,
      label: "development tasks correct",
    },
    {
      value: `${deterministicFaults.passes} / ${deterministicFaults.cases}`,
      label: "controlled failure tests passed",
    },
    {
      value: `${challenger.passes} / ${challenger.cases}`,
      label: `${challenger.model} challenger · baseline ${challenger.baselinePasses} / ${challenger.cases}`,
    },
    {
      value: String(decision.lockedCasesAccessed),
      label: "final unseen cases consumed",
    },
  ]

  return (
    <dl className="metric-rail" aria-label="Core experiment evidence">
      {items.map((item) => (
        <div className="metric" key={item.label}>
          <dt>{item.label}</dt>
          <dd>{item.value}</dd>
        </div>
      ))}
    </dl>
  )
}

function EfficiencyComparison() {
  const { adaptation } = publicEvidence.metrics

  const rows = [
    {
      label: "Best-case theoretical saving",
      value: adaptation.theoreticalReduction,
      note: "Development diagnostic only. This assumes advance knowledge of which attempts eventually fail.",
      kind: "theoretical",
    },
    {
      label: "Required project target",
      value: adaptation.requiredTargetReduction,
      note: "Predeclared threshold for a worthwhile final efficiency improvement.",
      kind: "target",
    },
    {
      label: "Best practical rule found",
      value: adaptation.bestPracticalReduction,
      note: `Development diagnostic only. It caused ${adaptation.observedPassLosses} previously successful tasks to fail.`,
      kind: "practical",
    },
  ] as const

  return (
    <figure className="comparison" aria-labelledby="comparison-title">
      <figcaption id="comparison-title" className="eyebrow">
        THE CENTRAL RESULT
      </figcaption>

      <div className="comparison-heading">
        <h2>Potential existed. A safe practical rule did not.</h2>
        <p>
          The theoretical figure is not an achieved saving. Runtime-visible
          rules could not capture the apparent headroom without either saving
          almost nothing or reducing reliability.
        </p>
      </div>

      <div className="bar-list">
        {rows.map((row) => (
          <div className="bar-row" key={row.label}>
            <div className="bar-copy">
              <span className="bar-label">{row.label}</span>
              <strong>{pct(row.value)}</strong>
            </div>
            <div className="bar-track" aria-hidden="true">
              <span
                className={`bar-fill ${row.kind}`}
                style={{ width: `${Math.max(row.value * 100, 2.5)}%` }}
              />
            </div>
            <p>{row.note}</p>
          </div>
        ))}
      </div>
    </figure>
  )
}

function DecisionStrip() {
  const { decision } = publicEvidence.metrics

  return (
    <div className="integrity-strip">
      <span>
        Formal verdict <strong>{decision.finalVerdict}</strong>
      </span>
      <span>
        Adaptive layer <strong>{decision.adaptiveRuntimePromotion}</strong>
      </span>
      <span>
        Locked comparison <strong>{decision.lockedPairedEvaluation}</strong>
      </span>
      <span>
        Locked cases consumed <strong>{decision.lockedCasesAccessed}</strong>
      </span>
    </div>
  )
}

function App() {
  const { adaptation } = publicEvidence.metrics

  return (
    <>
      <a className="skip-link" href="#main-content">
        Skip to content
      </a>

      <header className="site-header">
        <a className="brand" href="#main-content">
          HarbourDesk
        </a>
        <nav aria-label="Case study">
          <a href="#result">Result</a>
          <a href="#decision">Decision</a>
          <span>Evidence-first case study</span>
        </nav>
      </header>

      <main id="main-content">
        <section className="hero evidence-hero">
          <div className="hero-primary">
            <p className="eyebrow">HARBOURDESK · AI RELIABILITY STUDY</p>
            <h1>
              <span className="evidence-number">{pct(adaptation.theoreticalReduction)}</span>
              theoretical headroom.
            </h1>
          </div>

          <div
            className="evidence-versus"
            aria-label="Required target versus practical result"
          >
            <div>
              <span className="result-label">Required project target</span>
              <strong>{pct(adaptation.requiredTargetReduction, 0)}</strong>
            </div>
            <div>
              <span className="result-label">Best practical rule</span>
              <strong>{pct(adaptation.bestPracticalReduction)}</strong>
              <small>
                + {adaptation.observedPassLosses} reliability regressions
              </small>
            </div>
          </div>

          <p className="lede">
            The apparent opportunity was visible with hindsight. The bounded
            rules available while the AI was actually working could not capture
            it safely enough to justify the added complexity.
          </p>

          <div className="hero-decision">
            <span>Engineering decision</span>
            <strong>Don&apos;t ship the adaptive approach.</strong>
          </div>
        </section>

        <section id="result" className="result-section">
          <EfficiencyComparison />
          <EvidenceRail />
        </section>

        <section id="decision" className="decision-section">
          <p className="eyebrow">ENGINEERING DECISION</p>
          <div className="decision-grid">
            <h2>Reject the adaptive layer. Preserve the final unseen set.</h2>
            <div>
              <p>
                No adaptive candidate met the development admission threshold.
                The correct action was to stop rather than repeatedly test weak
                approaches against the final unseen benchmark.
              </p>
              <DecisionStrip />
            </div>
          </div>
        </section>

        <section className="evidence-boundary" aria-labelledby="evidence-boundary-title">
          <p className="eyebrow">PUBLIC EVIDENCE BOUNDARY</p>
          <div className="evidence-boundary-grid">
            <div>
              <h2 id="evidence-boundary-title">Every displayed result is bound to frozen public evidence.</h2>
              <p>
                Outcome metrics come from the R11 public results artifact. The
                20% threshold comes from the predeclared R4 efficiency gate.
                Private evaluator material and arbitrary experiment directories
                are not frontend inputs.
              </p>
            </div>
            <dl>
              <div>
                <dt>R11 release</dt>
                <dd>{publicEvidence.source.r11RunId}</dd>
              </div>
              <div>
                <dt>Results SHA256</dt>
                <dd>{publicEvidence.source.resultsSha256}</dd>
              </div>
              <div>
                <dt>Formal verdict</dt>
                <dd>{publicEvidence.metrics.decision.finalVerdict}</dd>
              </div>
            </dl>
          </div>
        </section>
      </main>

      <footer>
        <p>
          HarbourDesk reliability study · evidence-first publication direction ·
          frozen experiment
        </p>
      </footer>
    </>
  )
}

export default App
