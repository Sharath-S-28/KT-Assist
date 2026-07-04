"""
scripts/seed_demo_kai_cache.py — demo-mode branch only.

Authors KAI extraction + relationship-discovery mock responses grounded
in the real KCTA_KT_Transcript_PBI_Dashboards.docx transcript, keyed by
the exact content_hash/chunk_index the real pipeline computes, so the
live app (DEV_MODE + cache) reproduces this exact graph on every run
without any live Claude API call.

Object IDs are explicit (not left to KAIAgent's uuid4 setdefault) so
they stay stable across every future run/reprocess, which relationship
discovery's cache_key (content_hash:relationships) then references.

Boundary-check pass is intentionally left uncached: arbitrate_objects()
defaults any object with no verdict to "confirm" (see
services/agents/kai_relationship_discovery.py), so every authored
object survives arbitration with zero extra mock authoring needed.
"""

import json
from pathlib import Path

from services.core.asset_ingestion import compute_content_hash

TRANSCRIPT_PATH = Path("KCTA_KT_Transcript_PBI_Dashboards.docx")
CONTENT_HASH = compute_content_hash(TRANSCRIPT_PATH.read_bytes())
KAI_CACHE_DIR = Path("data/cache/kai")

# ---------------------------------------------------------------------------
# Objects, grouped by the chunk they were actually extracted from (verified
# against chunk_text()'s real 9-chunk boundaries for this exact file).
# ---------------------------------------------------------------------------

OBJECTS_BY_CHUNK: list[list[dict]] = [
    # chunk 0 — session opening + Dashboard 1 (Revenue) overview/SLA
    [
        {"id": "proc-revenue", "object_type": "Process", "name": "Weekly Revenue Dashboard Refresh & Publish",
         "description": "Weekly refresh and publish of the Revenue Power BI dashboard for CFO/Finance leadership. Most time-sensitive of the three dashboards.",
         "criticality": "Critical", "confidence": 0.97},
        {"id": "rule-rev-sla", "object_type": "Business Rule", "name": "Revenue Refresh SLA",
         "description": "Source data must be available by 8 AM Monday; the report must be published by 10 AM Monday.",
         "criticality": "Critical", "confidence": 0.95},
        {"id": "sys-sap-bw", "object_type": "System", "name": "SAP BW",
         "description": "Source system for the Revenue dashboard; Finance runs a Sunday-night extraction job producing an Excel export.",
         "criticality": "Critical", "confidence": 0.9},
    ],
    # chunk 1 — download/storage, validation, contact for SAP issues
    [
        {"id": "dep-rev-path", "object_type": "Dependency", "name": "Hardcoded Revenue File Path",
         "description": r"Revenue Power BI file is hardcoded to D:\Data\PBI_Refresh\Revenue\Raw\; must be remapped or copied to that exact path on any other machine.",
         "criticality": "Critical", "confidence": 0.92},
        {"id": "task-rev-source", "object_type": "Task", "name": "Retrieve & Place Revenue Extract",
         "description": "Download the Revenue_Weekly_YYYYMMDD.xlsx export from the Finance SharePoint site (Documents/Reports/Weekly Revenue Raw) and place it at the hardcoded local path without opening/resaving it.",
         "criticality": "Critical", "confidence": 0.9},
        {"id": "rule-rev-rowcount", "object_type": "Business Rule", "name": "Revenue Row Count Expected Range",
         "description": "Expected row count is ~2,000-2,500; below 1,500 or above 3,000 signals a likely SAP extraction problem.",
         "criticality": "Important", "confidence": 0.88},
        {"id": "task-rev-validate", "object_type": "Task", "name": "Validate Revenue Extract Data Quality",
         "description": "Check row count against expected range, confirm no blanks in the Net Revenue column (F), and confirm the date column (B) only contains current-week dates.",
         "criticality": "Critical", "confidence": 0.9},
        {"id": "esc-sap-issues", "object_type": "Escalation", "name": "SAP Extraction Issue Contact",
         "description": "Historically escalated to Suresh in Finance, who handles SAP extractions. Outgoing owner is not sure Suresh remains the right contact after handover.",
         "criticality": "Important", "confidence": 0.75},
        {"id": "risk-hardcoded-paths", "object_type": "Risk", "name": "Hardcoded Local File Path Fragility",
         "description": "All three dashboards depend on hardcoded local file paths; working from a different machine breaks refresh unless the path is manually remapped or replicated.",
         "criticality": "Important", "confidence": 0.85},
    ],
    # chunk 2 — region mapping, PBI refresh & publish
    [
        {"id": "task-rev-region", "object_type": "Task", "name": "Map Region Bucket via VLOOKUP",
         "description": "Add a Region Group column via VLOOKUP(H2, Region_Lookup!A:B, 2, FALSE) against the Region_Lookup tab; unmapped region codes must be added manually and reported to Finance.",
         "criticality": "Important", "confidence": 0.88},
        {"id": "dep-region-lookup", "object_type": "Dependency", "name": "Region_Lookup Tab",
         "description": "In-workbook lookup tab mapping SAP region codes to region groups; can go stale when SAP adds new region codes.",
         "criticality": "Important", "confidence": 0.85},
        {"id": "sys-pbi-desktop", "object_type": "System", "name": "Power BI Desktop",
         "description": "Used to open the .pbix file, verify/refresh the data source path, and publish to the Power BI Service.",
         "criticality": "Critical", "confidence": 0.92},
        {"id": "sys-pbi-service", "object_type": "System", "name": "Power BI Service",
         "description": "Hosted workspace destination all three dashboards are published to (e.g. Finance Analytics Workspace for Revenue).",
         "criticality": "Critical", "confidence": 0.9},
        {"id": "task-rev-refresh", "object_type": "Task", "name": "Refresh & Publish Revenue Dashboard",
         "description": "Verify the data source path in Transform Data/Data Source Settings, Close & Apply, Refresh (~3-5 min; investigate if over 10), then Publish to the Finance Analytics Workspace.",
         "criticality": "Critical", "confidence": 0.9},
    ],
    # chunk 3 — notification, Dashboard 2 (Returns) overview, data source
    [
        {"id": "task-rev-notify", "object_type": "Task", "name": "Notify #finance-reporting Channel",
         "description": "Informal Teams message to #finance-reporting confirming the weekly revenue report has been updated.",
         "criticality": "Supporting", "confidence": 0.8},
        {"id": "proc-returns", "object_type": "Process", "name": "Customer Returns Dashboard Refresh & Publish",
         "description": "Bi-weekly refresh/publish of the Ops-owned Customer Returns dashboard; original report builder (Marcus) has already left the company.",
         "criticality": "Important", "confidence": 0.9},
        {"id": "esc-returns-report-owner", "object_type": "Escalation", "name": "Returns Report Design Issue Contact",
         "description": "Original report author (Marcus) no longer at the company; outgoing owner believes someone on the Ops team ('maybe Deepa', last name unknown) could help with report-design issues.",
         "criticality": "Important", "confidence": 0.55},
        {"id": "sys-salesforce", "object_type": "System", "name": "Salesforce CRM",
         "description": "Source system for Returns data; a CRM team member (Anita) runs a report and emails it to a distribution list.",
         "criticality": "Important", "confidence": 0.85},
        {"id": "esc-crm-distribution", "object_type": "Escalation", "name": "CRM Distribution List Access",
         "description": "New owner must be added to the distribution list that receives the Salesforce returns export; the exact list name is unknown and must be obtained from IT or Anita directly.",
         "criticality": "Supporting", "confidence": 0.5},
        {"id": "task-ret-source", "object_type": "Task", "name": "Retrieve Salesforce Returns CSV Export",
         "description": "Receive Returns_Data_MMYYYY.csv, emailed by Anita from Salesforce, typically the Friday before the Monday refresh.",
         "criticality": "Important", "confidence": 0.85},
        {"id": "dep-ret-path", "object_type": "Dependency", "name": "Hardcoded Returns File Path",
         "description": r"Returns Power BI file is hardcoded to D:\Data\PBI_Refresh\Returns\Raw\, same limitation as Revenue.",
         "criticality": "Important", "confidence": 0.85},
    ],
    # chunk 4 — Returns validation/manual steps/workspace, Dashboard 3 overview
    [
        {"id": "rule-ret-rowcount", "object_type": "Business Rule", "name": "Returns Row Count Informal Range",
         "description": "No formal check, but typically 400-600 rows per bi-weekly period; flag if empty or under ~50.",
         "criticality": "Supporting", "confidence": 0.7},
        {"id": "task-ret-validate", "object_type": "Task", "name": "Validate Returns Data Date Range",
         "description": "Confirm the Return Date column (A) falls within the expected bi-weekly window.",
         "criticality": "Important", "confidence": 0.8},
        {"id": "task-ret-standardize", "object_type": "Task", "name": "Standardize Return Reason Values",
         "description": "Manual find-and-replace to normalize inconsistent CRM export values (e.g. 'Product Defect' -> 'Defective'); no lookup table exists for this, unlike Revenue's region mapping.",
         "criticality": "Important", "confidence": 0.8},
        {"id": "risk-manual-standardization", "object_type": "Risk", "name": "Manual Standardization Error Risk",
         "description": "Return Reason standardization relies on a manual, undocumented substitution list rather than a lookup table, making it error-prone and hard to hand off.",
         "criticality": "Supporting", "confidence": 0.75},
        {"id": "task-ret-refresh", "object_type": "Task", "name": "Refresh & Publish Returns Dashboard",
         "description": "Refresh Returns_Dashboard.pbix and publish; destination workspace believed to be 'Ops Analytics Workspace' but not confirmed by the outgoing owner.",
         "criticality": "Important", "confidence": 0.75},
        {"id": "ki-returns-workspace-uncertain", "object_type": "Known Issue", "name": "Returns Workspace Name Unconfirmed",
         "description": "Outgoing owner was not certain of the exact Power BI Service workspace name for the Returns dashboard and said he would confirm later.",
         "criticality": "Supporting", "confidence": 0.6},
        {"id": "proc-inventory", "object_type": "Process", "name": "Inventory Aging Report Refresh & Distribution",
         "description": "Monthly refresh/publish/distribution of the Inventory Aging report for the Supply Chain Director and warehouse managers.",
         "criticality": "Important", "confidence": 0.9},
    ],
    # chunk 5 — Inventory data source/storage/validation
    [
        {"id": "sys-sap-mm", "object_type": "System", "name": "SAP MM Module",
         "description": "Materials-management module of SAP; source system for the Inventory Aging extract, output as a pipe-delimited TXT file at month end.",
         "criticality": "Important", "confidence": 0.85},
        {"id": "dep-inv-path", "object_type": "Dependency", "name": "Hardcoded Inventory File Path",
         "description": r"Inventory Power BI file is hardcoded to D:\Data\PBI_Refresh\Inventory\Raw\, same limitation as Revenue/Returns.",
         "criticality": "Important", "confidence": 0.85},
        {"id": "task-inv-source", "object_type": "Task", "name": "Retrieve SAP MM Inventory Extract",
         "description": "Receive the pipe-delimited Inventory_Aging_MMMYYYY.txt file, auto-emailed by the ERP team; exact recipient email address to be confirmed with Vijay.",
         "criticality": "Important", "confidence": 0.8},
        {"id": "task-inv-import", "object_type": "Task", "name": "Import Pipe-Delimited Inventory File",
         "description": "Must use Excel's Import function (not double-click-open) or the pipe-delimited data collapses into a single column.",
         "criticality": "Important", "confidence": 0.85},
        {"id": "rule-inv-aging-cols", "object_type": "Business Rule", "name": "Four Aging Bucket Columns Required",
         "description": "The dashboard requires exactly four aging columns in order (0-30, 31-60, 61-90, 90-plus); missing any one causes a PBI error.",
         "criticality": "Important", "confidence": 0.85},
        {"id": "ki-missing-90plus-col", "object_type": "Known Issue", "name": "ERP Extract Sometimes Omits 90-Plus Column",
         "description": "The SAP MM extraction occasionally drops the 90-plus aging column entirely when there is no data in it; must be added back manually as an empty column.",
         "criticality": "Supporting", "confidence": 0.8},
        {"id": "ki-no-crosscheck-formula", "object_type": "Known Issue", "name": "No Formal Quantity Cross-Check Formula",
         "description": "Total quantity is meant to roughly match the Supply Chain report but there is no documented cross-check formula; previously done by eye, flagging if off by more than 10-15%.",
         "criticality": "Supporting", "confidence": 0.7},
        {"id": "esc-erp-extraction", "object_type": "Escalation", "name": "ERP Extraction Issue Contact",
         "description": "ERP/SAP MM extraction issues are escalated to Vijay.",
         "criticality": "Supporting", "confidence": 0.75},
    ],
    # chunk 6 — Inventory manual steps, distribution, PBI version dependency
    [
        {"id": "task-inv-costvalue", "object_type": "Task", "name": "Add Cost Value Column",
         "description": "Multiply Quantity by Unit Cost, where Unit Cost is looked up from Item_Master.xlsx (maintained by the Costing team on SharePoint), not present in the ERP extract itself.",
         "criticality": "Important", "confidence": 0.8},
        {"id": "dep-item-master", "object_type": "Dependency", "name": "Item_Master.xlsx",
         "description": "Costing-team-maintained SharePoint file providing per-item Unit Cost, required to compute the Inventory dashboard's Cost Value column.",
         "criticality": "Important", "confidence": 0.8},
        {"id": "task-inv-flag", "object_type": "Task", "name": "Add Review Flag Column",
         "description": "IF formula (e.g. =IF(G2>0,\"Yes\",\"No\")) flagging any item with nonzero 90-plus-day aged quantity for review.",
         "criticality": "Important", "confidence": 0.8},
        {"id": "task-inv-refresh", "object_type": "Task", "name": "Refresh & Publish Inventory Dashboard",
         "description": "Refresh Inventory_Aging_Dashboard.pbix and publish to the Supply Chain Analytics workspace.",
         "criticality": "Important", "confidence": 0.8},
        {"id": "task-inv-distribute", "object_type": "Task", "name": "Export & Email Excel to Supply Chain Director",
         "description": "Because the Supply Chain Director (Arjun Mehta) doesn't use Power BI Service, export the main table as Excel and email it directly to him (CC warehouse managers) after publishing.",
         "criticality": "Important", "confidence": 0.85},
        {"id": "dep-pbi-version", "object_type": "Dependency", "name": "Power BI Desktop October 2024+ Requirement",
         "description": "A connector change in this version is required for the Revenue dashboard to refresh correctly; older versions break it.",
         "criticality": "Important", "confidence": 0.85},
        {"id": "sys-sharepoint", "object_type": "System", "name": "SharePoint (Finance Site)",
         "description": "Hosts all three .pbix files (PBI Reports folder), the Revenue raw extract drop folder, and the Item_Master.xlsx costing file; also provides version history for recovery.",
         "criticality": "Critical", "confidence": 0.85},
    ],
    # chunk 7 — common errors/fixes, maintenance windows
    [
        {"id": "ki-credentials-error", "object_type": "Known Issue", "name": "Data Source Credentials Error",
         "description": "Appears when a refresh's underlying Excel/CSV file path has changed or the file isn't in the expected folder.",
         "criticality": "Supporting", "confidence": 0.75},
        {"id": "ki-column-not-found", "object_type": "Known Issue", "name": "Expression Error: Column Not Found (Revenue)",
         "description": "Occurs when the Region Lookup table gains a new column or a SAP-extract column is renamed; fixed manually in Power Query's Transform Data step. No written guide exists for this fix.",
         "criticality": "Important", "confidence": 0.8},
        {"id": "ki-encoding", "object_type": "Known Issue", "name": "Inventory TXT Encoding Issue",
         "description": "Occasionally the pipe-delimited file is ANSI instead of UTF-8, producing garbled characters; must be re-saved as UTF-8 in Notepad.",
         "criticality": "Supporting", "confidence": 0.75},
        {"id": "rule-maintenance-window", "object_type": "Business Rule", "name": "Scheduled Maintenance Windows",
         "description": "Avoid refreshing during the Power BI Service window (Sunday 2-4 AM IST) or SAP's monthly maintenance window (last Saturday, ~10 PM-2 AM), which can affect Inventory data availability.",
         "criticality": "Important", "confidence": 0.8},
    ],
    # chunk 8 — backup/recovery, closing (central "no SOP" gap)
    [
        {"id": "risk-no-backup-schedule", "object_type": "Risk", "name": "No Formal Backup Schedule",
         "description": "Recovery relies entirely on SharePoint's built-in version history; there is no formal, scheduled backup process for any of the three dashboards.",
         "criticality": "Important", "confidence": 0.8},
        {"id": "ki-no-sop", "object_type": "Known Issue", "name": "No Central SOP or Documentation Exists",
         "description": "Explicitly confirmed by the outgoing owner: 'There's nothing written down. This has all been in my head.' No consolidated SOP exists for any of the three dashboards prior to this KT session.",
         "criticality": "Critical", "confidence": 0.95},
        {"id": "risk-single-person-knowledge", "object_type": "Risk", "name": "Single-Person Institutional Knowledge",
         "description": "Refresh procedures, contacts, validation heuristics, and error fixes for all three dashboards existed only in the outgoing owner's head prior to this KT session.",
         "criticality": "Critical", "confidence": 0.9},
    ],
]

RELATIONSHIPS: list[dict] = [
    # HAS_TASK (Process -> Task)
    *[{"id": f"rel-ht-rev-{i}", "relationship_type": "HAS_TASK", "source_id": "proc-revenue", "target_id": t, "confidence": 0.9}
      for i, t in enumerate(["task-rev-source", "task-rev-validate", "task-rev-region", "task-rev-refresh", "task-rev-notify"])],
    *[{"id": f"rel-ht-ret-{i}", "relationship_type": "HAS_TASK", "source_id": "proc-returns", "target_id": t, "confidence": 0.9}
      for i, t in enumerate(["task-ret-source", "task-ret-validate", "task-ret-standardize", "task-ret-refresh"])],
    *[{"id": f"rel-ht-inv-{i}", "relationship_type": "HAS_TASK", "source_id": "proc-inventory", "target_id": t, "confidence": 0.9}
      for i, t in enumerate(["task-inv-source", "task-inv-import", "task-inv-costvalue", "task-inv-flag", "task-inv-refresh", "task-inv-distribute"])],
    # USES_SYSTEM (Task -> System)
    {"id": "rel-us-1", "relationship_type": "USES_SYSTEM", "source_id": "task-rev-source", "target_id": "sys-sap-bw", "confidence": 0.85},
    {"id": "rel-us-2", "relationship_type": "USES_SYSTEM", "source_id": "task-rev-source", "target_id": "sys-sharepoint", "confidence": 0.85},
    {"id": "rel-us-3", "relationship_type": "USES_SYSTEM", "source_id": "task-rev-refresh", "target_id": "sys-pbi-desktop", "confidence": 0.9},
    {"id": "rel-us-4", "relationship_type": "USES_SYSTEM", "source_id": "task-rev-refresh", "target_id": "sys-pbi-service", "confidence": 0.9},
    {"id": "rel-us-5", "relationship_type": "USES_SYSTEM", "source_id": "task-ret-source", "target_id": "sys-salesforce", "confidence": 0.85},
    {"id": "rel-us-6", "relationship_type": "USES_SYSTEM", "source_id": "task-ret-refresh", "target_id": "sys-pbi-desktop", "confidence": 0.85},
    {"id": "rel-us-7", "relationship_type": "USES_SYSTEM", "source_id": "task-ret-refresh", "target_id": "sys-pbi-service", "confidence": 0.85},
    {"id": "rel-us-8", "relationship_type": "USES_SYSTEM", "source_id": "task-inv-source", "target_id": "sys-sap-mm", "confidence": 0.85},
    {"id": "rel-us-9", "relationship_type": "USES_SYSTEM", "source_id": "task-inv-refresh", "target_id": "sys-pbi-desktop", "confidence": 0.85},
    {"id": "rel-us-10", "relationship_type": "USES_SYSTEM", "source_id": "task-inv-refresh", "target_id": "sys-pbi-service", "confidence": 0.85},
    {"id": "rel-us-11", "relationship_type": "USES_SYSTEM", "source_id": "task-inv-costvalue", "target_id": "sys-sharepoint", "confidence": 0.75},
    # DEPENDS_ON (Task -> Dependency)
    {"id": "rel-do-1", "relationship_type": "DEPENDS_ON", "source_id": "task-rev-source", "target_id": "dep-rev-path", "confidence": 0.9},
    {"id": "rel-do-2", "relationship_type": "DEPENDS_ON", "source_id": "task-rev-region", "target_id": "dep-region-lookup", "confidence": 0.88},
    {"id": "rel-do-3", "relationship_type": "DEPENDS_ON", "source_id": "task-ret-source", "target_id": "dep-ret-path", "confidence": 0.85},
    {"id": "rel-do-4", "relationship_type": "DEPENDS_ON", "source_id": "task-inv-source", "target_id": "dep-inv-path", "confidence": 0.85},
    {"id": "rel-do-5", "relationship_type": "DEPENDS_ON", "source_id": "task-inv-costvalue", "target_id": "dep-item-master", "confidence": 0.85},
    {"id": "rel-do-6", "relationship_type": "DEPENDS_ON", "source_id": "task-rev-refresh", "target_id": "dep-pbi-version", "confidence": 0.8},
    {"id": "rel-do-7", "relationship_type": "DEPENDS_ON", "source_id": "task-ret-refresh", "target_id": "dep-pbi-version", "confidence": 0.75},
    {"id": "rel-do-8", "relationship_type": "DEPENDS_ON", "source_id": "task-inv-refresh", "target_id": "dep-pbi-version", "confidence": 0.75},
    # GOVERNED_BY (Task -> Business Rule)
    {"id": "rel-gb-1", "relationship_type": "GOVERNED_BY", "source_id": "task-rev-refresh", "target_id": "rule-rev-sla", "confidence": 0.9},
    {"id": "rel-gb-2", "relationship_type": "GOVERNED_BY", "source_id": "task-rev-validate", "target_id": "rule-rev-rowcount", "confidence": 0.88},
    {"id": "rel-gb-3", "relationship_type": "GOVERNED_BY", "source_id": "task-ret-validate", "target_id": "rule-ret-rowcount", "confidence": 0.75},
    {"id": "rel-gb-4", "relationship_type": "GOVERNED_BY", "source_id": "task-inv-import", "target_id": "rule-inv-aging-cols", "confidence": 0.85},
    {"id": "rel-gb-5", "relationship_type": "GOVERNED_BY", "source_id": "task-rev-refresh", "target_id": "rule-maintenance-window", "confidence": 0.75},
    {"id": "rel-gb-6", "relationship_type": "GOVERNED_BY", "source_id": "task-ret-refresh", "target_id": "rule-maintenance-window", "confidence": 0.7},
    {"id": "rel-gb-7", "relationship_type": "GOVERNED_BY", "source_id": "task-inv-refresh", "target_id": "rule-maintenance-window", "confidence": 0.75},
    # HAS_RISK (Task -> Risk)
    {"id": "rel-hr-1", "relationship_type": "HAS_RISK", "source_id": "task-rev-source", "target_id": "risk-hardcoded-paths", "confidence": 0.85},
    {"id": "rel-hr-2", "relationship_type": "HAS_RISK", "source_id": "task-ret-standardize", "target_id": "risk-manual-standardization", "confidence": 0.8},
    {"id": "rel-hr-3", "relationship_type": "HAS_RISK", "source_id": "task-inv-refresh", "target_id": "risk-no-backup-schedule", "confidence": 0.75},
    {"id": "rel-hr-4", "relationship_type": "HAS_RISK", "source_id": "task-rev-validate", "target_id": "risk-single-person-knowledge", "confidence": 0.8},
    # MITIGATED_BY (Risk -> Control) -- intentionally none yet: no Control
    # object exists in the initial extraction (withheld for gap closure).
    # ESCALATES_TO (Task -> Escalation)
    {"id": "rel-et-1", "relationship_type": "ESCALATES_TO", "source_id": "task-rev-validate", "target_id": "esc-sap-issues", "confidence": 0.8},
    {"id": "rel-et-2", "relationship_type": "ESCALATES_TO", "source_id": "task-ret-validate", "target_id": "esc-returns-report-owner", "confidence": 0.6},
    {"id": "rel-et-3", "relationship_type": "ESCALATES_TO", "source_id": "task-ret-source", "target_id": "esc-crm-distribution", "confidence": 0.6},
    {"id": "rel-et-4", "relationship_type": "ESCALATES_TO", "source_id": "task-inv-source", "target_id": "esc-erp-extraction", "confidence": 0.75},
    # HAS_KNOWN_ISSUE (Task -> Known Issue)
    {"id": "rel-hki-1", "relationship_type": "HAS_KNOWN_ISSUE", "source_id": "task-rev-refresh", "target_id": "ki-column-not-found", "confidence": 0.8},
    {"id": "rel-hki-2", "relationship_type": "HAS_KNOWN_ISSUE", "source_id": "task-rev-refresh", "target_id": "ki-credentials-error", "confidence": 0.7},
    {"id": "rel-hki-3", "relationship_type": "HAS_KNOWN_ISSUE", "source_id": "task-inv-import", "target_id": "ki-encoding", "confidence": 0.75},
    {"id": "rel-hki-4", "relationship_type": "HAS_KNOWN_ISSUE", "source_id": "task-inv-import", "target_id": "ki-missing-90plus-col", "confidence": 0.8},
    {"id": "rel-hki-5", "relationship_type": "HAS_KNOWN_ISSUE", "source_id": "task-inv-refresh", "target_id": "ki-no-crosscheck-formula", "confidence": 0.7},
    {"id": "rel-hki-6", "relationship_type": "HAS_KNOWN_ISSUE", "source_id": "task-ret-refresh", "target_id": "ki-returns-workspace-uncertain", "confidence": 0.65},
    {"id": "rel-hki-7", "relationship_type": "HAS_KNOWN_ISSUE", "source_id": "task-rev-refresh", "target_id": "ki-no-sop", "confidence": 0.9},
]


def _sanitized_cache_path(cache_dir: Path, cache_key: str) -> Path:
    cache_dir.mkdir(parents=True, exist_ok=True)
    safe_key = cache_key.replace(":", "-")
    return cache_dir / f"{safe_key}.json"


def main() -> None:
    total_objects = 0
    for chunk_index, objects in enumerate(OBJECTS_BY_CHUNK):
        cache_key = f"{CONTENT_HASH}:{chunk_index}"
        path = _sanitized_cache_path(KAI_CACHE_DIR, cache_key)
        path.write_text(json.dumps({"objects": objects}, indent=2))
        total_objects += len(objects)
        print(f"chunk {chunk_index}: {len(objects)} objects -> {path}")

    rel_cache_key = f"{CONTENT_HASH}:relationships"
    rel_path = _sanitized_cache_path(KAI_CACHE_DIR, rel_cache_key)
    rel_path.write_text(json.dumps({"relationships": RELATIONSHIPS}, indent=2))
    print(f"relationships: {len(RELATIONSHIPS)} -> {rel_path}")
    print(f"content_hash: {CONTENT_HASH}")
    print(f"total objects: {total_objects}")


if __name__ == "__main__":
    main()
