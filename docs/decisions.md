# Architecture decision record

Each entry states the decision, why it was made, and what was given up.

---

## ADR-001 — LangGraph per work unit, not per run

**Decision.** The evaluation graph is invoked once per (test case × model) rather than once per run.

**Why.** Per-run orchestration would need loops, partial-failure branches and accumulator state inside the graph. Per-unit orchestration has exactly one conditional edge — `rag_enabled` — which is exactly the amount of control flow the pipeline actually has. Partial persistence and failure isolation become natural rather than engineered.

**Trade-off.** Cross-unit concerns (aggregation) live in the service layer rather than the graph. That is the correct place for them, but it means the graph does not represent the entire run.

---

## ADR-002 — Unavailable, never zero

**Decision.** A metric whose required input is absent returns `available=False` with a reason, and is excluded from aggregates.

**Why.** Scoring correctness as 0.0 for a dataset with no reference answers would make a model look catastrophically bad for a property of the dataset. In a tool whose output feeds model selection, conflating "unknown" with "wrong" is the most damaging error available.

**Trade-off.** Every consumer — aggregation, comparison, recommendation, the UI — must handle `None`. That cost is paid once and prevents a whole class of silent misreporting.

---

## ADR-003 — One tokenizer for metrics and retrieval

**Decision.** `app/core/text.py` is the single tokenizer; the deterministic metrics, the lexical embedder and the BM25 index all use it.

**Why.** Originally the metrics stemmed tokens while the embedder did not. The retriever therefore did not consider "refunds" a match for "refund", but `context_recall` did — so retrieval quality and the retrieval *metrics* were measuring different things.

**Measured effect** on the `rag_qa` pack:

| | Before | After |
|---|---|---|
| `context_recall` | 0.53 | **0.91** |
| `poor_retrieval` failures | 12 | **2** |

**Trade-off.** The RAG layer now depends on a core utility. That is acceptable; the alternative was a measurement tool whose components disagreed about word identity.

---

## ADR-004 — Magnitude-preserving normalisation in recommendations

**Decision.** Quality metrics (already 0–1) are used at their measured value. Latency, being unbounded, is scored as `fastest / this`.

**Why.** The first implementation min-max normalised every metric across candidates. With two candidates that collapses each metric to exactly 0 or 1, so a 0.90-vs-0.88 gap scored identically to 0.90-vs-0.30 and the ranking degenerated into a comparison of weight sums. Two-model comparison is the most common case, so the degenerate case was the normal case.

**Trade-off.** Absolute quality values now influence the score, so a field where every model scores ~0.9 produces small differences. That is honest: the models really are close.

A regression test asserts that a wide gap produces a larger score difference than a narrow one.

---

## ADR-005 — Ordered failure cascade

**Decision.** Classification runs in a fixed order: infrastructure → retrieval → grounding → answer quality → latency. The first match wins.

**Why.** Symptoms overlap. A case with a failed retrieval also shows low correctness and low faithfulness. Reporting it as a hallucination would send an engineer to tune the prompt when the passage was never retrieved. Ordering encodes causality: fix what happened first.

**Trade-off.** A case with genuinely independent problems reports only the earliest. The stored evidence includes every signal, so the others remain visible.

---

## ADR-006 — Two diagnosis engines, merged

**Decision.** The heuristic engine always runs. When a judge is configured, the LLM's output is merged into the heuristic's — LLM reasoning, heuristic actions.

**Why.** The LLM explains *why* better. The heuristic guarantees every suggestion maps to a real configuration field the improvement loop can apply. Taking the LLM's suggestions verbatim would produce prose that no automation could act on; taking only the heuristic's would lose the reasoning.

**Trade-off.** Merge logic is fiddly. The alternative — an improvement loop that cannot apply its own suggestions — is worse.

---

## ADR-007 — Deterministic test provider

**Decision.** Ship a provider producing deterministic extractive output, with selectable failure behaviours.

**Why.** The test suite must be reproducible, free and offline. It also makes the platform demonstrable without credentials, and lets the failure taxonomy be tested deliberately (`mock-hallucinate` reliably produces a hallucination).

**Trade-off.** Its output could be mistaken for a benchmark result. It is labelled as a test fixture in the provider list, the model picker and the README.

---

## ADR-008 — Hashing embedder as the default

**Decision.** Default to a deterministic lexical hash embedder; semantic embedders are opt-in.

**Why.** A 90 MB model download on first index is a poor default for a tool meant to run on any hardware, and non-determinism in the retrieval layer undermines regression testing. Sharing the tokenizer with the metrics (ADR-003) makes the lexical path perform respectably.

**Trade-off.** Weaker paraphrase handling. The Documents page states which embedder produced an index, and semantic embedders are one environment variable away.

---

## ADR-009 — Server-side credentials, always

**Decision.** No provider key ever reaches the browser. The frontend learns only whether a provider is configured.

**Why.** A key in browser storage or in a bundle is a key that leaks. The proxy costs one hop and removes the entire class of problem.

**Trade-off.** No direct browser-to-provider streaming. Not needed: this is a batch evaluation tool, not a chat interface.

A test sets a sentinel credential and asserts it appears nowhere in any API response.

---

## ADR-010 — Web reports first, PDF deferred

**Decision.** Reports are frozen JSON rendered as web pages, with JSON and CSV export. PDF is out of MVP scope.

**Why.** PDF generation adds a heavy dependency and layout work that serves presentation, not evidence. CSV covers the actual need — people paste results into spreadsheets.

**Trade-off.** No single-file artefact for sharing outside the tool. JSON export is complete enough to reconstruct one.

---

## ADR-011 — Paired bootstrap and permutation test instead of a t-test

**Decision.** All run-vs-run and model-vs-model metric comparisons use a paired bootstrap confidence interval (percentile method) and a two-sided sign-flip permutation test instead of Student's t-test. Sample size requirements use a normal-approximation power calculation.

**Why.** Metric scores in LLM evaluations violate standard parametric t-test assumptions:
1. **Bounded and multimodal.** Quality metrics live on [0, 1] (often clustering at 0.0 or 1.0 for binary or pass/fail deterministic checks), making normality assumptions invalid.
2. **Naturally paired.** Models answer identical test cases; treating observations as independent two-sample data discards pairing correlation and loses power.
3. **Non-parametric robustness.** The paired sign-flip permutation test is exact for $n \le 15$ and distribution-free under Monte Carlo for $n > 15$, while the percentile bootstrap provides intuitive uncertainty intervals without requiring variance symmetry.

**Trade-off.** The normal approximation for required sample size ($n = \lceil((z_{1-\alpha/2} + z_{\text{power}}) / d_z)^2\rceil$) assumes approximate asymptotic normality of mean differences; for very small samples with heavy tails it is an approximation rather than an exact power calculation. However, it requires no external libraries like SciPy, computes instantly in pure NumPy/math, and gives practical guidance on whether a null finding is genuinely absent or merely underpowered.

---

## ADR-012 — Judge calibration using Cohen's kappa and bias probes

**Decision.** Every judge-scored metric is calibrated against blind human labels using Cohen's kappa ($\kappa$), quadratic-weighted kappa ($\kappa_w$), paired bootstrap confidence intervals, and three targeted bias probes (order swap, verbosity padding, self-preference) before being trusted in recommendations and reports.

**Why.** LLM judges suffer from systematic biases and non-random errors that raw percentage agreement masks:
1. **Chance correction over raw accuracy.** Raw percentage agreement inflates confidence when labels are skewed (e.g., if 85% of cases are correct, a judge predicting "correct" uniformly achieves 85% raw accuracy). Cohen's kappa corrects for the expected baseline agreement by chance ($P_e$).
2. **Three-class discretisation (0, 1, 2).** Quality scores in [0, 1] are mapped into 0 (incorrect, $<0.34$), 1 (partial, $0.34 \le s < 0.67$), and 2 (correct, $\ge 0.67$). This mirrors standard rubric evaluation (incorrect / partially correct / correct) and avoids artificial continuous-precision false precision in subjective assessment.
3. **Quadratic-weighted kappa for ordinal severity.** The distance between incorrect (0) and correct (2) is worse than between partial (1) and correct (2). Quadratic weighting assigns penalising weights $(i-j)^2 / (k-1)^2$, properly penalising severe misclassifications ($0 \leftrightarrow 2$) more heavily than adjacent disagreements ($0 \leftrightarrow 1$ or $1 \leftrightarrow 2$).
4. **Isolated bias probes.** Probes isolate single confounding factors without modifying existing evaluation results:
   - *Order swap:* Flips reference and candidate order in the judge prompt to detect positional bias.
   - *Verbosity padding:* Appends a 77-word neutral filler to measure length-bias inflation.
   - *Self-preference:* Measures whether the judge rates models from its own model family higher than external models.

**Trade-off.** 
- **Single-annotator scope:** When calibrated against a single annotator, $\kappa$ measures agreement with that individual rather than absolute ground truth. The system explicitly reports this caveat and hedges verdict wording.
- **Sample size limits:** With fewer than 10 labels, kappa estimation is underpowered; the system returns `insufficient_labels` with no fabricated kappa.
- **Landis-Koch conventional boundaries:** Landis-Koch thresholds ($<0$ poor, $0\text{--}0.20$ slight, $0.21\text{--}0.40$ fair, $0.41\text{--}0.60$ moderate, $0.61\text{--}0.80$ substantial, $0.81\text{--}1.00$ almost perfect) are widely used conventions in NLP and medical literature, but are domain-dependent guidelines rather than universal thresholds.

