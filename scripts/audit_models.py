"""Model Availability Audit Script.

Discovers models from all configured providers, executes verification probes,
compares against static catalog entries, and generates `docs/model-audit-report.md`.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from pathlib import Path
import sys

# Ensure backend directory is in python path
backend_dir = Path(__file__).resolve().parent.parent / "backend"
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

from app.db.init_db import init_db
from app.db.session import SessionLocal
from app.providers.catalog import _CATALOG
from app.providers.registry import all_providers, is_provider_registered
from app.services.audit_service import AuditService


async def generate_audit_report() -> Path:
    init_db()
    report_path = Path(__file__).resolve().parent.parent / "docs" / "model-audit-report.md"
    report_path.parent.mkdir(parents=True, exist_ok=True)

    lines: list[str] = [
        "# Model Availability Audit Report",
        "",
        f"**Generated:** {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}",
        "**Auditor:** LLM-EvalHub Live Model Availability Prober",
        "",
        "---",
        "",
        "## Executive Summary",
        "",
        "This report audits the static catalog entries (`app/providers/catalog.py`) against live "
        "provider model listings and empirical verification probes (cheap text-generation probes with `max_tokens=8`, "
        "`temperature=0`).",
        "",
    ]

    with SessionLocal() as db:
        service = AuditService(db)
        providers = all_providers()

        catalog_dead_models: list[dict[str, str]] = []
        available_missing_from_catalog: list[dict[str, str]] = []
        provider_audit_blocks: list[str] = []

        for p in providers:
            p_key = p.key
            if p_key in ("ollama", "mock") and not p.is_configured:
                continue

            provider_audit_blocks.append(f"### Provider: `{p_key}` ({p.display_name})")
            if not p.is_configured:
                provider_audit_blocks.append("* **Status:** NOT CONFIGURED (No API key in environment)")
                provider_audit_blocks.append("")
                continue

            provider_audit_blocks.append(f"* **Base URL:** `{p.base_url}`")
            provider_audit_blocks.append(f"* **Configured:** Yes")

            # 1. Probe static catalog models for this provider
            static_entries = _CATALOG.get(p_key, [])
            provider_audit_blocks.append("")
            provider_audit_blocks.append("#### Static Catalog Verification")
            provider_audit_blocks.append("| Model ID | Probe Status | Latency | Reason |")
            provider_audit_blocks.append("|---|---|---|---|")

            static_ids = set()
            for mid, desc in static_entries:
                static_ids.add(mid)
                status, reason, lat, _ = await service.probe_model(p, mid)
                lat_str = f"{lat:.0f}ms" if lat else "—"
                short_reason = reason.replace("|", "/")[:80]
                provider_audit_blocks.append(f"| `{mid}` | **`{status}`** | {lat_str} | {short_reason} |")

                if status != "AVAILABLE":
                    catalog_dead_models.append({
                        "provider": p_key,
                        "model_id": mid,
                        "status": status,
                        "reason": reason,
                    })

            # 2. Discover live models
            try:
                discovered = await p.discover_models()
                provider_audit_blocks.append("")
                provider_audit_blocks.append(f"#### Live Discovered Text-Generation Candidates ({len(discovered)} total)")
                # Probe first 5 discovered
                probed_count = 0
                for cand in discovered[:6]:
                    status, reason, lat, _ = await service.probe_model(p, cand.id)
                    lat_str = f"{lat:.0f}ms" if lat else "—"
                    short_reason = reason.replace("|", "/")[:80]
                    provider_audit_blocks.append(f"- `{cand.id}`: **`{status}`** ({lat_str}) — {short_reason}")
                    probed_count += 1

                    if status == "AVAILABLE" and cand.id not in static_ids:
                        available_missing_from_catalog.append({
                            "provider": p_key,
                            "model_id": cand.id,
                            "latency_ms": f"{lat:.0f}ms" if lat else "—",
                        })

            except Exception as exc:
                provider_audit_blocks.append(f"*Discovery Error:* `{exc}`")

            provider_audit_blocks.append("")

        # Section: Dead Models in Static Catalog
        lines.append("## 1. Dead or Unavailable Models in Static Catalog")
        lines.append("")
        if catalog_dead_models:
            lines.append("The following models exist in `_CATALOG` but failed live verification probes (retired, renamed, 404, or plan restricted):")
            lines.append("")
            lines.append("| Provider | Model ID | Status | Reason |")
            lines.append("|---|---|---|---|")
            for item in catalog_dead_models:
                reason = item["reason"].replace("|", "/")[:100]
                lines.append(f"| `{item['provider']}` | `{item['model_id']}` | **`{item['status']}`** | {reason} |")
        else:
            lines.append("No dead catalog models detected.")
        lines.append("")

        # Section: Available Models Missing from Catalog
        lines.append("## 2. Available Models Missing from Static Catalog")
        lines.append("")
        if available_missing_from_catalog:
            lines.append("The following models were discovered live and confirmed **AVAILABLE** via probes, but are absent from the static catalog:")
            lines.append("")
            lines.append("| Provider | Model ID | Latency |")
            lines.append("|---|---|---|")
            for item in available_missing_from_catalog:
                lines.append(f"| `{item['provider']}` | `{item['model_id']}` | {item['latency_ms']} |")
        else:
            lines.append("None detected.")
        lines.append("")

        # Section: Provider Breakdown
        lines.append("## 3. Detailed Provider Audit Results")
        lines.append("")
        lines.extend(provider_audit_blocks)

        # Section: Honest Limitations
        lines.append("---")
        lines.append("")
        lines.append("## Honest Audit Caveats & Methodology")
        lines.append("")
        lines.append("1. **Point-in-Time Snapshot:** Model availability and quotas change dynamically. An `AVAILABLE` verdict confirms that a model answered a minimal probe request at the time of the audit.")
        lines.append("2. **Probe Scope:** A successful trivial probe (`max_tokens=8`, `temperature=0`) proves connectivity, authentication, and serving entitlement. It does not guarantee capability on complex long-context tasks.")
        lines.append("3. **Free-Tier Volatility:** Rate limits (`RATE_LIMITED`) and monthly allowances (`NOT_ENTITLED`) are account-specific and may vary over time.")
        lines.append("4. **Listings are Not Proof:** Providers frequently list models that are not actively provisioned by backend inference clusters (as observed on Hugging Face Inference Providers). Only empirical probes establish true availability.")

    report_content = "\n".join(lines)
    report_path.write_text(report_content, encoding="utf-8")
    print(f"Audit report generated at: {report_path}")
    return report_path


if __name__ == "__main__":
    asyncio.run(generate_audit_report())
