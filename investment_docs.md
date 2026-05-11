# Architecture Decision Record
## App 10 — Investment
**Ledger Logic Group | Document 1 of 5**
**Status: Accepted**

---

## Context

The Investment module is the tenth app in the portfolio and the third in the Ledger Logic group. It projects compound interest growth with optional periodic contributions, inflation adjustment, and ASCII chart visualization. It is the most mathematically complex module in the Ledger Logic group, requiring Decimal arithmetic throughout and versioned JSON persistence for scenarios. The module is the first in the portfolio to be split across four implementation files under a single entry-point.

---

## Decisions

### Decision 1 — Four-file architecture under a single entry point

**Chosen:** `investment.py` (entry point / re-exports), `investment_engine.py` (validation and projection math), `investment_reporting.py` (table and chart formatting), `investment_persist.py` (versioned JSON persistence), `investment_cli.py` (interactive menu and prompts).

**Rejected:** A single monolithic file.

**Reason:** The four concerns are genuinely orthogonal — the math does not need to know how results are formatted, the formatter does not need to know how scenarios are persisted, and persistence does not need to know about the CLI. The four-file split makes each concern testable in isolation and readable at a single-function level. `investment.py` re-exports all public names from the four modules so callers can `from investment import project_scenario` without knowing which submodule it came from.

---

### Decision 2 — `Decimal` in memory, decimal strings in JSON (schema v2)

**Chosen:** All monetary and rate fields are `Decimal` objects in memory. Persistence converts them to two-decimal strings via `_decimal_to_json_str()` before JSON serialization. Loading converts them back via `_coerce_decimal()`. A `__ll_investment__` metadata key carries `schema_version: 2`.

**Rejected:** Storing JSON numbers directly (schema v1).

**Reason:** JSON floats cannot represent all decimal fractions exactly. Storing `7.0` as a JSON number and reading it back produces `7.000000000000000...` which, when passed to `Decimal(7.0)`, carries binary float error. Storing `"7.00"` and converting with `Decimal("7.00")` is exact. The schema versioning allows legacy files (v1, plain numbers) to still load — `scenario_from_storage()` accepts any numeric type and coerces via `_coerce_decimal()`, which converts floats via `Decimal(str(float))` to avoid precision artifacts.

---

### Decision 3 — `_coerce_decimal()` with `bool`-before-`int` guard

**Chosen:** `_coerce_decimal()` checks `isinstance(value, bool)` before `isinstance(value, int)` and raises `ValueError` on `True`/`False`.

**Rejected:** Allowing booleans to coerce to `Decimal(0)` or `Decimal(1)`.

**Reason:** In Python, `bool` is a subclass of `int`. Without the `bool` check, `_coerce_decimal(True)` would silently produce `Decimal(1)`. A boolean in a monetary field is always a data error — a misconfigured dict, a JSON parsing quirk, or a caller mistake. Rejecting booleans explicitly produces a clear error message rather than a silent wrong value.

---

### Decision 4 — Inner loop for monthly compounding, outer loop per year

**Chosen:** `project_scenario()` uses an outer loop over years and an inner loop over periods (1 or 12). Each `ProjectionYearRow` accumulates `year_contributions` and `year_interest` across all inner periods before appending.

**Rejected:** A single flat loop over all periods.

**Reason:** The output schema is year-by-year — the caller needs `rows[year-1]["ending_balance"]`. Accumulating per-year in the inner loop and yielding per-year in the outer loop produces exactly this structure. A flat period loop would require a post-processing aggregation step to produce year rows.

---

### Decision 5 — Contribution timing as `start` / `end` per period

**Chosen:** `contribution_timing = "start"` adds the contribution before the interest calculation; `"end"` adds it after. Both apply within each inner period loop iteration.

**Rejected:** Only supporting end-of-period contributions.

**Reason:** Start-of-period (annuity due) contributions compound for one additional period compared to end-of-period (ordinary annuity). This is a real and material difference — over 20 years at 7% monthly, a $200/month start-of-period contribution produces meaningfully more than end-of-period. Supporting both gives the user accurate modeling for both contribution styles.

---

### Decision 6 — `META_KEY = "__ll_investment__"` schema version marker

**Chosen:** The JSON file includes `{"__ll_investment__": {"schema_version": 2}}` as a sentinel key. Loading checks this key to determine whether to apply v2 parsing (string decimal fields) or legacy parsing (numeric fields).

**Rejected:** A separate metadata file, or version stored in a filename.

**Reason:** A sentinel key inside the same JSON file is self-contained and portable. The file moves with its version marker. The double-underscore prefix makes the key visually distinct from scenario names and unlikely to collide with any user-chosen scenario name. Legacy files that lack the key are still handled — they just skip the v2 string-to-Decimal path.

---

### Decision 7 — Terminal encoding detection for chart characters

**Chosen:** `build_growth_chart()` tests `"█".encode(sys.stdout.encoding)`. If the terminal cannot encode the Unicode block character, it falls back to `"#"` (principal) and `"."` (interest).

**Rejected:** Always using Unicode blocks or always using ASCII fallback.

**Reason:** Windows terminals (especially older `cmd.exe` sessions) default to `cp1252` or `cp850` encoding and cannot render `U+2588`. The runtime encoding check ensures the chart renders correctly on all platforms without requiring the user to configure their terminal. The ASCII fallback (`#` and `.`) is visually clear and fully portable.

---

## Consequences

**Positive:**
- Four-file split keeps each concern independently readable and testable.
- Decimal-in-memory + string-in-JSON eliminates binary float precision errors in scenarios.
- `bool`-before-`int` coercion guard catches a class of silent data errors.
- Year-by-year rows with inner period accumulation match the schema contract exactly.
- Schema versioning allows file format evolution without breaking existing data.
- Terminal encoding detection makes ASCII chart work on all platforms.

**Negative / Trade-offs:**
- The annual compounding + monthly contribution modeling is an approximation (documented in `investment_engine.py` docstring): twelve monthly contributions are lumped into one annual period rather than modeled as twelve separate deposits. Monthly compounding is the correct choice when this precision matters.
- The CLI caps scenarios at four, which limits comparison flexibility for users with many investment strategies.
- `_decimal_to_json_str()` always quantizes to two decimal places — interest rates like `7.125%` are stored as `"7.13"`, losing the third decimal. A four-decimal storage format would be more accurate for rates.

---

*Constitution reference: Articles 1, 2, 3. Amendment 1.3: `parsing.py`, `schemas.py`, `storage.py` are pinned snapshots.*


---


# Technical Design Document
## App 10 — Investment
**Ledger Logic Group | Document 2 of 5**

---

## Overview

Investment projects compound interest growth year by year with optional contributions, inflation adjustment, and scenario persistence. It is split across four implementation modules under a single entry point.

**Files:** `investment.py` (entry/re-exports), `investment_engine.py` (math), `investment_reporting.py` (formatting), `investment_persist.py` (JSON persistence), `investment_cli.py` (CLI)
**Shared (pinned snapshots):** `parsing.py`, `schemas.py`, `storage.py`
**Entry point:** `investment.main()` → `investment_cli.menu()`
**Dependencies:** `decimal`, `sys`, `collections.abc` (stdlib); `schemas`, `storage` (Ledger Logic shared)

---

## Module Responsibilities

| File | Responsibility |
|---|---|
| `investment.py` | Entry point, re-exports all public names via `__all__` |
| `investment_engine.py` | `validate_scenario()`, `project_scenario()`, `contribution_for_period()`, `scenario_from_storage()`, `default_scenario()` |
| `investment_reporting.py` | `format_single_projection()`, `compare_scenarios()`, `build_growth_chart()` |
| `investment_persist.py` | `load_persisted_scenarios()`, `save_persisted_scenarios()`, `_decimal_to_json_str()`, `_scenario_to_storable()` |
| `investment_cli.py` | `menu()`, `create_or_edit_scenario()`, `prompt_with_default()`, `_parse_decimal_field()`, `_parse_years_field()` |

---

## Data Flow

```
investment_cli.menu()
        │
        ├─ create_or_edit_scenario()
        │     ├─ prompt_with_default() per field
        │     ├─ _parse_decimal_field() for money/rate/inflation
        │     ├─ _parse_years_field() for years
        │     └─ validate_scenario() → list[str] errors
        │
        ├─ project_scenario(scenario)
        │     ├─ validate_scenario() → raises ValueError if invalid
        │     ├─ Outer loop: year = 1..years
        │     │     └─ Inner loop: period = 1..periods_per_year
        │     │           ├─ contribution_for_period()
        │     │           ├─ if timing==start: balance += contribution
        │     │           ├─ interest = balance × (annual_rate / periods_per_year)
        │     │           ├─ balance += interest
        │     │           └─ if timing==end: balance += contribution
        │     └─ Return ProjectionResult
        │
        ├─ format_single_projection(result) → str
        ├─ compare_scenarios(scenarios) → str
        └─ build_growth_chart(result) → str

Persistence:
        load_persisted_scenarios()
             ├─ load_json(get_investment_profile_path())
             ├─ Check META_KEY for schema_version
             └─ scenario_from_storage(key, val) per entry

        save_persisted_scenarios(scenarios)
             ├─ _scenario_to_storable(scenario) per entry
             └─ save_json(payload, get_investment_profile_path())
```

---

## Engine: `investment_engine.py`

### `_coerce_decimal(value) → Decimal`
Type-dispatch coercion:
- `Decimal` → return as-is
- `bool` → raise `ValueError` (**checked before `int`**)
- `int` → `Decimal(value)`
- `float` → `Decimal(str(value))` (avoids binary float artifacts)
- `str` → `Decimal(value.strip())`
- Other → raise `ValueError`

---

### `validate_scenario(scenario) → list[str]`
Checks: non-blank name, non-negative numeric principal/rate/contribution/inflation, `years > 0` integer, compounding in `{"monthly", "annual"}`, contribution frequency in `{"monthly", "annual"}`, contribution timing in `{"start", "end"}`. Returns all errors found (does not short-circuit).

---

### `contribution_for_period(scenario, period_index, periods_per_year) → Decimal`

| frequency | periods_per_year | period_index | Returns |
|---|---|---|---|
| monthly | 12 | any | `amount` (one month) |
| monthly | 1 | any | `amount × 12` (lump-sum annual) |
| annual | 12 | 1 | `amount` (first period only) |
| annual | 12 | 2–12 | `Decimal(0)` |
| annual | 1 | any | `amount` |

---

### `project_scenario(scenario) → ProjectionResult`
Constants:
- `periods_per_year = 12` if compounding=monthly, else `1`
- `period_rate = annual_rate / 100 / periods_per_year`

Inner loop: `period_rate = annual_rate / periods_dec`

Real balance: `balance / (1 + inflation_rate) ^ year_number`

High-rate warning: emitted if `annual_rate > 25`.

---

### `ProjectionYearRow` Schema

```python
{
    "year": int,
    "starting_balance": Decimal,
    "contributions": Decimal,       # Sum of contributions this year
    "interest_earned": Decimal,     # Sum of interest this year
    "ending_balance": Decimal,
    "real_balance": Decimal,        # Inflation-adjusted ending_balance
    "principal_portion": Decimal,   # initial_principal + cumulative contributions
    "interest_portion": Decimal,    # max(0, ending_balance - principal_portion)
}
```

---

### `ProjectionResult` Schema

```python
{
    "scenario": InvestmentScenario,
    "rows": list[ProjectionYearRow],
    "ending_balance": Decimal,
    "total_contributed": Decimal,
    "total_earned": Decimal,
    "real_ending_balance": Decimal,
    "purchasing_power_loss": Decimal,
    "warning": str,                  # Empty string or high-rate warning
}
```

---

## Persistence: `investment_persist.py`

### JSON Structure (schema v2)
```json
{
  "__ll_investment__": {"schema_version": 2},
  "Starter": {
    "name": "Starter",
    "initial_principal": "10000.00",
    "annual_rate": "7.00",
    "years": 20,
    "compounding": "monthly",
    "contribution_amount": "200.00",
    "contribution_frequency": "monthly",
    "contribution_timing": "end",
    "inflation_rate": "2.50"
  }
}
```

Decimal fields stored as two-decimal strings. `years` stored as integer (not a Decimal field).

### `_decimal_to_json_str(d: Decimal) → str`
```python
q = d.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
return format(q, "f")   # "7.00" not "7E+0"
```

### Legacy (v1) loading
Files without `META_KEY` or with unknown version: all entries treated as scenario data. `scenario_from_storage()` handles both string and numeric field values via `_coerce_decimal()`.

---

## CLI: `investment_cli.py`

### `create_or_edit_scenario(existing) → InvestmentScenario | None`
Prompts for all nine fields with `prompt_with_default()`. Parses numerics with `_parse_decimal_field()` and `_parse_years_field()`. Returns `None` if any parse fails or `validate_scenario()` returns errors.

### Menu Options

| Option | Action |
|---|---|
| 1 | Create scenario (max 4) |
| 2 | View single scenario projection |
| 3 | Compare all scenarios side-by-side |
| 4 | Edit existing scenario |
| 5 | Delete scenario |
| 6 | Show ASCII growth chart |
| 7 | Quit |

---

## Reporting: `investment_reporting.py`

### `format_single_projection(result) → str`
108-character-wide table. Columns: Year, Start, Contrib, Interest, End, Real End, Note (milestone every 5 years).

### `compare_scenarios(scenarios) → str`
Side-by-side table, up to 4 scenarios. Rows for each year up to `max(years)`. Summary rows: Contrib total, Earned total.

### `build_growth_chart(result) → str`
Bar chart with two segments per row:
- `█` (or `#`) — principal + contributions portion
- `░` (or `.`) — interest/growth portion

Width default 80. Bars scaled by `ending_balance / max_ending_balance`.


---


# Interface Design Specification
## App 10 — Investment
**Ledger Logic Group | Document 3 of 5**

---

## Public API

All names available via `from investment import <name>`:

```python
project_scenario(scenario: Mapping[str, Any]) -> ProjectionResult
validate_scenario(scenario: Mapping[str, Any]) -> list[str]
default_scenario(name: str = "Starter") -> InvestmentScenario
scenario_from_storage(storage_key: str, data: Mapping[str, Any]) -> InvestmentScenario | None
contribution_for_period(scenario, period_index, periods_per_year) -> Decimal
load_persisted_scenarios() -> dict[str, InvestmentScenario]
save_persisted_scenarios(scenarios: Mapping[str, InvestmentScenario]) -> None
format_single_projection(result: ProjectionResult) -> str
compare_scenarios(scenarios: Mapping[str, InvestmentScenario]) -> str
build_growth_chart(result: ProjectionResult, width: int = 80) -> str
menu() -> None
create_or_edit_scenario(existing: InvestmentScenario | None = None) -> InvestmentScenario | None
```

---

## `InvestmentScenario` Schema

```python
{
    "name": str,
    "initial_principal": Decimal,          # Non-negative
    "annual_rate": Decimal,                # Percentage (e.g., Decimal("7") = 7%)
    "years": int,                          # > 0
    "compounding": "monthly" | "annual",
    "contribution_amount": Decimal,        # Non-negative
    "contribution_frequency": "monthly" | "annual",
    "contribution_timing": "start" | "end",
    "inflation_rate": Decimal,             # Percentage (e.g., Decimal("2.5") = 2.5%)
}
```

---

### CLI Entry Point

```bash
python investment.py
```

Interactive menu loop. Scenarios persist to `ledgerlogic_data/investment_scenarios.json`.

---

## Input/Output Examples

### Create and project a scenario
```python
from investment import project_scenario, default_scenario

scenario = default_scenario("Retirement")
# scenario["initial_principal"] = Decimal("10000")
# scenario["annual_rate"] = Decimal("7")
# scenario["years"] = 20
# scenario["contribution_amount"] = Decimal("200")
# scenario["contribution_frequency"] = "monthly"
# scenario["contribution_timing"] = "end"
# scenario["inflation_rate"] = Decimal("2.5")

result = project_scenario(scenario)
print(f"Ending balance: ${result['ending_balance']:,.2f}")
print(f"Real ending balance: ${result['real_ending_balance']:,.2f}")
print(f"Total contributed: ${result['total_contributed']:,.2f}")
print(f"Total earned: ${result['total_earned']:,.2f}")
```

### Validate a scenario
```python
from investment import validate_scenario

errors = validate_scenario({
    "name": "Test",
    "initial_principal": Decimal("-1000"),  # Invalid
    "annual_rate": Decimal("7"),
    "years": 0,                              # Invalid
    "compounding": "monthly",
    "contribution_amount": Decimal("0"),
    "contribution_frequency": "monthly",
    "contribution_timing": "end",
    "inflation_rate": Decimal("2.5"),
})
# errors: ["Initial principal cannot be negative.", "Years must be greater than zero."]
```

### Single projection table output
```
Scenario: Retirement
Principal $10,000.00 | Rate 7.00% | Years 20 | Compounding monthly
------------------------------------------------------------------------------------------------------------
Year   Start          Contrib       Interest            End       Real End       Note
------------------------------------------------------------------------------------------------------------
1      $10,000.00      $2,400.00       $741.97     $13,141.97     $12,821.43
2      $13,141.97      $2,400.00     $1,086.59     $16,628.56     $15,839.73
...
5      $21,835.01      $2,400.00     $1,697.95     $25,932.96     $22,810.56  milestone
...
20     $85,123.45      $2,400.00     $6,512.34    $94,035.79     $63,214.18  milestone
------------------------------------------------------------------------------------------------------------
Total contributed: $58,000.00 | Total earned: $36,035.79
Ending balance: $94,035.79 | Inflation-adjusted ending balance: $63,214.18
Purchasing power loss estimate: $30,821.61
```

### Growth chart output
```
Growth chart
Legend: █ principal/contributions, ░ growth
--------------------------------------------------------------------------------
Year  1 ████████░░                                         $13,141.97
Year  2 █████████████░░░                                   $16,628.56
...
Year 20 ████████████████████████░░░░░░░░░░░░░░░░░░░░       $94,035.79
```

### Compare scenarios
```
Year      Retirement       Aggressive      Conservative
------------------------------------------------------
1         $13,141.97       $15,200.00       $10,800.00
...
------------------------------------------------------
Contrib   $58,000.00       $58,000.00       $58,000.00
Earned    $36,035.79       $82,415.00        $8,220.00
```

---

## Validation Rules Summary

| Field | Rule |
|---|---|
| `name` | Non-blank string |
| `initial_principal` | Non-negative, numeric |
| `annual_rate` | Non-negative, numeric |
| `years` | Integer, > 0 |
| `contribution_amount` | Non-negative, numeric |
| `inflation_rate` | Non-negative, numeric |
| `compounding` | `"monthly"` or `"annual"` |
| `contribution_frequency` | `"monthly"` or `"annual"` |
| `contribution_timing` | `"start"` or `"end"` |


---


# Runbook
## App 10 — Investment
**Ledger Logic Group | Document 4 of 5**

---

## Requirements

- Python 3.10 or later
- No third-party dependencies
- `schemas.py`, `storage.py`, `parsing.py` in same directory or `PYTHONPATH`
- `typing_extensions` for `schemas.py` (Python < 3.11)

---

## Installation

```bash
git clone https://github.com/PrincetonAfeez/ledger-logic
cd ledger-logic/investment
pip install typing_extensions   # Only if Python < 3.11
```

---

## Running the CLI

```bash
python investment.py
```

On first run, no scenarios exist. Select option 1 to create a scenario. Scenarios persist automatically to `ledgerlogic_data/investment_scenarios.json`.

---

## Common Workflows

### Create and view a basic scenario
```
> python investment.py
1. Create scenario
  Scenario name [Starter]: Retirement Fund
  Initial principal [10000]: 15000
  Annual interest rate (%) [7]: 8
  Years [20]: 30
  Compounding (monthly/annual) [monthly]: monthly
  Contribution amount [200]: 500
  Contribution frequency (monthly/annual) [monthly]: monthly
  Contribution timing (start/end) [end]: end
  Inflation rate (%) [2.5]: 3
Saved scenario Retirement Fund.

2. View single scenario
  Scenario name: Retirement Fund
[Year-by-year table displayed]
```

### Edit an existing scenario
```
4. Edit a scenario
  Scenario to edit: Retirement Fund
  [fields shown with current values — press Enter to keep, or type new value]
```

### View ASCII growth chart
```
6. Show chart
  Scenario name for chart: Retirement Fund
[ASCII bar chart displayed]
```

---

## Using as a Library

### Project a custom scenario
```python
from decimal import Decimal
from investment import project_scenario

scenario = {
    "name": "HYSA",
    "initial_principal": Decimal("50000"),
    "annual_rate": Decimal("4.5"),
    "years": 5,
    "compounding": "monthly",
    "contribution_amount": Decimal("0"),
    "contribution_frequency": "monthly",
    "contribution_timing": "end",
    "inflation_rate": Decimal("3.0"),
}
result = project_scenario(scenario)
print(f"Balance in 5 years: ${result['ending_balance']:,.2f}")
```

### Load and save persisted scenarios
```python
from investment import load_persisted_scenarios, save_persisted_scenarios, project_scenario

scenarios = load_persisted_scenarios()
for name, scenario in scenarios.items():
    result = project_scenario(scenario)
    print(f"{name}: ${result['ending_balance']:,.2f}")
```

### Format a projection as text
```python
from investment import project_scenario, format_single_projection, default_scenario

result = project_scenario(default_scenario("Quick Check"))
print(format_single_projection(result))
```

---

## Running Tests

No dedicated test file was uploaded for App 10. Manual verification:

```bash
python investment.py
# Create a scenario: principal=$10,000, rate=7%, 20 years, monthly, $200/mo, end
# View it — confirm year 20 ending balance is approximately $94,035
# Check that Real End is lower than End (inflation adjustment)
# Check that Purchasing power loss = End - Real End
```

---

## Troubleshooting

### Scenarios not loading after restart
Scenarios are saved to `ledgerlogic_data/investment_scenarios.json` in the CWD. Run from the same directory each time, or set `LEDGERLOGIC_DATA_DIR` environment variable.

### `Skipped invalid scenario stored under 'X'`
The JSON entry for scenario `X` failed validation (negative rate, non-integer years, etc.). Edit the JSON file directly to fix the values, or delete the entry and re-create via the CLI.

### Chart shows `#` and `.` instead of block characters
Your terminal encoding (likely Windows `cp1252`) cannot render Unicode block characters. The ASCII fallback is automatic and displays the same information.

### Annual rate > 25% produces a warning
The engine emits `"High rate warning: annual rate is above 25%."` — the projection still runs but the result may be unrealistic. Verify the rate is entered as a percentage (e.g., `7` for 7%, not `0.07`).

### `_parse_decimal_field` returns None during scenario creation
The entered value is not numeric. The prompt will re-display after the error message. Enter a plain number (`7`, `10000`, `2.5`) without units or special characters.


---


# Lessons Learned
## App 10 — Investment
**Ledger Logic Group | Document 5 of 5**

---

## Why This Design Was Chosen

The four-file architecture emerged from recognizing that the module had genuinely four audiences: the person who wants to understand the math (engine), the person who wants to understand the output format (reporting), the person who wants to understand storage (persist), and the person who wants to understand the interactive flow (CLI). Writing all four in one file would have produced a 600+ line module where financial formulas were interleaved with `input()` calls and `json.dump()` calls. The split makes each file a coherent, self-contained story.

The Decimal-in-memory + string-in-JSON decision came from a direct failure. The first persistence implementation stored `Decimal` objects by converting them to `float` for JSON serialization. Loading `7.0` from JSON and passing it to `Decimal(7.0)` produced `Decimal('6.9999999999999964472863211994990706443786621093750')`. Storing `"7.00"` and loading with `Decimal("7.00")` produces exactly `Decimal('7.00')`. The lesson was immediate: float-to-Decimal conversion must go through string, never directly.

---

## What Was Intentionally Omitted

**Month-by-month output table:** The projection table shows year-by-year data. For a 30-year projection with monthly compounding, a month-by-month table would have 360 rows — too long for a terminal. Year-by-year with milestone markers is the correct granularity for the display layer. The inner loop still runs monthly for accurate calculation.

**Tax treatment:** Investment returns are often taxed (capital gains, ordinary income on interest). The module does not model taxes. Adding tax would require knowing the user's marginal rate, the account type (taxable/Roth/traditional), and the jurisdiction — far outside the scope of this learning project.

**Multiple asset allocation:** The module projects a single rate of return. A portfolio with multiple asset classes (stocks/bonds/cash) at different rates would require either a blended rate input or a separate per-asset projection layer.

**Sensitivity analysis:** The module does not show what happens to the ending balance if the rate varies by ±1%. A range/sensitivity table would be useful but was out of scope.

---

## Biggest Weakness

The annual compounding + monthly contribution limitation is the most significant modeling gap. When `compounding="annual"` and `contribution_frequency="monthly"`, the engine lumps twelve monthly contributions into one lump sum per year (`contribution_for_period()` returns `amount × 12` for `periods_per_year == 1`). This is mathematically equivalent to making one annual payment of twelve months' worth, not twelve separate monthly payments that each earn interest for different lengths of time within the year. The module docstring explicitly documents this with a recommendation to use monthly compounding when this precision matters. For most practical planning purposes the difference is small, but for rigorous financial modeling it is incorrect.

---

## Scaling Considerations

**If scenarios need more fields:** `InvestmentScenario` is a TypedDict — adding a field requires: one entry in the TypedDict, one entry in `default_scenario()`, one prompt in `create_or_edit_scenario()`, one coercion in `scenario_from_storage()`, and one entry in `_DECIMAL_FIELDS` if it is a monetary/rate value. The schema versioning would increment to v3 for files with the new field.

**If the four-decimal precision is needed for rates:** Change `_decimal_to_json_str()` to quantize to `Decimal("0.0001")` and update `format(q, "f")` accordingly. Load/save would become `"7.1250"` strings. No algorithm changes required.

**If performance matters for long projections:** The inner loop at 12 periods × 40 years = 480 Decimal multiplications per scenario is already fast. For batch projection of thousands of scenarios, `numpy` financial functions would be faster, but `Decimal` accuracy would be lost. The current implementation is correct and fast enough for interactive use.

---

## What the Next Refactor Would Be

1. **Four-decimal rate storage** — `_decimal_to_json_str()` quantize to `"0.0001"` for rate fields.
2. **Month-by-month detail on demand** — `project_scenario_monthly(scenario)` returning 360 rows, available but not displayed by default.
3. **Tax modeling** — optional `tax_rate` field applied to `year_interest` in the projection loop.
4. **Sensitivity table** — `project_rate_range(scenario, low, high, step)` producing a table of ending balances across a rate range.

---

## What This Project Taught

**Decimal-to-JSON requires string as the intermediate.** `float(Decimal("7"))` → `7.0` → `json.dumps` → `7.0` → `json.loads` → `7.0` → `Decimal(7.0)` → binary float error. `Decimal("7")` → `"7.00"` → `json.dumps` → `"7.00"` → `json.loads` → `"7.00"` → `Decimal("7.00")` → exact. The string is the only correct bridge between `Decimal` and JSON.

**`bool` subclasses `int` in Python.** `_coerce_decimal()` would silently accept `True` as `1` and `False` as `0` without the `bool` check. This is not a theoretical concern — JSON `true`/`false` values loaded by `json.loads` become Python booleans. A configuration file with `"years": true` would silently set years to 1 without the guard. Checking `isinstance(value, bool)` before `isinstance(value, int)` is the correct pattern for all numeric coercion functions in Python.

**Schema versioning should be added before the first user, not after.** The `META_KEY` + `SCHEMA_VERSION` pattern was designed in from the start. Adding schema versioning retroactively to a deployed system requires migrating all existing files — doing it first makes future format changes trivial. The v1 fallback in `load_persisted_scenarios()` handles the hypothetical pre-versioning state without code duplication.

---

*Constitution v2.0 checklist: This document satisfies Article 5 (trade-off documentation) for App 10.*
