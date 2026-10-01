import { useState } from "react"
import {
  ArrowUpRight,
  Check,
  Database,
  FileCheck,
  GitBranch,
  Lock,
  ShieldCheck,
} from "lucide-react"
import {
  Bar,
  BarChart,
  LabelList,
  ResponsiveContainer,
  XAxis,
  YAxis,
} from "recharts"

import "./App.css"
import {
  Tabs,
  TabsContent,
  TabsList,
  TabsTrigger,
} from "@/components/ui/tabs"
import { publicationEvidence as evidence } from "./data/publicationEvidence"

const pct = (ratio: number, digits = 1) => `${(ratio * 100).toFixed(digits)}%`

type FailureFamilyId = "F1" | "F2" | "F3" | "F4" | "F5" | "F6"

const failureFamilies: Array<{
  id: FailureFamilyId
  short: string
  title: string
  definition: string
  question: string
}> = [
  {
    id: "F1",
    short: "Access mismatch",
    title: "Access does not match the plan",
    definition:
      "The customer’s current plan and actual account access do not agree.",
    question:
      "Can the AI determine the correct access state before making a change?",
  },
  {
    id: "F3",
    short: "Stale rules",
    title: "Old rules conflict with current rules",
    definition:
      "Older or expired rules look relevant, but a newer valid rule gives a different answer.",
    question: "Can the AI identify the rule that is actually current?",
  },
  {
    id: "F2",
    short: "Unclear request",
    title: "The request is unclear",
    definition:
      "The customer has not clearly identified the account, feature, or action.",
    question: "Will the AI ask for clarification instead of guessing?",
  },
  {
    id: "F6",
    short: "Unknown outcome",
    title: "The action may already have happened",
    definition:
      "A previous operation may have committed even though its response was lost or interrupted.",
    question:
      "Will the AI verify what already happened before retrying?",
  },
  {
    id: "F4",
    short: "Conflicting records",
    title: "The records disagree",
    definition:
      "Different system records contradict one another about ownership, state, access, or provenance.",
    question:
      "Will the AI recognise conflicting evidence instead of blindly trusting one record?",
  },
  {
    id: "F5",
    short: "Permission boundary",
    title: "The requester may not have permission",
    definition:
      "The action may be valid, but the person requesting it may not be authorised.",
    question: "Can the AI verify authority before changing account state?",
  },
]

const underTheHood = {
  architecture: {
    title: "Typed boundaries before model freedom",
    description:
      "The runtime keeps model output behind typed contracts and deterministic state-changing controls.",
    bullets: [
      "Pydantic boundaries and explicit tool schemas",
      "Deterministic write realization and state transitions",
      "Evidence provenance attached to observable execution",
    ],
    flow: ["Model proposal", "Schema validation", "Tool policy", "State transition"],
  },
  evaluation: {
    title: "Evaluation was staged to preserve independent evidence",
    description:
      "Development evidence was used to investigate. Validation and the final unseen set had separate roles and access rules.",
    bullets: [
      "Template-separated benchmark with six failure families",
      "Independent outcome scoring",
      "Development, validation, and final unseen partitions",
    ],
    flow: ["Development", "Candidate admission", "Validation", "Final unseen"],
  },
  safety: {
    title: "Reliability controls did not depend on the model being right",
    description:
      "State-changing actions were guarded by deterministic checks so model mistakes did not automatically become writes.",
    bullets: [
      "Authorization and approval checks",
      "Compare-and-swap revisions and idempotency",
      "Unknown-outcome recovery and controlled fault tests",
    ],
    flow: ["Request", "Authority", "Revision check", "Idempotent write"],
  },
  evidence: {
    title: "Claims terminate in inspectable artifacts",
    description:
      "The closeout preserved traces, usage accounting, hashes, and a deliberately smaller sanitized public surface.",
    bullets: [
      "Trace and usage evidence captured during evaluation",
      "Hash-bound R10 closeout and R11 public release",
      "Private evaluation material excluded from the public UI",
    ],
    flow: ["Execution", "Receipts", "R10 closeout", "R11 public release"],
  },
} as const

const links = {
  repo: "https://github.com/kablewithak/adaptive-agent-runtime",
  methodology:
    "https://github.com/kablewithak/adaptive-agent-runtime/blob/main/docs/checkpoints/2026-09-28-r4-benchmark-and-final-acceptance-contract.md",
  results:
    "https://github.com/kablewithak/adaptive-agent-runtime/blob/main/space/evidence/results.json",
}

function SectionIntro({
  eyebrow,
  title,
  children,
}: {
  eyebrow: string
  title: string
  children?: React.ReactNode
}) {
  return (
    <div className="section-intro">
      <p className="eyebrow">{eyebrow}</p>
      <div className="section-intro-grid">
        <h2>{title}</h2>
        {children ? <div className="section-intro-copy">{children}</div> : null}
      </div>
    </div>
  )
}

function EvidenceRail() {
  const { benchmark } = evidence.publication
  const { fixedReference, deterministicFaults, decision } = evidence.metrics

  const items = [
    {
      value: String(benchmark.totalCases),
      label: "evaluation cases designed",
    },
    {
      value: `${fixedReference.passes} / ${fixedReference.cases}`,
      label: "development tasks correct",
    },
    {
      value: `${deterministicFaults.passes} / ${deterministicFaults.cases}`,
      label: "controlled failure tests passed",
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
          <dd>{item.value}</dd>
          <dt>{item.label}</dt>
        </div>
      ))}
    </dl>
  )
}

function FailureFamilySection() {
  const [selected, setSelected] = useState<FailureFamilyId>("F1")
  const { denominator, results } = evidence.publication.failureFamilies
  const selectedFamily =
    failureFamilies.find((family) => family.id === selected) ?? failureFamilies[0]

  const chartData = failureFamilies.map((family) => ({
    id: family.id,
    name: family.short,
    passes: results[family.id],
    label: `${results[family.id]} / ${denominator}`,
  }))

  return (
    <section id="failure-families" className="case-section">
      <SectionIntro
        eyebrow="04 · FAILURE FAMILIES"
        title="The aggregate score hid a very uneven reliability profile."
      >
        <p>
          Six deliberately different failure families tested whether the system
          could resolve ambiguity, stale policy, contradictory evidence,
          permission boundaries, and uncertain prior actions.
        </p>
      </SectionIntro>

      <div className="family-layout">
        <figure className="family-chart" aria-labelledby="family-chart-title">
          <figcaption id="family-chart-title">
            Development tasks completed correctly
          </figcaption>
          <p className="chart-subtitle">
            Direct result out of {denominator} cases in each family.
          </p>
          <div className="chart-frame" aria-hidden="true">
            <ResponsiveContainer width="100%" height={360}>
              <BarChart
                data={chartData}
                layout="vertical"
                margin={{ top: 8, right: 48, bottom: 8, left: 8 }}
              >
                <XAxis type="number" domain={[0, denominator]} hide />
                <YAxis
                  type="category"
                  dataKey="name"
                  width={124}
                  axisLine={false}
                  tickLine={false}
                  tick={{ fontSize: 12, fill: "var(--muted)" }}
                />
                <Bar
                  dataKey="passes"
                  fill="var(--accent)"
                  radius={[0, 3, 3, 0]}
                  isAnimationActive={false}
                >
                  <LabelList
                    dataKey="label"
                    position="right"
                    fill="var(--ink)"
                    fontSize={12}
                    fontWeight={700}
                  />
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </div>
          <div className="sr-only">
            {chartData.map((row) => (
              <span key={row.id}>
                {row.id} {row.name}: {row.label}.{" "}
              </span>
            ))}
          </div>
        </figure>

        <div className="family-explorer">
          <div className="family-buttons" aria-label="Failure family details">
            {failureFamilies.map((family) => {
              const isActive = selected === family.id
              return (
                <button
                  type="button"
                  className="family-button"
                  data-active={isActive}
                  aria-pressed={isActive}
                  onClick={() => setSelected(family.id)}
                  key={family.id}
                >
                  <span>{family.id}</span>
                  <strong>{family.short}</strong>
                  <small>
                    {results[family.id]} / {denominator}
                  </small>
                </button>
              )
            })}
          </div>

          <div className="family-detail" aria-live="polite">
            <p className="technical-label">{selectedFamily.id}</p>
            <h3>{selectedFamily.title}</h3>
            <p>{selectedFamily.definition}</p>
            <div>
              <span>What was being tested?</span>
              <strong>{selectedFamily.question}</strong>
            </div>
          </div>
        </div>
      </div>
    </section>
  )
}

function OptimizationResult() {
  const { adaptation } = evidence.metrics

  const rows = [
    {
      label: "Best-case theoretical saving",
      value: adaptation.theoreticalReduction,
      detail:
        "A hindsight-only upper bound that knows which trajectories eventually fail.",
      kind: "theoretical",
    },
    {
      label: "Required project target",
      value: adaptation.requiredTargetReduction,
      detail: "The predeclared threshold for worthwhile final efficiency.",
      kind: "target",
    },
    {
      label: "Best practical rule found",
      value: adaptation.bestPracticalReduction,
      detail: `Development diagnostic only — and it caused ${adaptation.observedPassLosses} previously successful tasks to fail.`,
      kind: "practical",
    },
  ] as const

  return (
    <section id="result" className="case-section optimization-section">
      <SectionIntro
        eyebrow="07 · CENTRAL OPTIMISATION RESULT"
        title="There was a lot of potential waste. We could not safely identify it early enough."
      >
        <p>
          The theoretical headroom used future knowledge. A deployable rule did
          not have that privilege: it had to decide using only information
          visible while the system was working.
        </p>
      </SectionIntro>

      <figure className="optimization-chart">
        <figcaption className="sr-only">
          Comparison of theoretical saving, required project target, and best
          practical saving.
        </figcaption>
        {rows.map((row) => (
          <div className="optimization-row" key={row.label}>
            <div className="optimization-label">
              <span>{row.label}</span>
              <strong>{pct(row.value)}</strong>
            </div>
            <div className="optimization-track" aria-hidden="true">
              <span
                className={`optimization-fill ${row.kind}`}
                style={{ width: `${Math.max(row.value * 100, 2.5)}%` }}
              />
            </div>
            <p>{row.detail}</p>
          </div>
        ))}
      </figure>

      <div className="decision-sentence">
        <span>Decision</span>
        <strong>
          The saving was not worth the reliability cost. Do not ship the
          adaptive approach.
        </strong>
      </div>
    </section>
  )
}

function UnderTheHood() {
  return (
    <section id="engineering" className="case-section">
      <SectionIntro
        eyebrow="11 · UNDER THE HOOD"
        title="The model was only one component in the reliability system."
      >
        <p>
          Technical depth lives here so the first read stays recruiter-friendly
          while the implementation remains inspectable.
        </p>
      </SectionIntro>

      <Tabs defaultValue="architecture" className="technical-tabs">
        <TabsList variant="line" aria-label="Technical layers">
          <TabsTrigger value="architecture">Architecture</TabsTrigger>
          <TabsTrigger value="evaluation">Evaluation</TabsTrigger>
          <TabsTrigger value="safety">Safety</TabsTrigger>
          <TabsTrigger value="evidence">Evidence</TabsTrigger>
        </TabsList>

        {Object.entries(underTheHood).map(([key, content]) => (
          <TabsContent value={key} key={key}>
            <div className="technical-panel">
              <div>
                <p className="technical-label">{key}</p>
                <h3>{content.title}</h3>
                <p>{content.description}</p>
                <ul>
                  {content.bullets.map((bullet) => (
                    <li key={bullet}>
                      <Check aria-hidden="true" />
                      <span>{bullet}</span>
                    </li>
                  ))}
                </ul>
              </div>

              <div className="technical-flow" aria-label={`${key} flow`}>
                {content.flow.map((step, index) => (
                  <div className="flow-step" key={step}>
                    <span>{String(index + 1).padStart(2, "0")}</span>
                    <strong>{step}</strong>
                  </div>
                ))}
              </div>
            </div>
          </TabsContent>
        ))}
      </Tabs>
    </section>
  )
}

function App() {
  const { benchmark, developmentOutcomes, deterministicControls, publicRelease } =
    evidence.publication
  const {
    fixedReference,
    deterministicFaults,
    adaptation,
    challenger,
    decision,
  } = evidence.metrics

  const timeline = [
    {
      label: "Baseline established",
      value: `${fixedReference.passes} / ${fixedReference.cases} development successes`,
    },
    {
      label: "Failure patterns analysed",
      value: `${developmentOutcomes.observedFailures} observed failures investigated`,
    },
    {
      label: "Safety controls challenged",
      value: `${deterministicFaults.passes} / ${deterministicFaults.cases} controlled tests passed`,
    },
    {
      label: "Efficiency opportunity studied",
      value: `${pct(adaptation.theoreticalReduction)} theoretical headroom`,
    },
    {
      label: "Practical rules tested",
      value: `${pct(adaptation.bestPracticalReduction)} saving + ${adaptation.observedPassLosses} regressions`,
    },
    {
      label: "Engineering decision",
      value: "Reject adaptive layer",
    },
    {
      label: "Final unseen set",
      value: `Preserved · ${decision.lockedCasesAccessed} cases consumed`,
    },
  ]

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
          <a href="#result">Results</a>
          <a href="#method">Method</a>
          <a href="#engineering">Engineering</a>
          <a href="#evidence">Evidence</a>
          <a href={links.repo} target="_blank" rel="noreferrer">
            GitHub <ArrowUpRight aria-hidden="true" />
          </a>
        </nav>
      </header>

      <main id="main-content">
        <section className="hero evidence-hero">
          <div className="hero-copy">
            <p className="eyebrow">HARBOURDESK · AI RELIABILITY STUDY</p>
            <h1>
              <span>{pct(adaptation.theoreticalReduction)}</span>
              theoretical headroom.
            </h1>
            <p className="lede">
              The opportunity looked substantial with hindsight. The strongest
              practical rule saved only {pct(adaptation.bestPracticalReduction)}
              {" "}and caused {adaptation.observedPassLosses} previously
              successful tasks to fail.
            </p>
          </div>

          <div className="hero-comparison" aria-label="Core optimization result">
            <div>
              <span>Required project target</span>
              <strong>{pct(adaptation.requiredTargetReduction, 0)}</strong>
            </div>
            <div>
              <span>Best practical rule</span>
              <strong>{pct(adaptation.bestPracticalReduction)}</strong>
              <small>
                + {adaptation.observedPassLosses} reliability regressions
              </small>
            </div>
          </div>

          <div className="hero-decision">
            <span>Engineering decision</span>
            <strong>Don&apos;t ship the adaptive approach.</strong>
          </div>

          <EvidenceRail />
        </section>

        <section className="case-section question-section">
          <SectionIntro
            eyebrow="02 · THE QUESTION"
            title="Can an AI system use less processing without becoming less reliable?"
          >
            <p>
              The baseline was allowed a fixed amount of work. The experiment
              tested whether some tasks could stop earlier without sacrificing
              correctness.
            </p>
          </SectionIntro>

          <div className="question-comparison">
            <div>
              <span className="technical-label">BASELINE SYSTEM</span>
              <h3>Fixed amount of work</h3>
              <p>
                Every task could continue to the same maximum processing
                budget.
              </p>
            </div>
            <div>
              <span className="technical-label">PROPOSED IDEA</span>
              <h3>Stop earlier when evidence says more work is unlikely to help</h3>
              <p>
                Savings only count if previously successful tasks stay
                successful.
              </p>
            </div>
          </div>
        </section>

        <section id="method" className="case-section">
          <SectionIntro
            eyebrow="03 · HOW IT WAS TESTED"
            title="The benchmark was staged so weak ideas could not consume the final evidence."
          >
            <p>
              The final unseen set was only available to an approach that first
              earned admission. No adaptive candidate did, so those cases stayed
              closed.
            </p>
          </SectionIntro>

          <div className="benchmark-summary">
            <strong>{benchmark.totalCases} cases</strong>
            <span>{benchmark.templateCount} templates</span>
            <span>{benchmark.failureFamilyCount} failure families</span>
          </div>

          <div className="benchmark-split">
            <div>
              <span className="split-number">{benchmark.developmentCases}</span>
              <strong>Development</strong>
              <p>Build and investigate the approach.</p>
            </div>
            <div>
              <span className="split-number">{benchmark.validationCases}</span>
              <strong>Validation</strong>
              <p>Separate evidence for checking a qualified approach.</p>
            </div>
            <div className="locked-split">
              <span className="split-number">{benchmark.lockedCases}</span>
              <strong>Final unseen tests</strong>
              <p>Opened only if the approach qualifies.</p>
              <span className="split-status">
                <Lock aria-hidden="true" /> Preserved
              </span>
            </div>
          </div>
        </section>

        <FailureFamilySection />

        <section className="case-section struggle-section">
          <SectionIntro
            eyebrow="05 · WHERE THE SYSTEM STRUGGLED"
            title="Finishing the task was not the same as getting it right."
          >
            <p>
              A terminal workflow can still end in the wrong decision. That is
              why completion rate was not treated as reliability.
            </p>
          </SectionIntro>

          <div className="outcome-grid">
            <div>
              <strong>{developmentOutcomes.passes}</strong>
              <span>passed</span>
            </div>
            <div>
              <strong>{developmentOutcomes.terminalButWrong}</strong>
              <span>terminal-but-wrong</span>
            </div>
            <div>
              <strong>{developmentOutcomes.nonterminalFailures}</strong>
              <span>non-terminal failures</span>
            </div>
          </div>

          <p className="outcome-callout">
            <strong>
              {pct(developmentOutcomes.terminalWrongShareOfFailures, 0)}
            </strong>{" "}
            of observed development failures finished the workflow but reached
            the wrong result.
          </p>

          <p className="reading-note">
            The hardest areas were conflicting records, permission boundaries,
            and interrupted previous actions.
          </p>
        </section>

        <section className="case-section fault-section">
          <SectionIntro
            eyebrow="06 · CONTROLLED FAILURE TESTING"
            title="What happens when the system around the AI breaks?"
          >
            <p>
              These were deterministic control tests, not live-model accuracy
              cases. They exercised failure handling around provider, tool,
              permission, state, and evidence boundaries.
            </p>
          </SectionIntro>

          <div className="fault-result">
            <div className="fault-score">
              <ShieldCheck aria-hidden="true" />
              <strong>
                {deterministicFaults.passes} / {deterministicFaults.cases}
              </strong>
              <span>controlled failure tests passed</span>
            </div>
            <div className="fault-controls">
              <div>
                <span>Defined safety-rule failures</span>
                <strong>{deterministicControls.definedSafetyRuleFailures}</strong>
              </div>
              <div>
                <span>Unexpected effective writes</span>
                <strong>{deterministicControls.unexpectedEffectiveWrites}</strong>
              </div>
            </div>
          </div>

          <div className="fault-categories" aria-label="Fault programme areas">
            {[
              "Provider / API",
              "Tool execution",
              "Limits",
              "Duplicate-action protection",
              "Permissions / policy",
              "Evidence integrity",
            ].map((item) => (
              <span key={item}>{item}</span>
            ))}
          </div>

          <p className="nonclaim">
            This does not prove universal production safety. It shows that the
            predeclared deterministic fault programme passed.
          </p>
        </section>

        <OptimizationResult />

        <section className="case-section challenger-section">
          <SectionIntro
            eyebrow="08 · MODEL CHALLENGER"
            title="A different model did not solve the problem either."
          >
            <p>
              This was a bounded challenger screen on the same frozen subset,
              not a universal model leaderboard.
            </p>
          </SectionIntro>

          <div className="challenger-table" role="table" aria-label="Model challenger comparison">
            <div role="row" className="challenger-row">
              <div role="cell">
                <span>{fixedReference.model}</span>
                <small>baseline subset</small>
              </div>
              <strong role="cell">
                {challenger.baselinePasses} / {challenger.cases}
              </strong>
              <span role="cell">{pct(challenger.baselinePassRate)}</span>
            </div>
            <div role="row" className="challenger-row">
              <div role="cell">
                <span>{challenger.model}</span>
                <small>challenger</small>
              </div>
              <strong role="cell">
                {challenger.passes} / {challenger.cases}
              </strong>
              <span role="cell">{pct(challenger.passRate)}</span>
            </div>
          </div>

          <div className="bounded-decision">
            <span>Decision</span>
            <strong>{challenger.decision.replaceAll("_", " ")}</strong>
          </div>
        </section>

        <section className="case-section engineering-decision">
          <SectionIntro
            eyebrow="09 · ENGINEERING DECISION"
            title="Reject the adaptive layer. Preserve the final unseen set."
          >
            <p>
              No adaptive candidate met the development threshold. The correct
              action was to stop rather than repeatedly test weak approaches
              against independent evidence.
            </p>
          </SectionIntro>

          <div className="decision-ledger">
            <div>
              <span>Experiment</span>
              <strong>Complete</strong>
            </div>
            <div>
              <span>Adaptive approach</span>
              <strong>Rejected during development</strong>
            </div>
            <div>
              <span>Final unseen tests</span>
              <strong>Preserved and not opened</strong>
            </div>
            <div>
              <span>Formal research verdict</span>
              <strong>{decision.finalVerdict}</strong>
            </div>
          </div>

          <div className="inconclusive-explainer">
            <span>Why “inconclusive”?</span>
            <p>
              The frozen rules required a qualified candidate before the final
              paired comparison could run. No candidate earned admission, so
              final quality and efficiency were not measured. “Inconclusive”
              preserves that distinction rather than pretending an unexecuted
              gate passed or failed.
            </p>
          </div>
        </section>

        <section className="case-section journey-section">
          <SectionIntro
            eyebrow="10 · EXPERIMENT JOURNEY"
            title="A sequence of gates, not a hunt for a positive result."
          />
          <ol className="timeline">
            {timeline.map((item, index) => (
              <li key={item.label}>
                <span className="timeline-index">
                  {String(index + 1).padStart(2, "0")}
                </span>
                <div>
                  <strong>{item.label}</strong>
                  <p>{item.value}</p>
                </div>
              </li>
            ))}
          </ol>
        </section>

        <UnderTheHood />

        <section id="evidence" className="case-section evidence-section">
          <SectionIntro
            eyebrow="12 · EVIDENCE & REPRODUCIBILITY"
            title="Don’t trust the headline. Inspect the evidence."
          >
            <p>
              The public layer is intentionally smaller than the internal
              evidence surface: enough to verify the published claims without
              exposing private benchmark material.
            </p>
          </SectionIntro>

          <div className="evidence-links">
            <a href={links.repo} target="_blank" rel="noreferrer">
              GitHub repository <ArrowUpRight aria-hidden="true" />
            </a>
            <a href={links.methodology} target="_blank" rel="noreferrer">
              Methodology <ArrowUpRight aria-hidden="true" />
            </a>
            <a href={links.results} target="_blank" rel="noreferrer">
              Sanitized results <ArrowUpRight aria-hidden="true" />
            </a>
          </div>

          <div className="evidence-ledger">
            <div>
              <FileCheck aria-hidden="true" />
              <span>Public release</span>
              <strong>R11 {publicRelease.status}</strong>
            </div>
            <div>
              <Database aria-hidden="true" />
              <span>Public files</span>
              <strong>{publicRelease.publicFileCount}</strong>
            </div>
            <div>
              <Lock aria-hidden="true" />
              <span>Locked cases consumed</span>
              <strong>{decision.lockedCasesAccessed}</strong>
            </div>
            <div>
              <GitBranch aria-hidden="true" />
              <span>Adaptive promotion</span>
              <strong>{decision.adaptiveRuntimePromotion}</strong>
            </div>
          </div>

          <dl className="hash-ledger">
            <div>
              <dt>Release ZIP SHA256</dt>
              <dd>{evidence.source.releaseZipSha256}</dd>
            </div>
            <div>
              <dt>Results SHA256</dt>
              <dd>{evidence.source.resultsSha256}</dd>
            </div>
            <div>
              <dt>R11 release commit</dt>
              <dd>{evidence.source.releaseCommit}</dd>
            </div>
          </dl>

          <div className="privacy-boundary">
            <strong>Public boundary</strong>
            <span>
              No raw traces · No private expectations · No validation payloads ·
              No locked case payloads
            </span>
          </div>

          <details className="nonclaims">
            <summary>Explicit non-claims</summary>
            <ul>
              {evidence.nonClaims.map((claim) => (
                <li key={claim}>{claim}</li>
              ))}
            </ul>
          </details>
        </section>
      </main>

      <footer>
        <span>HarbourDesk · Adaptive Agent Runtime reliability case study</span>
        <span>
          Formal verdict <strong>{decision.finalVerdict}</strong>
        </span>
      </footer>
    </>
  )
}

export default App
