export const reportsSection = {
  id: 'reports',
  title: 'Reports & Export',
  group: 'Using the platform',
  summary: 'Generate immutable audit-ready evaluation reports, export raw metrics and work unit data in JSON and CSV formats, and prepare executive summaries.',
  blocks: [
    {
      type: 'paragraph',
      text: 'The Reports page (`/reports`) and Report Detail view (`/reports/:id`) allow you to compile, persist, and export evaluation summaries. A report is an immutable snapshot compiled from stored database records, guaranteeing that figures never shift retroactively.',
    },
    {
      type: 'heading',
      id: 'report-sections',
      level: 2,
      text: 'Report Structure and Contents',
    },
    {
      type: 'list',
      items: [
        'Executive Summary: High-level overview of the evaluated dataset, candidate models, headline quality scores, and aggregate pass rates.',
        'Model Comparison Table: Side-by-side performance matrix showing metric averages, sample sizes, and latency benchmarks.',
        'Failure Taxonomy Breakdown: Proportions of failures classified into the 10 failure categories (hallucination, retrieval gap, timeout, etc.).',
        'Judge Calibration Summary: Measured Cohen\'s kappa reliability and bias probe results for any LLM judges used.',
        'Configuration & Provenance: The exact prompt templates, parameters, and retrieval settings used during the evaluation.',
      ],
    },
    {
      type: 'heading',
      id: 'export-formats',
      level: 2,
      text: 'Export Formats: JSON and CSV',
    },
    {
      type: 'table',
      caption: 'Supported Report Exports',
      headers: ['Format', 'Endpoint', 'Contents', 'Primary Use Case'],
      rows: [
        ['JSON', '`/api/reports/:id/export?format=json`', 'Complete structured report tree including configuration snapshots, metric summaries, and calibration data.', 'Automated ingestion into CI/CD pipelines or enterprise data lakes.'],
        ['CSV', '`/api/reports/:id/export?format=csv`', 'Flat tabular export of every work unit: question, model, generated answer, ground truth, scores, and failure status.', 'Ad-hoc analysis in pandas, Excel, Google Sheets, or BI dashboards.'],
      ],
    },
    {
      type: 'callout',
      tone: 'honesty',
      title: 'PDF Status and Printing',
      body: 'Automated backend PDF generation is intentionally excluded from the platform dependencies to keep backend deployments lightweight. To generate a PDF report, open the report in your browser and use standard Print to PDF (`Ctrl+P` / `Cmd+P`). The application includes dedicated `@media print` stylesheets that strip navigation bars and format tables cleanly for document printing.',
    },
  ],
}
