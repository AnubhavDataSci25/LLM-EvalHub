import { addingMetricPackSection } from './sections/addingMetricPack.js'
import { addingProviderSection } from './sections/addingProvider.js'
import { apiReferenceSection } from './sections/apiReference.js'
import { architectureSection } from './sections/architecture.js'
import { benchmarksSection } from './sections/benchmarks.js'
import { compareSection } from './sections/compare.js'
import { conceptsSection } from './sections/concepts.js'
import { dashboardSection } from './sections/dashboard.js'
import { dataModelSection } from './sections/dataModel.js'
import { datasetsSection } from './sections/datasets.js'
import { documentsSection } from './sections/documents.js'
import { experimentsSection } from './sections/experiments.js'
import { failuresDiagnosisSection } from './sections/failuresDiagnosis.js'
import { improvementLoopSection } from './sections/improvementLoop.js'
import { installationSection } from './sections/installation.js'
import { metricsReferenceSection } from './sections/metricsReference.js'
import { newEvaluationSection } from './sections/newEvaluation.js'
import { overviewSection } from './sections/overview.js'
import { quickstartSection } from './sections/quickstart.js'
import { recommendationsSection } from './sections/recommendations.js'
import { reportsSection } from './sections/reports.js'
import { runningEvaluationsSection } from './sections/runningEvaluations.js'
import { scoreLimitationsSection } from './sections/scoreLimitations.js'
import { settingsProvidersSection } from './sections/settingsProviders.js'

export const DOC_SECTIONS = [
  // Group A: Getting started
  overviewSection,
  quickstartSection,
  installationSection,
  conceptsSection,

  // Group B: Using the platform
  dashboardSection,
  datasetsSection,
  benchmarksSection,
  documentsSection,
  newEvaluationSection,
  runningEvaluationsSection,
  experimentsSection,
  compareSection,
  failuresDiagnosisSection,
  improvementLoopSection,
  recommendationsSection,
  reportsSection,
  settingsProvidersSection,

  // Group C: Evaluation reference
  metricsReferenceSection,
  scoreLimitationsSection,

  // Group D: Technical reference
  architectureSection,
  apiReferenceSection,
  addingProviderSection,
  addingMetricPackSection,
  dataModelSection,
]

export const DOC_GROUPS = [
  {
    name: 'Getting started',
    sections: DOC_SECTIONS.filter((s) => s.group === 'Getting started'),
  },
  {
    name: 'Using the platform',
    sections: DOC_SECTIONS.filter((s) => s.group === 'Using the platform'),
  },
  {
    name: 'Evaluation reference',
    sections: DOC_SECTIONS.filter((s) => s.group === 'Evaluation reference'),
  },
  {
    name: 'Technical reference',
    sections: DOC_SECTIONS.filter((s) => s.group === 'Technical reference'),
  },
]

export function getAllSections() {
  return DOC_SECTIONS
}

export function getSection(id) {
  if (!id) return DOC_SECTIONS[0]
  return DOC_SECTIONS.find((s) => s.id === id) || null
}

export function getAdjacentSections(id) {
  const currentIndex = DOC_SECTIONS.findIndex((s) => s.id === id)
  if (currentIndex === -1) {
    return { prev: null, next: DOC_SECTIONS[1] || null }
  }
  return {
    prev: currentIndex > 0 ? DOC_SECTIONS[currentIndex - 1] : null,
    next: currentIndex < DOC_SECTIONS.length - 1 ? DOC_SECTIONS[currentIndex + 1] : null,
  }
}

export function getSectionHeadings(section) {
  if (!section || !section.blocks) return []
  return section.blocks
    .filter((b) => b.type === 'heading')
    .map((b) => ({
      id: b.id,
      text: b.text,
      level: b.level || 2,
    }))
}
