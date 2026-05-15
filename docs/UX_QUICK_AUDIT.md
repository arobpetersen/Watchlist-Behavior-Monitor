# UX Quick Audit

Date: 2026-05-14

## Executive Summary

- Daily Snapshot, Rolling Setup Monitor, and Daily Intelligence Report now share a much clearer review language: Market Context, Day Read, Trigger Read, and ticker detail.
- The biggest easy UX win is label cleanup on older/support pages. Several places still say `Failed D0`, `Later Failed`, `Close Loc.`, or `Range / ATR14` while newer pages use `D0 Fail`, `Failed After D0`, `Close Position`, and `Range x ATR(14)`.
- Setup Behavior Overview remains useful but feels like the least aligned main page: it leads with historical windows and legacy trigger tables, while the Daily Intelligence Report is hidden in an expander.
- Daily Snapshot still has old `Daily Feature Detail` and `Group Summaries` below the new top read. They are useful as audit/context, but the labels and prominence feel older than the new workflow table.
- Watchlist Top Movers is functionally strong but has a confusing title/section mismatch: `Hypothetical Optimal Portfolio` sounds more strategic than the rest of the app and can feel recommendation-adjacent.
- Performance quick wins are mostly already identified in `docs/PERFORMANCE_AUDIT.md`: selected-date caching for Daily Snapshot, clearer cache-hit diagnostics, and reducing duplicate token/helper calls are the best small follow-ups.

## Easy Wins

| Area/Page | Issue | Suggested Fix | Impact | Complexity | Risk |
| --- | --- | --- | --- | --- | --- |
| Setup Behavior Overview | User-facing labels still use `Later Failed` in captions, filters, tables, and reads. | Rename display labels to `Failed After D0` while keeping underlying helper names unchanged. | High | Low | Low |
| Setup Performance | Definitions/table use `Failed D0`, while newer day reads use `D0 Fail`. | Keep table metric if desired, but add wording that setup-level `Failed D0` is lifecycle-status based; avoid mixing it with top-read `D0 Fail`. | Medium | Low | Low |
| Daily Feature Detail / Ticker Detail / Rolling Behavior | Legacy labels `Close Loc.` and `Range / ATR14` remain in older tables. | Rename display columns to `Close Position` and `Range x ATR(14)` or `Range / ATR(14)` consistently. | Medium | Low | Low |
| Daily Snapshot | Group Summaries are visually prominent as a `subheader` after the editor. | Move to a collapsed `Group Summaries / Audit` expander or add a caption that they are secondary context. | Medium | Low | Low |
| Daily Snapshot | `Edit Selected Candidate` is a full subheader directly after the table. | Put editor in a collapsed expander or rename to `Edit Setup / Entry Tactic / Rating` to match Rolling Setup Monitor. | Medium | Low | Low |
| Rolling Setup Monitor | Definitions and Audit OR Trigger appear before data. | Consider moving `Audit OR Trigger` below the setup-date sections or collapsing it under a secondary `Audit Tools` grouping. | Medium | Low/Medium | Low |
| Watchlist Top Movers | `Hypothetical Optimal Portfolio` sounds recommendation-like. | Rename to `Hypothetical Portfolio View` or `Portfolio View` and keep eligibility wording. | High | Low | Low |
| Watchlist Top Movers | `Reference Tables` appears as a large header before the most-used Top Movers tables. | Rename to `Mover Tables` or remove the extra header so the two tables scan faster. | Low/Medium | Low | Low |
| Daily Intelligence Report | Report is hidden inside Setup Behavior Overview expander. | Keep it in the same page, but consider expanding it by default or placing it before historical window detail. | Medium | Low | Low |
| Data Health | `Refresh derived views from database` is technically accurate but not very user-clear. | Add button help/caption: refreshes cached derived monitor/report views after metadata or database updates. | Medium | Low | Low |
| Data Health | `Active/Coverage Rows` and `Coverage Source` are accurate but technical. | Rename display labels to `Rows Checked` and `Coverage Check Source`. | Low/Medium | Low | Low |
| Shared UI | Repeated page-level `Data Health` expanders can compete with page content. | Keep collapsed unless warning; add a one-line summary caption only when healthy. | Medium | Low | Low |
| Performance | Daily Snapshot selected-date monitor table recomputes on rerun. | Add cached selected-date loader keyed by `db_path`, setup date, and data-health token. | Medium | Low | Low |
| Performance | Several pages call `data_health_cache_token(db_path)` multiple times per render. | Compute once per page and reuse local variable. | Low | Low | Low |
| Performance Debug | Cached detailed monitor timings can look like a fresh rebuild happened. | Label as `last cache-miss build detail` or only show detailed rows when cache miss is known. | Medium | Low | Low |

## Page-by-Page Notes

### Daily Snapshot

What works:
- The page now reads like a single-day review sheet.
- Market Context, Day Read, and Trigger Read are visually aligned with Rolling Setup Monitor.
- The Setup Candidates table remains the right primary detail surface.
- Metadata editing is scoped to manual fields and does not imply trigger/status editability.

What feels off:
- `Daily Feature Detail` and `Group Summaries` still use older labels from `dashboard_queries.py`, including `Close Loc.` and `Range / ATR14`.
- Group Summaries are visually secondary but presented as a full subheader, which can make them feel as important as the canonical workflow table.
- The editor label differs from Rolling Setup Monitor. Daily Snapshot says `Edit Selected Candidate`; Rolling says `Edit Setup / Entry Tactic / Rating`.

Easy improvement candidates:
- Rename Daily Feature Detail columns to `Close Position` and `Range x ATR(14)`.
- Move Group Summaries into a collapsed expander or relabel as `Group Summaries / Audit`.
- Rename the editor section to `Edit Setup / Entry Tactic / Rating`.
- Add a small caption under Group Summaries that these are legacy feature summaries, not canonical lifecycle outcomes.

### Rolling Setup Monitor

What works:
- The top read is now the strongest visual hierarchy in the app.
- D0 Fail behavior matches the desired definition.
- Market Context uses the clearer QQQ move, character tag, Close Position, and ATR(14) language.
- Trigger Read is compact and readable without becoming a wall of text.

What feels off:
- `Definitions / Logic` and `Audit OR Trigger` come before the actual setup-date sections. They are collapsed, but they still occupy the top of the page before the user sees the daily read.
- The detail table and metadata editor are in good places, but the audit tool feels like a developer/validation tool more than a primary monitor feature.

Easy improvement candidates:
- Move `Audit OR Trigger` below the setup-date sections or group it with other audit/detail expanders.
- Add a one-line caption under the title: `Latest 5 setup dates using canonical monitor rows.` This would clarify why it differs from all-history pages.
- Consider using the same metadata editor section label as Daily Snapshot after that page is renamed.

### Setup Behavior Overview

What works:
- It is the main historical comparison page and uses shared cached monitor history.
- The Daily Intelligence Report now provides a concise written synopsis inside the page.
- Definitions are clear and collapsed.

What feels off:
- This page still uses older language heavily: `Later Failed`, `Clean Active`, `Median Current`, `Median Max`, and multiple historical trigger tables.
- The Daily Intelligence Report is probably the most useful 10-second read on the page, but it is inside an expander after the Historical Window Summary.
- Captions use `Currently Active and Later Failed`, while newer page language says `Active` and `Failed After D0`.
- The `Current status` filter includes `Later Failed`, which is less clear than `Failed After D0`.

Easy improvement candidates:
- Rename user-facing `Later Failed` to `Failed After D0` on this page.
- Put Daily Intelligence Report above `Historical Window Summary`, or expand it by default.
- Keep historical trigger tables but make them feel explicitly secondary: `Historical Trigger Outcomes`.
- Review whether `Median Current` and `Median Max` should remain in overview tables only, not in top snapshot/cards.

### Watchlist Top Movers

What works:
- Page intent is clear once the user reaches the tables.
- Portfolio eligibility audit is collapsed and useful for trust.
- It uses shared full monitor history and is cheap once history exists.
- Captions explain entry-based Current % / Max % clearly.

What feels off:
- `Hypothetical Optimal Portfolio` sounds more recommendation-like than the app’s current deterministic language.
- `Reference Tables` is a large header that may down-rank the actual Top Movers tables unnecessarily.
- `Top 10 Active Watchlist Movers` and `Top Triggered Watchlist Movers` are useful, but the page starts with the portfolio section before the broader active/top mover read.

Easy improvement candidates:
- Rename `Hypothetical Optimal Portfolio` to `Hypothetical Portfolio View` or `Portfolio View`.
- Rename `Reference Tables` to `Mover Tables` or remove the header.
- Consider leading with `Top 10 Active Watchlist Movers`, then portfolio view, if user workflow is usually “what is moving now?”
- Keep all current filters and tables unchanged.

### Setup Performance

What works:
- Purpose is clearly stated and auditable.
- It correctly reuses shared monitor history.
- Filters are simple and the page is not visually overbuilt.
- Unclassified grouping and sample gating are explained.

What feels off:
- It still uses `Failed D0`, not `D0 Fail`. That is acceptable if it means strict lifecycle status, but the distinction from top-read D0 Fail should be explicit.
- Top cards use `st.metric`, which is compact but less visually aligned with the custom top-read tiles elsewhere.
- The table is wide, but appropriate for this page’s purpose.

Easy improvement candidates:
- Add one sentence in Definitions: `Setup Performance Failed D0 uses Current Status only; day-level D0 Fail also includes Trigger Day Fail.`
- Consider renaming `Highest Failure Setup` card detail to make sample gating clearer.
- Leave the core table alone for now.

### Daily Intelligence Report

What works:
- The report now follows the requested order: Summary Read, Market Context, Day Read, Trigger Read, Names to Review, Portfolio Snapshot.
- It avoids the old dense Watchlist Pulse / Trigger Quality / Progression table stack.
- D0 Fail, Failed After D0, Retested, Close < BE, and Median D3 High align with Daily Snapshot / Rolling Setup Monitor.
- The visible LLM prompt surface has been removed.

What feels off:
- The `Names to Review` section can still feel like a mini dump if five rows all have similar reasons.
- Portfolio Snapshot still says `Current Progress portfolio`, which is fine, but it may be read as more action-oriented than intended.
- The report is inside an expander, so many users may miss the improved synopsis.

Easy improvement candidates:
- Cap Names to Review at three rows in the rendered report, while keeping payload logic unchanged.
- Add reason grouping if multiple names have the same reason, but only as a small formatting pass.
- Consider expanding the report by default on Setup Behavior Overview.

### Data Health Indicator

What works:
- The expensive full-history dependency was removed from the default health path.
- The indicator is collapsed unless status requires attention.
- Stale active daily-bar rows are auditable and capped.

What feels off:
- Labels such as `Active/Coverage Rows` and `Coverage Source` are accurate but technical.
- The data health expander appears on several pages; when healthy, it may still visually compete with page content.
- `Refresh derived views from database` is precise but not intuitive to a non-developer user.

Easy improvement candidates:
- Rename `Active/Coverage Rows` to `Rows Checked`.
- Rename `Coverage Source` to `Coverage Check Source`.
- Add button help text or a caption near refresh buttons: `Refreshes cached monitor/report views after data or manual metadata changes.`

### Ticker Detail

What works:
- It is simple and fast to understand: select ticker, see rows.
- It is appropriately narrow.

What feels off:
- It uses older feature-detail labels like `Close Loc.` and `Range / ATR14`.
- It lacks context that this is an audit/detail page, not the canonical setup-day read.
- There is no Data Health indicator, refresh affordance, or explanation of what fields are shown.

Easy improvement candidates:
- Rename columns to match newer language.
- Add a short caption: `Per-ticker feature and setup history for audit/context.`
- Consider adding Data Health only if this page becomes a regular workflow page; otherwise keep it lightweight.

### Rolling Setup Behavior

What works:
- It is very simple.

What feels off:
- It appears to be an older/legacy page next to the newer Setup Behavior Overview.
- It uses older summary labels from `dashboard_queries.py`.
- It may duplicate or confuse the newer overview page.

Easy improvement candidates:
- Add a caption that this is a legacy feature summary, or consider hiding/deprioritizing it later.
- Rename old `Close Loc.` / `Range / ATR14` labels if the page stays visible.

## Top 5 Recommended Next Tasks

### 1. Normalize user-facing failure labels on Setup Behavior Overview

Why it matters: This is the largest remaining language mismatch. The page still says `Later Failed` in captions, filters, tables, and reads while the newer pages use `Failed After D0`.

Files likely involved:
- `pages/5_Setup_Behavior_Overview.py`
- `src/setup_behavior_overview.py`
- related tests in `tests/test_setup_behavior_overview.py`

Estimated complexity: Low/Medium.

Tests needed: Yes. Display-label assertions will likely need updates.

### 2. Rename old market/feature labels in audit tables

Why it matters: `Close Loc.` and `Range / ATR14` now look stale next to `Close Position` and `Range x ATR(14)`.

Files likely involved:
- `src/dashboard_queries.py`
- `src/rolling_setup_monitor.py` for detail-table display labels, if desired
- tests that assert exact column names

Estimated complexity: Low.

Tests needed: Yes if exact table-column tests exist.

### 3. Make Daily Snapshot secondary sections feel secondary

Why it matters: The new top read and Setup Candidates table are the primary workflow. Group Summaries and Daily Feature Detail should read as audit/context.

Files likely involved:
- `pages/1_Daily_Snapshot.py`

Estimated complexity: Low.

Tests needed: Maybe. Only if page-source smoke tests assert section names/order.

### 4. Rename Top Movers portfolio wording

Why it matters: `Hypothetical Optimal Portfolio` is the closest remaining phrase to recommendation-style language. A neutral label improves trust and consistency.

Files likely involved:
- `pages/6_Watchlist_Top_Movers.py`
- possibly tests for page source strings

Estimated complexity: Low.

Tests needed: Maybe.

### 5. Add cached selected-date Daily Snapshot loader

Why it matters: Daily Snapshot is already selected-date optimized, but ordinary Streamlit reruns still rebuild the selected-date monitor table. This is a small performance win without changing metrics.

Files likely involved:
- `pages/1_Daily_Snapshot.py`
- possibly `src/dashboard_queries.py` if the cached loader is centralized

Estimated complexity: Low.

Tests needed: Optional. Existing tests should cover behavior; add a small source-level test only if practical.

## Do Not Do Yet

- Do not materialize full monitor history in DuckDB as part of a UX cleanup.
- Do not redesign the full app navigation.
- Do not add market regime analytics or setup performance by market context.
- Do not add deeper backtesting, outcome prediction, or recommendation language.
- Do not add a new Market Context page.
- Do not replace current canonical lifecycle/status logic.
- Do not remove audit/detail tables before confirming which ones are still used in the workflow.
- Do not make broad CSS redesigns across all pages in one pass.
- Do not add LLM-generated narrative reports.

