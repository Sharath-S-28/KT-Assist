# KT-Assist — Research, IP & Publication Program

Persistent registry for the research track. Survives across sessions; the four
other knowledge files remain authoritative for engineering state.

**Claim tagging convention (applies to every row in this file):**
`VERIFIED` (traceable to project material, a citation, or an executed experiment) ·
`INFERRED` (reasonable read of available evidence) ·
`HYPOTHESIS` (untested) · `UNKNOWN` (needs research).

**Status legend for readiness:** Red = insufficient research · Amber = underway ·
Green = manuscript-ready · Blue = submission-ready (three-reviewer pass cleared).

---

## 0. BLOCKING GATE — Provenance & IP ownership

**Nothing in Sections 3–7 may be published, filed, demonstrated externally, or
carried into an independent product until this section resolves.** This is not a
formality. It determines whether there is a research program at all.

Status: **OPEN — unresolved as of 2026-08-14.**

### 0.1 Facts established

| # | Fact | Tag |
|---|---|---|
| P1 | System was conceived and built in the context of a pitch to Genpact (employer) | VERIFIED (owner statement) |
| P2 | Repository `github.com/Sharath-S-28/KT-Assist` is a personal private GitHub account, not a Genpact-owned org | VERIFIED |
| P3 | Owner now intends to develop the concept independently of Genpact | VERIFIED (owner statement, 2026-08-14) |
| P4 | Frontend palette and brand assets are Genpact-aligned (`frontend/theme.py`, `il86bgenpactrebrandv011.pdf`) | VERIFIED |
| P5 | `KCTA_KT_Transcript_PBI_Dashboards.docx` is the sole real-world evidence asset; its provenance and confidentiality class are undetermined | UNKNOWN |
| P6 | Employment status, invention-assignment terms, and whether build occurred on employer time/equipment | UNKNOWN |
| P7 | Whether the pitch constituted a formal, documented disclosure to Genpact (innovation programme, funded time, management review) | UNKNOWN |
| P8 | Governing jurisdiction assumed India; contract terms likely decisive over statute | INFERRED |
| P9 | Whether any other individual contributed to design or code | UNKNOWN |

### 0.2 Questions that must be answered before the gate clears

1. Current employment status and date of any separation.
2. Exact wording of the invention-assignment / IP clause in the employment
   contract, plus any separate NDA, innovation-programme, or moonlighting policy.
3. Time, equipment, and premises used for the build (personal vs. employer).
4. Nature and documentation trail of the Genpact pitch.
5. Confidentiality class of the PBI transcript and of any client identifiers in it.
6. Whether Genpact has expressed any interest, claim, or decision on the pitch.

### 0.3 Asset disposition (preliminary, pending legal advice)

| Asset | Preliminary disposition | Tag |
|---|---|---|
| General problem framing (KT assurance is unmeasured) | Public domain — an industry-wide problem, not employer IP | INFERRED |
| Owner's personal know-how and skill | Ordinarily portable; contract terms may narrow this | INFERRED |
| Source code in this repository | Highest-risk category — disposition depends on 0.2 items 1–3 | UNKNOWN |
| Master Specification v2 (Chunks 0–10) | Same risk category as code | UNKNOWN |
| PBI transcript and any derived cached extractions | Treat as employer/client-confidential until proven otherwise; **do not carry forward** | INFERRED |
| Genpact palette and brand assets | Not portable under any scenario | VERIFIED |
| Demo personas (Ravi, Priya, Meera) | Fictional; portable | VERIFIED |

### 0.4 Candidate paths (no recommendation until 0.2 is answered)

- **Path A — Written release.** Request an explicit, written assignment or
  non-assertion from Genpact, most plausible if the pitch was declined. Cleanest
  outcome; costs nothing but a conversation and a document.
- **Path B — Clean-room reconstruction.** New repository, no artefact, file, or
  text carried across; rebuilt from published literature and first principles on
  personal time and equipment, with a contemporaneous provenance log. Reduces but
  does not eliminate risk where a broad assignment clause applies.
- **Path C — Divergent product.** Build in the same problem space but from a
  materially different technical approach.

**Standing constraint:** this file and its author are not a substitute for legal
advice. An Indian IP/employment counsel review is a prerequisite, not an optional
extra, before Path A, B, or C is chosen.

---

## 1. Decision log

| ID | Date | Decision | Why | Evidence | Alternatives | Risks | IP implication | Publication implication | Next action |
|---|---|---|---|---|---|---|---|---|---|
| D1 | 2026-08-14 | Open the research/IP track and hold all publication and independent-build activity behind Section 0 | Ownership is undetermined and is upstream of every other decision | §0.1 P1–P9 | Proceed and resolve IP later — rejected as it compounds exposure | Delay | Gate is the IP posture | All papers held at Red | Answer §0.2; obtain counsel |

---

## 2. Mechanism inventory & confidentiality classification

Classification is preliminary. **Novelty is not asserted here** — no mechanism may
carry a novelty claim until it has a row in Section 3.

| ID | Mechanism | Locus | Class | Research interest (HYPOTHESIS unless noted) |
|---|---|---|---|---|
| M1 | LLM excluded from all scoring, enforced mechanically by invariant tests | `tests/invariants/test_architectural_boundaries.py`, `config/scoring.py` | Patent-sensitive | Auditable-by-construction architecture for LLM decision systems |
| M2 | Cross-chunk attribute arbitration (merge / CONFLICTING / deterministic N/A / NOT_OBSERVED) | `services/agents/attribute_arbitration.py` | Patent-sensitive | Deterministic conflict resolution over multi-pass LLM extraction |
| M3 | Five-level finding detection; TC/AC/RC/OS/EV dimensions with N/A renormalisation; KCS/KQS dual gates | `finding_detectors.py`, `dimensional_scoring.py` | Patent-sensitive | Separation of completeness from quality in KG assurance |
| M4 | Finding → Gap → Bundle consolidation and multi-factor prioritisation | `consolidation.py`, `prioritization.py` | Confidential | |
| M5 | Hierarchical closure loop; six termination reasons including deterministic no-progress detection by graph + open-finding signature | `hierarchical_closure.py` | Patent-sensitive | Termination guarantee for LLM-in-the-loop remediation |
| M6 | Transition-risk materiality rules → KAR → readiness-gate adapter | `transition_risk.py`, `kar_adapter.py` | Confidential | |
| M7 | Graph-grounded scenario generation with independent-grounding validation (generator/validator circularity break) | `scenario_generation.py`, `scenario_validation.py` | Patent-sensitive | Strongest single candidate on current evidence |
| M8 | Evidence marker → competency → pillar → OIS; weighted intra-pillar aggregation; asymmetric critical bands; boundary zone | `kase_scoring.py`, `threshold_model.py` | Confidential | Closest to established psychometric practice; weakest novelty prospect |
| M9 | Verbatim scoring-kernel portability via Pyodide with golden parity fixtures | [PROPOSAL R1], issue_log #23 | Public | Reproducibility artefact; not a contribution on its own |

---

## 3. Novelty matrix

**Empty. Phase 1 not started.** No novelty claim may be made anywhere in the
programme until the corresponding row exists here.

| Component | Existing literature | Closest approach | KT Assist difference | Scientific novelty (High–Unclear, with why) | Technical novelty | Patent potential | Publication potential |
|---|---|---|---|---|---|---|---|
| _(none yet)_ | | | | | | | |

---

## 4. Prior-art matrix

**Empty. Phase 3 not started.**

| Invention | Prior art | Similarity | Difference | Novel element | Risk | Required analysis |
|---|---|---|---|---|---|---|
| _(none yet)_ | | | | | | |

---

## 5. Claim–evidence log

Known evidence deficits, recorded so no manuscript can be drafted in ignorance of them.

| ID | Claim the system implicitly makes | Current evidence | Tag | What would resolve it |
|---|---|---|---|---|
| E1 | OIS measures operational independence | None external. Internally consistent only | UNKNOWN | Concurrent/predictive validation against supervisor rating, post-transition incident rate, or time-to-independence |
| E2 | The pipeline works on real KT material | One transcript, one domain (Power BI dashboards) | VERIFIED but n=1 | ≥3 domains, ideally ≥10 packages |
| E3 | Receiver assessment discriminates real capability | All receiver responses to date are Claude-authored or fixture-authored | HYPOTHESIS | Human participants producing genuine responses |
| E4 | Hierarchical assurance improves on the v1 flat-coverage baseline | Both implementations exist and are separately tested; never compared on a common task | HYPOTHESIS | Head-to-head ablation — v1 is a free internal baseline |
| E5 | LLM extraction is reliable enough to ground the scores | Never exercised against a live model in the hierarchical path (no API key in any environment used) | UNKNOWN | Live-model reliability run with inter-run and inter-model agreement measurement |
| E6 | Competency instrumentation covers the construct | 10 of 12 competencies exercised; 2 structurally unreachable (issue_log #14) | VERIFIED (as a limitation) | New scenario-generation mechanisms for Knowledge Stewardship and Analytical Thinking |
| E7 | The readiness bands are meaningfully separable | "Conditionally Ready" was reachable only after a fixture-granularity fix (issue_log #15/#16) | VERIFIED (as a limitation) | Sensitivity analysis on real response data |

---

## 6. Paper manifest

**Empty. Phase 2 not started.** On current evidence no empirical paper is
supportable; see Section 5.

| ID | Working title | Research question(s) | Hypotheses | Novel contribution | Required experiments | Required literature | Patent interaction | Expected reviewer objections | Readiness |
|---|---|---|---|---|---|---|---|---|---|
| _(none yet)_ | | | | | | | | | Red |

---

## 7. Review objections register

| Reviewer concern | Severity | Required change | Evidence needed | Status |
|---|---|---|---|---|
| _(none yet — no manuscript drafted)_ | | | | |

---

## 8. Open questions register

| ID | Question | Owner | Status |
|---|---|---|---|
| Q1–Q6 | See §0.2 (provenance and IP) | Sharath | Open |
| Q7 | Ratification of blueprint rulings R1–R9 (issue_log #23) | Sharath | Open |
| Q8 | Ethics/consent basis for any human-subject evaluation; IRB or equivalent trigger | Sharath | Open |
| Q9 | Target venue class (systems, IR/KG, HCI, management/IS) — depends on which contribution survives Phase 1 | Deferred to Phase 5 | Open |
