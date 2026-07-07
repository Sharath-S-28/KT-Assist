"""
services/demo/hierarchical_kai_attributes.py — demo-mode only.

Pilot-profile (PILOT_PROFILE: System / Known Issue / Task) structured
attribute overlay for the demo's KCTA_KT_Transcript_PBI_Dashboards.docx
graph. Every value below is derived directly from the corresponding
object's own already-authored description in
scripts/seed_demo_kai_cache.py -- this is a restructuring of
already-established, transcript-grounded content into the pilot
ontology's {attribute_name: value} shape, not new invented knowledge.

Deliberately NOT populated here (left NOT_OBSERVED by omission, the
KAI extractor's own default for anything a chunk never addressed):
  - System.workspace (conditional; only applies if system_type ==
    'BI_PLATFORM', never set, so the condition never includes it as a
    required member anyway -- omitted for that reason, not withheld).
  - Known Issue.escalation_condition (conditional; requires_escalation
    is never set either, same reasoning).
  - validation_status / evidence_refs on every Known Issue: these are
    NOT profile attribute_requirements at all -- they are the separate
    Wave-5 evidence/validation fields (schemas/knowledge_graph.py),
    intentionally left at their KAI-extraction default ("Unvalidated",
    []) so the Level-5 VALIDATION_GAP detector has real, undoctored
    work to do. This is the ONE deliberately-withheld dimension in this
    fixture, closed later via services/demo/hierarchical_gap_answers.py
    -- mirroring the same "withhold one real thing, close it for real"
    principle scripts/seed_demo_stage2_close_gap.py already established
    for the legacy Control gap.

Every mandatory attribute for every System/Known Issue/Task IS
populated (state=PRESENT), so TC/AC/RC/OS all measure 1.0 at initial
hierarchical validation -- the only dimension starting below 1.0 is EV
(evidence), driven entirely by the withheld validation_status/
evidence_refs above.

Raw shape matches services.agents.kai_extraction._parse_pilot_attributes'
expected per-attribute dict: {"proposed_state": "PRESENT", "value": str,
"source_reference": str}. source_reference is a short human-readable
pointer back to the source object/session, not a page/line citation
(none exists in this docx-derived fixture).
"""

# -- Systems (mandatory: system_name, purpose, access_path) ------------------

SYSTEM_ATTRIBUTES: dict[str, dict[str, dict]] = {
    "sys-sap-bw": {
        "system_name": {"proposed_state": "PRESENT", "value": "SAP BW",
                         "source_reference": "KCTA transcript: Revenue dashboard source system"},
        "purpose": {"proposed_state": "PRESENT",
                    "value": "Source system for the Revenue dashboard; Finance runs a Sunday-night extraction job producing an Excel export.",
                    "source_reference": "KCTA transcript: Revenue dashboard source system"},
        "access_path": {"proposed_state": "PRESENT",
                         "value": "Sunday-night SAP BW extraction job output is retrieved from the Finance SharePoint site (Documents/Reports/Weekly Revenue Raw).",
                         "source_reference": "KCTA transcript: Retrieve & Place Revenue Extract"},
    },
    "sys-pbi-desktop": {
        "system_name": {"proposed_state": "PRESENT", "value": "Power BI Desktop",
                         "source_reference": "KCTA transcript: Region mapping / PBI refresh & publish"},
        "purpose": {"proposed_state": "PRESENT",
                    "value": "Used to open each dashboard's .pbix file, verify/refresh the data source path, and publish to the Power BI Service.",
                    "source_reference": "KCTA transcript: Region mapping / PBI refresh & publish"},
        "access_path": {"proposed_state": "PRESENT",
                         "value": "Opens the relevant .pbix file from SharePoint's PBI Reports folder; requires the October 2024+ Desktop version for the Revenue connector to work.",
                         "source_reference": "KCTA transcript: PBI version dependency / SharePoint hosting"},
    },
    "sys-pbi-service": {
        "system_name": {"proposed_state": "PRESENT", "value": "Power BI Service",
                         "source_reference": "KCTA transcript: Region mapping / PBI refresh & publish"},
        "purpose": {"proposed_state": "PRESENT",
                    "value": "Hosted workspace destination all three dashboards are published to (e.g. Finance Analytics Workspace for Revenue).",
                    "source_reference": "KCTA transcript: Region mapping / PBI refresh & publish"},
        "access_path": {"proposed_state": "PRESENT",
                         "value": "Reached by publishing from Power BI Desktop into the dashboard's named workspace (e.g. Finance Analytics Workspace, Supply Chain Analytics workspace).",
                         "source_reference": "KCTA transcript: Refresh & Publish tasks"},
    },
    "sys-salesforce": {
        "system_name": {"proposed_state": "PRESENT", "value": "Salesforce CRM",
                         "source_reference": "KCTA transcript: Returns dashboard data source"},
        "purpose": {"proposed_state": "PRESENT",
                    "value": "Source system for Returns data; a CRM team member (Anita) runs a report and emails it to a distribution list.",
                    "source_reference": "KCTA transcript: Returns dashboard data source"},
        "access_path": {"proposed_state": "PRESENT",
                         "value": "Accessed by Anita in the CRM team, who runs the Salesforce report and emails Returns_Data_MMYYYY.csv to the distribution list.",
                         "source_reference": "KCTA transcript: Retrieve Salesforce Returns CSV Export"},
    },
    "sys-sap-mm": {
        "system_name": {"proposed_state": "PRESENT", "value": "SAP MM Module",
                         "source_reference": "KCTA transcript: Inventory dashboard data source"},
        "purpose": {"proposed_state": "PRESENT",
                    "value": "Materials-management module of SAP; source system for the Inventory Aging extract, output as a pipe-delimited TXT file at month end.",
                    "source_reference": "KCTA transcript: Inventory dashboard data source"},
        "access_path": {"proposed_state": "PRESENT",
                         "value": "Month-end pipe-delimited extract is auto-emailed by the ERP team; Vijay is the contact for extraction issues.",
                         "source_reference": "KCTA transcript: Retrieve SAP MM Inventory Extract"},
    },
    "sys-sharepoint": {
        "system_name": {"proposed_state": "PRESENT", "value": "SharePoint (Finance Site)",
                         "source_reference": "KCTA transcript: Inventory manual steps / distribution"},
        "purpose": {"proposed_state": "PRESENT",
                    "value": "Hosts all three .pbix files (PBI Reports folder), the Revenue raw extract drop folder, and the Item_Master.xlsx costing file; also provides version history for recovery.",
                    "source_reference": "KCTA transcript: Inventory manual steps / distribution"},
        "access_path": {"proposed_state": "PRESENT",
                         "value": "Finance Site document libraries (PBI Reports folder, Revenue raw extract drop folder, Item_Master.xlsx); recovery via right-click Version History.",
                         "source_reference": "KCTA transcript: Backup/recovery, closing"},
    },
}

# -- Known Issues (mandatory: trigger, impact, detection_method,
#    resolution_path unless self_resolving) -----------------------------------

KNOWN_ISSUE_ATTRIBUTES: dict[str, dict[str, dict]] = {
    "ki-credentials-error": {
        "trigger": {"proposed_state": "PRESENT",
                    "value": "A refresh's underlying Excel/CSV file path has changed or the file isn't in the expected folder.",
                    "source_reference": "KCTA transcript: common errors/fixes"},
        "impact": {"proposed_state": "PRESENT",
                   "value": "The scheduled Power BI refresh fails with a credentials error, blocking dashboard publish until fixed.",
                   "source_reference": "KCTA transcript: common errors/fixes"},
        "detection_method": {"proposed_state": "PRESENT",
                              "value": "Refresh fails in Power BI Desktop/Service with a visible data-source credentials error.",
                              "source_reference": "KCTA transcript: common errors/fixes"},
        "resolution_path": {"proposed_state": "PRESENT",
                             "value": "Reconnect/repoint the data source to the correct file path in Power BI's Data Source Settings, then retry the refresh.",
                             "source_reference": "KCTA transcript: common errors/fixes"},
    },
    "ki-column-not-found": {
        "trigger": {"proposed_state": "PRESENT",
                    "value": "The Region Lookup table gains a new column, or a SAP-extract column is renamed.",
                    "source_reference": "KCTA transcript: common errors/fixes"},
        "impact": {"proposed_state": "PRESENT",
                   "value": "Power BI's Transform Data step throws an expression error, blocking the Revenue dashboard refresh.",
                   "source_reference": "KCTA transcript: common errors/fixes"},
        "detection_method": {"proposed_state": "PRESENT",
                              "value": "Power Query's Transform Data step surfaces an explicit 'column not found' expression error on refresh.",
                              "source_reference": "KCTA transcript: common errors/fixes"},
        "resolution_path": {"proposed_state": "PRESENT",
                             "value": "Fixed manually in Power Query's Transform Data step; no written guide exists for this fix today.",
                             "source_reference": "KCTA transcript: common errors/fixes"},
    },
    "ki-encoding": {
        "trigger": {"proposed_state": "PRESENT",
                    "value": "The pipe-delimited SAP MM extract is occasionally saved as ANSI instead of UTF-8.",
                    "source_reference": "KCTA transcript: common errors/fixes"},
        "impact": {"proposed_state": "PRESENT",
                   "value": "The imported Inventory data shows garbled characters, corrupting the aging report until fixed.",
                   "source_reference": "KCTA transcript: common errors/fixes"},
        "detection_method": {"proposed_state": "PRESENT",
                              "value": "Garbled/incorrect characters are visible in the imported inventory data after the pipe-delimited import.",
                              "source_reference": "KCTA transcript: common errors/fixes"},
        "resolution_path": {"proposed_state": "PRESENT",
                             "value": "Re-save the file as UTF-8 in Notepad before re-importing into Excel/Power BI.",
                             "source_reference": "KCTA transcript: common errors/fixes"},
    },
    "ki-missing-90plus-col": {
        "trigger": {"proposed_state": "PRESENT",
                    "value": "The SAP MM extraction has no data in the 90-plus aging bucket for that period.",
                    "source_reference": "KCTA transcript: Inventory data source/storage/validation"},
        "impact": {"proposed_state": "PRESENT",
                   "value": "The dashboard's four-aging-column requirement is violated, causing a Power BI import error if not corrected.",
                   "source_reference": "KCTA transcript: Inventory data source/storage/validation"},
        "detection_method": {"proposed_state": "PRESENT",
                              "value": "The pipe-delimited extract is missing the fourth (90-plus) aging column entirely, visible on inspection.",
                              "source_reference": "KCTA transcript: Inventory data source/storage/validation"},
        "resolution_path": {"proposed_state": "PRESENT",
                             "value": "Manually add back the 90-plus column as an empty column before importing.",
                             "source_reference": "KCTA transcript: Inventory data source/storage/validation"},
    },
    "ki-no-crosscheck-formula": {
        "trigger": {"proposed_state": "PRESENT",
                    "value": "Total quantity on the Inventory dashboard should roughly match the Supply Chain report each month.",
                    "source_reference": "KCTA transcript: Inventory data source/storage/validation"},
        "impact": {"proposed_state": "PRESENT",
                   "value": "Without a formal check, a data-quality mismatch versus the Supply Chain report could go unnoticed.",
                   "source_reference": "KCTA transcript: Inventory data source/storage/validation"},
        "detection_method": {"proposed_state": "PRESENT",
                              "value": "Previously checked by eye, flagging if totals are off by more than 10-15%; no documented formula exists.",
                              "source_reference": "KCTA transcript: Inventory data source/storage/validation"},
        "resolution_path": {"proposed_state": "PRESENT",
                             "value": "Manually eyeball total quantity against the Supply Chain report and flag any 10-15%+ discrepancy; no formalized formula exists yet.",
                             "source_reference": "KCTA transcript: Inventory data source/storage/validation"},
    },
    "ki-returns-workspace-uncertain": {
        "trigger": {"proposed_state": "PRESENT",
                    "value": "Publishing the refreshed Returns dashboard to its Power BI Service workspace.",
                    "source_reference": "KCTA transcript: Inventory manual steps/workspace, Dashboard 3 overview"},
        "impact": {"proposed_state": "PRESENT",
                   "value": "The new owner may publish to the wrong or an unconfirmed workspace, breaking distribution for report consumers.",
                   "source_reference": "KCTA transcript: Inventory manual steps/workspace, Dashboard 3 overview"},
        "detection_method": {"proposed_state": "PRESENT",
                              "value": "The outgoing owner was himself not certain of the exact workspace name and said he would confirm later.",
                              "source_reference": "KCTA transcript: Inventory manual steps/workspace, Dashboard 3 overview"},
        "resolution_path": {"proposed_state": "PRESENT",
                             "value": "Confirm the exact Power BI Service workspace name (believed to be 'Ops Analytics Workspace') with the outgoing owner or Ops team before relying on it.",
                             "source_reference": "KCTA transcript: Inventory manual steps/workspace, Dashboard 3 overview"},
    },
    "ki-no-sop": {
        "trigger": {"proposed_state": "PRESENT",
                    "value": "There has never been a consolidated, written procedure for any of the three dashboards prior to this KT session.",
                    "source_reference": "KCTA transcript: backup/recovery, closing"},
        "impact": {"proposed_state": "PRESENT",
                   "value": "All refresh procedures, contacts, validation heuristics, and error fixes existed only in the outgoing owner's head -- a single point of failure for the whole handover.",
                   "source_reference": "KCTA transcript: backup/recovery, closing"},
        "detection_method": {"proposed_state": "PRESENT",
                              "value": "Explicitly confirmed by the outgoing owner during this KT session: 'There's nothing written down. This has all been in my head.'",
                              "source_reference": "KCTA transcript: backup/recovery, closing"},
        "resolution_path": {"proposed_state": "PRESENT",
                             "value": "This KT session's transcript and the resulting knowledge graph/package now serve as the first written record; the receiver should treat it as the SOP going forward.",
                             "source_reference": "KCTA transcript: backup/recovery, closing"},
    },
}

# -- Tasks (mandatory: trigger_condition, execution_steps, responsible_role,
#    validation_criteria) -----------------------------------------------------

TASK_ATTRIBUTES: dict[str, dict[str, dict]] = {
    "task-rev-source": {
        "trigger_condition": {"proposed_state": "PRESENT", "value": "Weekly, ahead of the Monday 10 AM Revenue Refresh SLA.",
                               "source_reference": "KCTA transcript: Revenue SLA"},
        "execution_steps": {"proposed_state": "PRESENT",
                             "value": r"Download Revenue_Weekly_YYYYMMDD.xlsx from the Finance SharePoint site (Documents/Reports/Weekly Revenue Raw) and place it at D:\Data\PBI_Refresh\Revenue\Raw\ without opening/resaving it.",
                             "source_reference": "KCTA transcript: Retrieve & Place Revenue Extract"},
        "responsible_role": {"proposed_state": "PRESENT", "value": "Dashboard owner (KT receiver).",
                              "source_reference": "KCTA transcript: Retrieve & Place Revenue Extract"},
        "validation_criteria": {"proposed_state": "PRESENT",
                                 "value": "File is present at the exact hardcoded path, unopened/unmodified, ready for the next validation task.",
                                 "source_reference": "KCTA transcript: Retrieve & Place Revenue Extract"},
    },
    "task-rev-validate": {
        "trigger_condition": {"proposed_state": "PRESENT", "value": "After the Revenue extract file is retrieved and placed.",
                               "source_reference": "KCTA transcript: Validate Revenue Extract Data Quality"},
        "execution_steps": {"proposed_state": "PRESENT",
                             "value": "Check row count against the expected ~2,000-2,500 range, confirm no blanks in the Net Revenue column (F), and confirm the date column (B) only contains current-week dates.",
                             "source_reference": "KCTA transcript: Validate Revenue Extract Data Quality"},
        "responsible_role": {"proposed_state": "PRESENT", "value": "Dashboard owner (KT receiver).",
                              "source_reference": "KCTA transcript: Validate Revenue Extract Data Quality"},
        "validation_criteria": {"proposed_state": "PRESENT",
                                 "value": "Row count within expected range, no blank Net Revenue values, dates restricted to the current week; escalate to Suresh in Finance if row count is out of range.",
                                 "source_reference": "KCTA transcript: Validate Revenue Extract Data Quality"},
    },
    "task-rev-region": {
        "trigger_condition": {"proposed_state": "PRESENT", "value": "After Revenue data validation passes.",
                               "source_reference": "KCTA transcript: Map Region Bucket via VLOOKUP"},
        "execution_steps": {"proposed_state": "PRESENT",
                             "value": "Add a Region Group column via VLOOKUP(H2, Region_Lookup!A:B, 2, FALSE) against the Region_Lookup tab.",
                             "source_reference": "KCTA transcript: Map Region Bucket via VLOOKUP"},
        "responsible_role": {"proposed_state": "PRESENT", "value": "Dashboard owner (KT receiver).",
                              "source_reference": "KCTA transcript: Map Region Bucket via VLOOKUP"},
        "validation_criteria": {"proposed_state": "PRESENT",
                                 "value": "Every region code resolves to a Region Group; any unmapped code is added manually and reported to Finance.",
                                 "source_reference": "KCTA transcript: Map Region Bucket via VLOOKUP"},
    },
    "task-rev-refresh": {
        "trigger_condition": {"proposed_state": "PRESENT",
                               "value": "After region mapping is complete, before the 10 AM Monday SLA deadline.",
                               "source_reference": "KCTA transcript: Refresh & Publish Revenue Dashboard"},
        "execution_steps": {"proposed_state": "PRESENT",
                             "value": "Verify the data source path in Transform Data/Data Source Settings, Close & Apply, Refresh (~3-5 min), then Publish to the Finance Analytics Workspace.",
                             "source_reference": "KCTA transcript: Refresh & Publish Revenue Dashboard"},
        "responsible_role": {"proposed_state": "PRESENT", "value": "Dashboard owner (KT receiver).",
                              "source_reference": "KCTA transcript: Refresh & Publish Revenue Dashboard"},
        "validation_criteria": {"proposed_state": "PRESENT",
                                 "value": "Refresh completes without error in the expected time window (investigate if over 10 minutes) and the published report is visible in the Finance Analytics Workspace before the SLA deadline.",
                                 "source_reference": "KCTA transcript: Refresh & Publish Revenue Dashboard"},
    },
    "task-rev-notify": {
        "trigger_condition": {"proposed_state": "PRESENT", "value": "Immediately after the Revenue dashboard is successfully published.",
                               "source_reference": "KCTA transcript: Notify #finance-reporting Channel"},
        "execution_steps": {"proposed_state": "PRESENT",
                             "value": "Send an informal Teams message to #finance-reporting confirming the weekly revenue report has been updated.",
                             "source_reference": "KCTA transcript: Notify #finance-reporting Channel"},
        "responsible_role": {"proposed_state": "PRESENT", "value": "Dashboard owner (KT receiver).",
                              "source_reference": "KCTA transcript: Notify #finance-reporting Channel"},
        "validation_criteria": {"proposed_state": "PRESENT",
                                 "value": "A confirmation message appears in #finance-reporting after each successful publish.",
                                 "source_reference": "KCTA transcript: Notify #finance-reporting Channel"},
    },
    "task-ret-source": {
        "trigger_condition": {"proposed_state": "PRESENT", "value": "Bi-weekly, typically the Friday before the Monday refresh.",
                               "source_reference": "KCTA transcript: Retrieve Salesforce Returns CSV Export"},
        "execution_steps": {"proposed_state": "PRESENT",
                             "value": "Receive Returns_Data_MMYYYY.csv, emailed by Anita from Salesforce.",
                             "source_reference": "KCTA transcript: Retrieve Salesforce Returns CSV Export"},
        "responsible_role": {"proposed_state": "PRESENT", "value": "Dashboard owner (KT receiver); Anita (CRM team) is the source contact.",
                              "source_reference": "KCTA transcript: Retrieve Salesforce Returns CSV Export"},
        "validation_criteria": {"proposed_state": "PRESENT",
                                 "value": "The CSV has been received by email before the scheduled bi-weekly refresh.",
                                 "source_reference": "KCTA transcript: Retrieve Salesforce Returns CSV Export"},
    },
    "task-ret-validate": {
        "trigger_condition": {"proposed_state": "PRESENT", "value": "After the Returns CSV export is received.",
                               "source_reference": "KCTA transcript: Validate Returns Data Date Range"},
        "execution_steps": {"proposed_state": "PRESENT",
                             "value": "Confirm the Return Date column (A) falls within the expected bi-weekly window.",
                             "source_reference": "KCTA transcript: Validate Returns Data Date Range"},
        "responsible_role": {"proposed_state": "PRESENT", "value": "Dashboard owner (KT receiver).",
                              "source_reference": "KCTA transcript: Validate Returns Data Date Range"},
        "validation_criteria": {"proposed_state": "PRESENT",
                                 "value": "All dates in column A fall inside the expected bi-weekly window.",
                                 "source_reference": "KCTA transcript: Validate Returns Data Date Range"},
    },
    "task-ret-standardize": {
        "trigger_condition": {"proposed_state": "PRESENT", "value": "After date validation passes.",
                               "source_reference": "KCTA transcript: Standardize Return Reason Values"},
        "execution_steps": {"proposed_state": "PRESENT",
                             "value": "Manually find-and-replace inconsistent CRM export values (e.g. 'Product Defect' -> 'Defective'); no lookup table exists for this.",
                             "source_reference": "KCTA transcript: Standardize Return Reason Values"},
        "responsible_role": {"proposed_state": "PRESENT", "value": "Dashboard owner (KT receiver).",
                              "source_reference": "KCTA transcript: Standardize Return Reason Values"},
        "validation_criteria": {"proposed_state": "PRESENT",
                                 "value": "Return Reason values are normalized to the standard set used by the dashboard, done manually since no lookup table exists.",
                                 "source_reference": "KCTA transcript: Standardize Return Reason Values"},
    },
    "task-ret-refresh": {
        "trigger_condition": {"proposed_state": "PRESENT", "value": "After Return Reason standardization is complete.",
                               "source_reference": "KCTA transcript: Refresh & Publish Returns Dashboard"},
        "execution_steps": {"proposed_state": "PRESENT",
                             "value": "Refresh Returns_Dashboard.pbix and publish to its Power BI Service workspace.",
                             "source_reference": "KCTA transcript: Refresh & Publish Returns Dashboard"},
        "responsible_role": {"proposed_state": "PRESENT", "value": "Dashboard owner (KT receiver).",
                              "source_reference": "KCTA transcript: Refresh & Publish Returns Dashboard"},
        "validation_criteria": {"proposed_state": "PRESENT",
                                 "value": "Refresh and publish complete without error; destination workspace name should be confirmed (see the Returns Workspace Name Unconfirmed known issue) rather than assumed.",
                                 "source_reference": "KCTA transcript: Refresh & Publish Returns Dashboard"},
    },
    "task-inv-source": {
        "trigger_condition": {"proposed_state": "PRESENT", "value": "Monthly, at month end.",
                               "source_reference": "KCTA transcript: Retrieve SAP MM Inventory Extract"},
        "execution_steps": {"proposed_state": "PRESENT",
                             "value": "Receive the pipe-delimited Inventory_Aging_MMMYYYY.txt file, auto-emailed by the ERP team.",
                             "source_reference": "KCTA transcript: Retrieve SAP MM Inventory Extract"},
        "responsible_role": {"proposed_state": "PRESENT", "value": "Dashboard owner (KT receiver); Vijay is the ERP/SAP MM extraction contact.",
                              "source_reference": "KCTA transcript: Retrieve SAP MM Inventory Extract"},
        "validation_criteria": {"proposed_state": "PRESENT",
                                 "value": "The pipe-delimited file has been received by email at month end; recipient address to be reconfirmed with Vijay.",
                                 "source_reference": "KCTA transcript: Retrieve SAP MM Inventory Extract"},
    },
    "task-inv-import": {
        "trigger_condition": {"proposed_state": "PRESENT", "value": "After the monthly Inventory extract is received.",
                               "source_reference": "KCTA transcript: Import Pipe-Delimited Inventory File"},
        "execution_steps": {"proposed_state": "PRESENT",
                             "value": "Import the file into Excel using the Import function (not double-click-open), or the pipe-delimited data collapses into a single column.",
                             "source_reference": "KCTA transcript: Import Pipe-Delimited Inventory File"},
        "responsible_role": {"proposed_state": "PRESENT", "value": "Dashboard owner (KT receiver).",
                              "source_reference": "KCTA transcript: Import Pipe-Delimited Inventory File"},
        "validation_criteria": {"proposed_state": "PRESENT",
                                 "value": "Data appears correctly split across columns after import (not collapsed into one column) and is not garbled.",
                                 "source_reference": "KCTA transcript: Import Pipe-Delimited Inventory File"},
    },
    "task-inv-costvalue": {
        "trigger_condition": {"proposed_state": "PRESENT", "value": "After the Inventory file is successfully imported.",
                               "source_reference": "KCTA transcript: Add Cost Value Column"},
        "execution_steps": {"proposed_state": "PRESENT",
                             "value": "Multiply Quantity by Unit Cost, where Unit Cost is looked up from Item_Master.xlsx (maintained by the Costing team on SharePoint).",
                             "source_reference": "KCTA transcript: Add Cost Value Column"},
        "responsible_role": {"proposed_state": "PRESENT", "value": "Dashboard owner (KT receiver), sourcing Unit Cost from the Costing team's file.",
                              "source_reference": "KCTA transcript: Add Cost Value Column"},
        "validation_criteria": {"proposed_state": "PRESENT",
                                 "value": "Every row has a computed Cost Value using the current Item_Master.xlsx unit costs.",
                                 "source_reference": "KCTA transcript: Add Cost Value Column"},
    },
    "task-inv-flag": {
        "trigger_condition": {"proposed_state": "PRESENT", "value": "After the Cost Value column is added.",
                               "source_reference": "KCTA transcript: Add Review Flag Column"},
        "execution_steps": {"proposed_state": "PRESENT",
                             "value": 'Add an IF formula (e.g. =IF(G2>0,"Yes","No")) flagging any item with nonzero 90-plus-day aged quantity for review.',
                             "source_reference": "KCTA transcript: Add Review Flag Column"},
        "responsible_role": {"proposed_state": "PRESENT", "value": "Dashboard owner (KT receiver).",
                              "source_reference": "KCTA transcript: Add Review Flag Column"},
        "validation_criteria": {"proposed_state": "PRESENT",
                                 "value": "Every item with nonzero 90-plus aged quantity is flagged 'Yes' for review.",
                                 "source_reference": "KCTA transcript: Add Review Flag Column"},
    },
    "task-inv-refresh": {
        "trigger_condition": {"proposed_state": "PRESENT", "value": "After the Review Flag column is added.",
                               "source_reference": "KCTA transcript: Refresh & Publish Inventory Dashboard"},
        "execution_steps": {"proposed_state": "PRESENT",
                             "value": "Refresh Inventory_Aging_Dashboard.pbix and publish to the Supply Chain Analytics workspace.",
                             "source_reference": "KCTA transcript: Refresh & Publish Inventory Dashboard"},
        "responsible_role": {"proposed_state": "PRESENT", "value": "Dashboard owner (KT receiver).",
                              "source_reference": "KCTA transcript: Refresh & Publish Inventory Dashboard"},
        "validation_criteria": {"proposed_state": "PRESENT",
                                 "value": "Refresh and publish complete without error and the report is visible in the Supply Chain Analytics workspace.",
                                 "source_reference": "KCTA transcript: Refresh & Publish Inventory Dashboard"},
    },
    "task-inv-distribute": {
        "trigger_condition": {"proposed_state": "PRESENT", "value": "Immediately after the Inventory dashboard is published.",
                               "source_reference": "KCTA transcript: Export & Email Excel to Supply Chain Director"},
        "execution_steps": {"proposed_state": "PRESENT",
                             "value": "Export the main table as Excel and email it directly to the Supply Chain Director (Arjun Mehta), CC warehouse managers, since he doesn't use Power BI Service.",
                             "source_reference": "KCTA transcript: Export & Email Excel to Supply Chain Director"},
        "responsible_role": {"proposed_state": "PRESENT", "value": "Dashboard owner (KT receiver).",
                              "source_reference": "KCTA transcript: Export & Email Excel to Supply Chain Director"},
        "validation_criteria": {"proposed_state": "PRESENT",
                                 "value": "Arjun Mehta and the warehouse managers receive the Excel export by email after each publish.",
                                 "source_reference": "KCTA transcript: Export & Email Excel to Supply Chain Director"},
    },
}

# Combined overlay keyed by object id, applied on top of the base
# OBJECTS_BY_CHUNK entries in scripts/seed_demo_kai_cache.py.
PILOT_ATTRIBUTE_OVERLAY: dict[str, dict[str, dict]] = {
    **SYSTEM_ATTRIBUTES,
    **KNOWN_ISSUE_ATTRIBUTES,
    **TASK_ATTRIBUTES,
}

# REMOVED (issue_log.md #13): System -> Dependency DEPENDS_ON edges are
# no longer pre-seeded here. discover_relationships() only consults
# RELATIONSHIP_TYPE_RULES (primary), never RELATIONSHIP_TYPE_RULES_ADDITIONAL,
# so these were silently rejected at ingestion despite being valid per
# scoring/RC. Each System now starts with an open RELATIONSHIP_GAP
# (rule_family "failure_recovery") and closes it for real through the
# hierarchical closure loop -- see
# services/demo/hierarchical_gap_answers.py's _RELATIONSHIP_ANSWERS,
# which uses InterpretedRelationshipChange via apply_interpreted_changes()
# (confirmed no type-pair check on that path). The bug itself is
# unfixed and reported separately.
