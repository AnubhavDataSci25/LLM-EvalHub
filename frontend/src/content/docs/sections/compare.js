export const compareSection = {
  id: 'compare',
  title: 'Compare & Statistical Testing',
  group: 'Using the platform',
  summary: 'Measure model-vs-model and run-vs-run performance with metric deltas, paired bootstrap confidence intervals, permutation tests, and explicit uncertainty verdicts.',
  blocks: [
    {
      type: 'paragraph',
      text: 'The Compare page (`/compare`) answers the fundamental question behind evaluation: *did this change actually improve the system?* It supports two comparison modes: model-vs-model within a single run, and run-vs-run across different experiments.',
    },
    {
      type: 'heading',
      id: 'understanding-deltas',
      level: 2,
      text: 'Reading Metric Deltas: Why a Delta is Not Proof',
    },
    {
      type: 'paragraph',
      text: 'In standard evaluation tools, an observed metric difference (e.g. +0.04 in correctness) is reported as a flat win. However, on small or noisy test sets, random variance often creates an apparent improvement that fails to replicate.',
    },
    {
      type: 'callout',
      tone: 'honesty',
      title: 'A Delta is Not a Proof of Improvement',
      body: 'A positive delta without uncertainty bounds is often noise. In LLM-EvalHub, a metric delta is only classified as an improvement if it passes a paired sign-flip permutation test ($p < 0.05$) and its 95% bootstrap confidence interval excludes zero.',
    },
    {
      type: 'heading',
      id: 'statistical-pipeline',
      level: 2,
      text: 'Statistical Significance Pipeline',
    },
    {
      type: 'paragraph',
      text: 'When comparing runs or models, LLM-EvalHub executes a four-step statistical analysis:',
    },
    {
      type: 'list',
      items: [
        '1. Strict Paired Alignment: Cases are paired by test_case_id AND provider/model. Any case where a metric is unavailable on either side is excluded from paired calculations, and the dropped count is explicitly reported.',
        '2. Bootstrap Confidence Intervals: A 10,000-resample non-parametric bootstrap computes the 95% confidence interval [CI_low, CI_high] for the mean delta.',
        '3. Paired Permutation Test: An exact or Monte Carlo sign-flip permutation test computes the empirical two-sided p-value.',
        '4. Effect Size: Computes Cohen\'s d_z for paired differences, quantifying the standardized magnitude of the shift.',
      ],
    },
    {
      type: 'heading',
      id: 'verdict-classification',
      level: 2,
      text: 'Statistical Verdict Taxonomy',
    },
    {
      type: 'table',
      caption: 'Comparison Verdict Classification',
      headers: ['Verdict', 'Badge Tone', 'Criteria', 'Interpretation'],
      rows: [
        ['`improved`', 'Good (Green)', 'p < 0.05 AND 95% CI > 0', 'Statistically significant improvement. You can defend deploying this fix.'],
        ['`regressed`', 'Bad (Red)', 'p < 0.05 AND 95% CI < 0', 'Statistically significant regression. The change damaged quality.'],
        ['`no_change`', 'Neutral (Gray)', '|delta| < 0.005', 'Metric is effectively unchanged between configurations.'],
        ['`inconclusive`', 'Warn (Yellow)', 'CI spans across 0.0', 'Observed movement is statistically indistinguishable from random noise.'],
        ['`underpowered`', 'Warn (Yellow)', 'Sample size N < 8', 'Too few paired test cases to detect a meaningful statistical effect.'],
      ],
    },
  ],
}
