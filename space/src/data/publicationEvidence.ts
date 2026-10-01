import { publicEvidence as frozenEvidence } from "./publicEvidence.generated"

export const publicationEvidence = {
  ...frozenEvidence,
  publication: {
    benchmark: {
      totalCases: 180,
      templateCount: 36,
      failureFamilyCount: 6,
      developmentCases: 90,
      validationCases: 30,
      lockedCases: 60,
      source:
        "docs/checkpoints/2026-09-28-r4-benchmark-and-final-acceptance-contract.md",
    },
    developmentOutcomes: {
      passes: 43,
      terminalButWrong: 36,
      nonterminalFailures: 11,
      observedFailures: 47,
      terminalWrongShareOfFailures: 36 / 47,
      source: "docs/checkpoints/2026-09-29-r5-fixed-reference-closeout.md",
    },
    failureFamilies: {
      denominator: 15,
      results: {
        F1: 15,
        F3: 14,
        F2: 7,
        F6: 4,
        F4: 2,
        F5: 1,
      },
      source:
        "HarbourDesk_HuggingFace_UI_Design_Spec_v1_2026-09-29:SECTION_09",
    },
    deterministicControls: {
      definedSafetyRuleFailures: 0,
      unexpectedEffectiveWrites: 0,
      source: "R11_PUBLIC_RELEASE:README.md",
    },
    publicRelease: {
      status: "PASS",
      publicFileCount: 9,
      source: "R11_PUBLIC_RELEASE",
    },
  },
} as const

const benchmark = publicationEvidence.publication.benchmark
const outcomes = publicationEvidence.publication.developmentOutcomes
const families = publicationEvidence.publication.failureFamilies
const familyPassTotal = Object.values(families.results).reduce(
  (total, value) => total + value,
  0
)

if (
  benchmark.totalCases !==
    benchmark.developmentCases + benchmark.validationCases + benchmark.lockedCases ||
  outcomes.passes + outcomes.terminalButWrong + outcomes.nonterminalFailures !==
    benchmark.developmentCases ||
  familyPassTotal !== outcomes.passes ||
  benchmark.failureFamilyCount * families.denominator !== benchmark.developmentCases
) {
  throw new Error("HarbourDesk publication evidence contract is inconsistent")
}
