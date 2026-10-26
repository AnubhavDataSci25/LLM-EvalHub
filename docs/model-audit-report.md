# Model Availability Audit Report

**Generated:** 2026-10-26 09:48:31 UTC
**Auditor:** LLM-EvalHub Live Model Availability Prober

---

## Executive Summary

This report audits the static catalog entries (`app/providers/catalog.py`) against live provider model listings and empirical verification probes (cheap text-generation probes with `max_tokens=8`, `temperature=0`).

## 1. Dead or Unavailable Models in Static Catalog

The following models exist in `_CATALOG` but failed live verification probes (retired, renamed, 404, or plan restricted):

| Provider | Model ID | Status | Reason |
|---|---|---|---|
| `groq` | `llama-3.3-70b-versatile` | **`NOT_FOUND`** | Model not found or retired (404): Model or endpoint not found on 'groq': The model `llama-3.3-70b-ve |
| `groq` | `llama-3.1-8b-instant` | **`NOT_FOUND`** | Model not found or retired (404): Model or endpoint not found on 'groq': The model `llama-3.1-8b-ins |
| `groq` | `qwen/qwen3-32b` | **`NOT_FOUND`** | Model not found or retired (404): Model or endpoint not found on 'groq': The model `qwen/qwen3-32b`  |
| `gemini` | `gemini-2.5-flash` | **`NOT_FOUND`** | Model not found or retired (404): Gemini request failed: This model models/gemini-2.5-flash is no lo |
| `gemini` | `gemini-2.5-flash-lite` | **`NOT_FOUND`** | Model not found or retired (404): Gemini request failed: This model models/gemini-2.5-flash-lite is  |
| `gemini` | `gemini-2.5-pro` | **`NOT_FOUND`** | Model not found or retired (404): Gemini request failed: This model models/gemini-2.5-pro is no long |
| `gemini` | `gemini-2.0-flash` | **`NOT_FOUND`** | Model not found or retired (404): Gemini request failed: This model models/gemini-2.0-flash is no lo |
| `huggingface` | `meta-llama/Llama-3.3-70B-Instruct` | **`NOT_ENTITLED`** | Tier/plan restricted: Quota or payment required on 'huggingface': You have no remaining credits. Pur |
| `huggingface` | `meta-llama/Llama-3.1-8B-Instruct` | **`NOT_ENTITLED`** | Tier/plan restricted: Quota or payment required on 'huggingface': You have no remaining credits. Pur |
| `huggingface` | `Qwen/Qwen2.5-7B-Instruct` | **`NOT_FOUND`** | Probe rejected: Request rejected by 'huggingface': The requested model 'Qwen/Qwen2.5-7B-Instruct' is |
| `huggingface` | `deepseek-ai/DeepSeek-R1` | **`NOT_ENTITLED`** | Tier/plan restricted: Quota or payment required on 'huggingface': You have no remaining credits. Pur |
| `huggingface` | `openai/gpt-oss-120b` | **`NOT_ENTITLED`** | Tier/plan restricted: Quota or payment required on 'huggingface': You have no remaining credits. Pur |
| `openrouter` | `qwen/qwen3-30b-a3b-instruct` | **`NOT_FOUND`** | Probe rejected: Request rejected by 'openrouter': qwen/qwen3-30b-a3b-instruct is not a valid model I |
| `nvidia_nim` | `meta/llama-3.3-70b-instruct` | **`NOT_FOUND`** | Probe rejected: Request rejected by 'nvidia_nim': The model 'meta/llama-3.3-70b-instruct' has reache |
| `nvidia_nim` | `meta/llama-3.1-8b-instruct` | **`NOT_FOUND`** | Probe rejected: Request rejected by 'nvidia_nim': The model 'meta/llama-3.1-8b-instruct' has reached |
| `nvidia_nim` | `nvidia/llama-3.1-nemotron-nano-8b-v1` | **`NOT_FOUND`** | Probe rejected: Request rejected by 'nvidia_nim': The model 'nvidia/llama-3.1-nemotron-nano-8b-v1' h |
| `nvidia_nim` | `openai/gpt-oss-120b` | **`NOT_FOUND`** | Probe rejected: Request rejected by 'nvidia_nim': The model 'openai/gpt-oss-120b' has reached its en |
| `nvidia_nim` | `qwen/qwen3-next-80b-a3b-instruct` | **`NOT_FOUND`** | Probe rejected: Request rejected by 'nvidia_nim': The model 'qwen/qwen3-next-80b-a3b-instruct' has r |

## 2. Available Models Missing from Static Catalog

The following models were discovered live and confirmed **AVAILABLE** via probes, but are absent from the static catalog:

| Provider | Model ID | Latency |
|---|---|---|
| `groq` | `openai/gpt-oss-20b` | 1065ms |
| `groq` | `qwen/qwen3.8-27b` | 783ms |
| `groq` | `allam-2-7b` | 863ms |
| `gemini` | `gemma-4-26b-a4b-it` | 1731ms |
| `gemini` | `gemini-flash-lite-latest` | 1131ms |
| `openrouter` | `moonshotai/kimi-k3.1-pro` | 3599ms |
| `openrouter` | `recursive/flint-v1.0:free` | 951ms |
| `openrouter` | `minimax/minimax-m3.1-flash` | 1757ms |
| `openrouter` | `deepseek/deepseek-v4.1-flash-1017` | 1663ms |
| `openrouter` | `elorian/glimpse` | 1167ms |
| `mock` | `mock-extractive` | 12ms |
| `mock` | `mock-verbose` | 16ms |
| `mock` | `mock-hallucinate` | 16ms |

## 3. Detailed Provider Audit Results

### Provider: `groq` (Groq)
* **Base URL:** `https://api.groq.com/openai/v1`
* **Configured:** Yes

#### Static Catalog Verification
| Model ID | Probe Status | Latency | Reason |
|---|---|---|---|
| `llama-3.3-70b-versatile` | **`NOT_FOUND`** | 1455ms | Model not found or retired (404): Model or endpoint not found on 'groq': The mod |
| `llama-3.1-8b-instant` | **`NOT_FOUND`** | 728ms | Model not found or retired (404): Model or endpoint not found on 'groq': The mod |
| `openai/gpt-oss-120b` | **`AVAILABLE`** | 1061ms | Probe succeeded with non-empty response. |
| `qwen/qwen3-32b` | **`NOT_FOUND`** | 576ms | Model not found or retired (404): Model or endpoint not found on 'groq': The mod |

#### Live Discovered Text-Generation Candidates (4 total)
- `openai/gpt-oss-20b`: **`AVAILABLE`** (1065ms) — Probe succeeded with non-empty response.
- `qwen/qwen3.8-27b`: **`AVAILABLE`** (783ms) — Probe succeeded with non-empty response.
- `allam-2-7b`: **`AVAILABLE`** (863ms) — Probe succeeded with non-empty response.
- `openai/gpt-oss-120b`: **`AVAILABLE`** (1559ms) — Probe succeeded with non-empty response.

### Provider: `gemini` (Google Gemini)
* **Base URL:** `https://generativelanguage.googleapis.com/v1beta`
* **Configured:** Yes

#### Static Catalog Verification
| Model ID | Probe Status | Latency | Reason |
|---|---|---|---|
| `gemini-2.5-flash` | **`NOT_FOUND`** | 1337ms | Model not found or retired (404): Gemini request failed: This model models/gemin |
| `gemini-2.5-flash-lite` | **`NOT_FOUND`** | 1757ms | Model not found or retired (404): Gemini request failed: This model models/gemin |
| `gemini-2.5-pro` | **`NOT_FOUND`** | 1067ms | Model not found or retired (404): Gemini request failed: This model models/gemin |
| `gemini-2.0-flash` | **`NOT_FOUND`** | 1267ms | Model not found or retired (404): Gemini request failed: This model models/gemin |

#### Live Discovered Text-Generation Candidates (41 total)
- `gemini-2.5-flash`: **`NOT_FOUND`** (967ms) — Model not found or retired (404): Gemini request failed: This model models/gemin
- `gemini-2.5-pro`: **`NOT_FOUND`** (867ms) — Model not found or retired (404): Gemini request failed: This model models/gemin
- `gemma-4-26b-a4b-it`: **`AVAILABLE`** (1731ms) — Probe succeeded with non-empty response.
- `gemma-4-31b-it`: **`UPSTREAM_ERROR`** (1479ms) — Upstream error (500): Upstream error from Gemini: Internal error encountered.
- `gemini-flash-latest`: **`TIMEOUT`** (10430ms) — Probe timed out: Gemini timed out after 10s.
- `gemini-flash-lite-latest`: **`AVAILABLE`** (1131ms) — Probe succeeded with non-empty response.

### Provider: `huggingface` (Hugging Face)
* **Base URL:** `https://router.huggingface.co/v1`
* **Configured:** Yes

#### Static Catalog Verification
| Model ID | Probe Status | Latency | Reason |
|---|---|---|---|
| `meta-llama/Llama-3.3-70B-Instruct` | **`NOT_ENTITLED`** | 1334ms | Tier/plan restricted: Quota or payment required on 'huggingface': You have no re |
| `meta-llama/Llama-3.1-8B-Instruct` | **`NOT_ENTITLED`** | 983ms | Tier/plan restricted: Quota or payment required on 'huggingface': You have no re |
| `Qwen/Qwen2.5-7B-Instruct` | **`NOT_FOUND`** | 793ms | Probe rejected: Request rejected by 'huggingface': The requested model 'Qwen/Qwe |
| `deepseek-ai/DeepSeek-R1` | **`NOT_ENTITLED`** | 1069ms | Tier/plan restricted: Quota or payment required on 'huggingface': You have no re |
| `openai/gpt-oss-120b` | **`NOT_ENTITLED`** | 807ms | Tier/plan restricted: Quota or payment required on 'huggingface': You have no re |

#### Live Discovered Text-Generation Candidates (128 total)
- `deepseek-ai/DeepSeek-V4.1-Flash-1017`: **`NOT_ENTITLED`** (808ms) — Tier/plan restricted: Quota or payment required on 'huggingface': You have no re
- `MiniMaxAI/MiniMax-M3.1-Flash`: **`NOT_ENTITLED`** (806ms) — Tier/plan restricted: Quota or payment required on 'huggingface': You have no re
- `Qwen/Qwen3.8-27B`: **`NOT_ENTITLED`** (991ms) — Tier/plan restricted: Quota or payment required on 'huggingface': You have no re
- `meta-models/Muse-Spark-Open-816B-A42B`: **`NOT_ENTITLED`** (968ms) — Tier/plan restricted: Quota or payment required on 'huggingface': You have no re
- `reflection/Beam-1.0-501B-A23B`: **`NOT_ENTITLED`** (882ms) — Tier/plan restricted: Quota or payment required on 'huggingface': You have no re
- `deepseek-ai/DeepSeek-V4.1-Flash`: **`NOT_ENTITLED`** (796ms) — Tier/plan restricted: Quota or payment required on 'huggingface': You have no re

### Provider: `openrouter` (OpenRouter)
* **Base URL:** `https://openrouter.ai/api/v1`
* **Configured:** Yes

#### Static Catalog Verification
| Model ID | Probe Status | Latency | Reason |
|---|---|---|---|
| `meta-llama/llama-3.3-70b-instruct` | **`AVAILABLE`** | 2700ms | Probe succeeded with non-empty response. |
| `google/gemma-3-27b-it` | **`AVAILABLE`** | 2708ms | Probe succeeded with non-empty response. |
| `qwen/qwen3-30b-a3b-instruct` | **`NOT_FOUND`** | 594ms | Probe rejected: Request rejected by 'openrouter': qwen/qwen3-30b-a3b-instruct is |
| `mistralai/mistral-small-3.2-24b-instruct` | **`AVAILABLE`** | 2480ms | Probe succeeded with non-empty response. |

#### Live Discovered Text-Generation Candidates (457 total)
- `moonshotai/kimi-k3.1-pro`: **`AVAILABLE`** (3599ms) — Probe succeeded with non-empty response.
- `recursive/flint-v1.0:free`: **`AVAILABLE`** (951ms) — Probe succeeded with non-empty response.
- `minimax/minimax-m3.1-flash`: **`AVAILABLE`** (1757ms) — Probe succeeded with non-empty response.
- `deepseek/deepseek-v4.1-flash-1017`: **`AVAILABLE`** (1663ms) — Probe succeeded with non-empty response.
- `elorian/glimpse`: **`AVAILABLE`** (1167ms) — Probe succeeded with non-empty response.
- `xingchen-agi/xing4.0-29b-a4b:free`: **`RATE_LIMITED`** (2742ms) — Rate limited (429): Provider 'openrouter' rate limited the request.

### Provider: `nvidia_nim` (NVIDIA NIM)
* **Base URL:** `https://integrate.api.nvidia.com/v1`
* **Configured:** Yes

#### Static Catalog Verification
| Model ID | Probe Status | Latency | Reason |
|---|---|---|---|
| `meta/llama-3.3-70b-instruct` | **`NOT_FOUND`** | 472ms | Probe rejected: Request rejected by 'nvidia_nim': The model 'meta/llama-3.3-70b- |
| `meta/llama-3.1-8b-instruct` | **`NOT_FOUND`** | 504ms | Probe rejected: Request rejected by 'nvidia_nim': The model 'meta/llama-3.1-8b-i |
| `nvidia/llama-3.1-nemotron-nano-8b-v1` | **`NOT_FOUND`** | 589ms | Probe rejected: Request rejected by 'nvidia_nim': The model 'nvidia/llama-3.1-ne |
| `openai/gpt-oss-120b` | **`NOT_FOUND`** | 991ms | Probe rejected: Request rejected by 'nvidia_nim': The model 'openai/gpt-oss-120b |
| `qwen/qwen3-next-80b-a3b-instruct` | **`NOT_FOUND`** | 796ms | Probe rejected: Request rejected by 'nvidia_nim': The model 'qwen/qwen3-next-80b |

#### Live Discovered Text-Generation Candidates (74 total)
- `01-ai/yi-large`: **`NOT_FOUND`** (885ms) — Model not found or retired (404): Model or endpoint not found on 'nvidia_nim': F
- `adept/fuyu-8b`: **`NOT_FOUND`** (798ms) — Model not found or retired (404): Model or endpoint not found on 'nvidia_nim': F
- `ai21labs/jamba-1.5-large-instruct`: **`NOT_FOUND`** (769ms) — Model not found or retired (404): Model or endpoint not found on 'nvidia_nim': F
- `aisingapore/sea-lion-7b-instruct`: **`NOT_FOUND`** (707ms) — Model not found or retired (404): Model or endpoint not found on 'nvidia_nim': F
- `bigcode/starcoder2-15b`: **`NOT_FOUND`** (740ms) — Model not found or retired (404): Model or endpoint not found on 'nvidia_nim': 4
- `databricks/dbrx-instruct`: **`NOT_FOUND`** (660ms) — Model not found or retired (404): Model or endpoint not found on 'nvidia_nim': F

### Provider: `mock` (Deterministic test provider)
* **Base URL:** `local://mock`
* **Configured:** Yes

#### Static Catalog Verification
| Model ID | Probe Status | Latency | Reason |
|---|---|---|---|

#### Live Discovered Text-Generation Candidates (18 total)
- `mock-extractive`: **`AVAILABLE`** (12ms) — Probe succeeded with non-empty response.
- `mock-empty`: **`EMPTY_RESPONSE`** (0ms) — Probe returned empty completion.
- `mock-timeout`: **`TIMEOUT`** (13ms) — Probe timed out: Deterministic test provider simulated a timeout.
- `mock-error`: **`UPSTREAM_ERROR`** (16ms) — Upstream error (503): Deterministic test provider simulated an upstream failure.
- `mock-verbose`: **`AVAILABLE`** (16ms) — Probe succeeded with non-empty response.
- `mock-hallucinate`: **`AVAILABLE`** (16ms) — Probe succeeded with non-empty response.

---

## Honest Audit Caveats & Methodology

1. **Point-in-Time Snapshot:** Model availability and quotas change dynamically. An `AVAILABLE` verdict confirms that a model answered a minimal probe request at the time of the audit.
2. **Probe Scope:** A successful trivial probe (`max_tokens=8`, `temperature=0`) proves connectivity, authentication, and serving entitlement. It does not guarantee capability on complex long-context tasks.
3. **Free-Tier Volatility:** Rate limits (`RATE_LIMITED`) and monthly allowances (`NOT_ENTITLED`) are account-specific and may vary over time.
4. **Listings are Not Proof:** Providers frequently list models that are not actively provisioned by backend inference clusters (as observed on Hugging Face Inference Providers). Only empirical probes establish true availability.