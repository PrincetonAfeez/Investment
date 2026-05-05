"""Typed public shapes for data flowing between LedgerLogic modules and the CLI.

These are documentation and static-check contracts; runtime still uses plain dicts.
"""

# PINNED SNAPSHOT — sourced from https://github.com/PrincetonAfeez/ledger-logic
# This is the original copy of schemas.py pinned at the version that passed
# the Ledger Logic evaluation. Any updates must be replicated to all repositories within Ledger Logic.


from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Literal, TypedDict

from typing_extensions import NotRequired

# --- Shared string enums (CLI / storage values) ---

CompoundingLiteral = Literal["monthly", "annual"]
ContributionFrequencyLiteral = Literal["monthly", "annual"]
ContributionTimingLiteral = Literal["start", "end"]
BudgetComparisonStatusLiteral = Literal["OVER", "UNDER", "EVEN"]
BudgetTierLiteral = Literal["Needs", "Wants", "Savings"]
BudgetComparisonTierLiteral = Literal["Needs", "Wants", "Savings", "Unknown"]
MonthlyTrendLiteral = Literal["starting point", "up", "down", "flat"]


class CategoryRule(TypedDict):
    """Merchant rule target for the categorizer."""

    category: str
    subcategory: str


class RuleMatchResult(TypedDict):
    """Output of :func:`ledgerlogic.categorizer.find_best_rule_match`."""

    category: str
    subcategory: str
    confidence: float
    match_type: str
    rule_key: str


class CategorizedRecord(TypedDict):
    """Single transaction row after classification or when loaded for analysis.

    Core dimensions are always present after normalization; optional fields appear
    after classification or when shaping rows for specific consumers.
    """

    date: str | date
    merchant: str
    amount: float
    category: str
    subcategory: NotRequired[str]
    confidence: NotRequired[float]
    match_type: NotRequired[str]


class CategorySummaryRow(TypedDict):
    """One line from :func:`ledgerlogic.categorizer.summarize_categories`."""

    category: str
    total: float
    count: int


class ClassificationResult(TypedDict):
    """Return value of :func:`ledgerlogic.categorizer.run_classification`."""

    records: list[CategorizedRecord]
    flagged: list[CategorizedRecord]
    warnings: list[str]
    summary: list[CategorySummaryRow]
    rules: dict[str, CategoryRule]


class WeekendWeekdaySummary(TypedDict):
    weekend_total: float
    weekday_total: float
    weekend_avg: float
    weekday_avg: float
    percentage_difference: float


class TimeOfMonthSplit(TypedDict):
    pre_payday_total: float
    pre_payday_count: int
    post_payday_total: float
    post_payday_count: int


class SpendingAnomalyRow(TypedDict):
    """One flagged row from :func:`ledgerlogic.analysis.metrics.detect_anomalies`."""

    date: date
    merchant: str
    amount: float
    category: str
    category_average: float
    multiple: float


class AnomalyReport(TypedDict):
    anomalies: list[SpendingAnomalyRow]
    counts: dict[str, int]
    affected_categories: set[str]


class MerchantFrequencySummaryRow(TypedDict):
    """Shape of each row from :func:`ledgerlogic.analysis.metrics.count_by_merchant`."""

    merchant: str
    count: int


class MerchantSpendSummaryRow(TypedDict):
    """Shape of each row from :func:`ledgerlogic.analysis.metrics.spend_by_merchant`."""

    merchant: str
    total: float


class DayOfWeekSpendRow(TypedDict):
    """One weekday bucket from :func:`ledgerlogic.analysis.metrics.day_of_week_breakdown`."""

    day: str
    total: float
    count: int
    average: float


class MonthlyTrendRow(TypedDict):
    """One month line from :func:`ledgerlogic.analysis.metrics.monthly_trends`."""

    month: str
    total: float
    trend: MonthlyTrendLiteral


class AnalysisReport(TypedDict):
    """Return value of :func:`ledgerlogic.analyzer.run_all_reports`."""

    record_count: int
    top_by_frequency: list[MerchantFrequencySummaryRow]
    top_by_spend: list[MerchantSpendSummaryRow]
    day_of_week: list[DayOfWeekSpendRow]
    weekend_vs_weekday: WeekendWeekdaySummary
    time_of_month: TimeOfMonthSplit
    monthly_trends: list[MonthlyTrendRow]
    anomaly_report: AnomalyReport


class GreedyTraceStep(TypedDict):
    denomination: int
    name: str
    before: int
    count: int
    after: int


class ParsedAmountToCents(TypedDict):
    """Return value of :func:`ledgerlogic.change_maker.parse_amount_to_cents`."""

    input_text: str
    cents: int
    dollars: float
    rounded: bool


class ChangeResult(TypedDict):
    """Return value of :func:`ledgerlogic.change_maker.calculate_change`.

    Parsing errors raise :class:`ValueError` before a result is returned; every
    successful return includes all keys below.
    """

    ok: bool
    cents: int
    amount: float
    rounded: bool
    breakdown: dict[int, int]
    trace: list[GreedyTraceStep]
    bill_count: int
    coin_count: int
    verification: float
    used_denominations: set[int]
    unused_denominations: set[int]
    message: str


class InvestmentScenario(TypedDict):
    """Fields expected by :func:`ledgerlogic.investment.project_scenario`."""

    name: str
    initial_principal: float
    annual_rate: float
    years: int
    compounding: CompoundingLiteral
    contribution_amount: float
    contribution_frequency: ContributionFrequencyLiteral
    contribution_timing: ContributionTimingLiteral
    inflation_rate: float


class FinancialReportParams(TypedDict):
    """Inputs for :func:`ledgerlogic.report_builder.build_financial_summary_lines`."""

    payday: int
    income: float
    monthly: float
    rate: float
    years: int
    inflation: float
    output: str | None


class ProjectionYearRow(TypedDict):
    """One year of output from :func:`ledgerlogic.investment.project_scenario`."""

    year: int
    starting_balance: float
    contributions: float
    interest_earned: float
    ending_balance: float
    real_balance: float
    principal_portion: float
    interest_portion: float


class ProjectionResult(TypedDict):
    """Return value of :func:`ledgerlogic.investment.project_scenario`."""

    scenario: InvestmentScenario
    rows: list[ProjectionYearRow]
    ending_balance: float
    total_contributed: float
    total_earned: float
    real_ending_balance: float
    purchasing_power_loss: float
    warning: str  # empty string when no high-rate warning


class BudgetCategoryProfile(TypedDict):
    """One category line inside :class:`BudgetAllocation` ``categories``."""

    tier: BudgetTierLiteral
    weight: int | float
    priority: int
    actual_spend: float
    budgeted_amount: float


class BudgetAllocation(TypedDict):
    """Return shape from ``allocate_*`` functions in :mod:`ledgerlogic.budget`."""

    strategy: str
    allocations: dict[str, float]
    categories: dict[str, BudgetCategoryProfile]
    allocated_total: float
    remaining: float
    warnings: list[str]


class BudgetComparisonRow(TypedDict):
    """One row from :func:`ledgerlogic.budget.compare_actual_to_budget`."""

    category: str
    budgeted: float
    actual: float
    difference: float
    percentage_of_budget: float | None
    status: BudgetComparisonStatusLiteral
    tier: BudgetComparisonTierLiteral
    priority: int


class BudgetComparisonResult(TypedDict):
    """Return value of :func:`ledgerlogic.budget.compare_actual_to_budget`."""

    rows: list[BudgetComparisonRow]
    overages: set[str]
    under_budget: set[str]
    total_overage: float
    total_surplus: float
    total_actual: float
    total_budgeted: float


class ReconciliationRecord(TypedDict):
    """One normalized row from a reconciliation CSV (or mock data)."""

    date: date
    merchant: str
    merchant_key: str
    amount: float
    amount_cents: int
    source_label: str
    line_number: int


class ReconciliationPair(TypedDict):
    """A source row paired with a reference row and match metadata."""

    source: ReconciliationRecord
    reference: ReconciliationRecord
    confidence: float
    reason: str
    amount_delta: float
    date_gap: int


class ReconciliationSetSummary(TypedDict):
    """Counts of (date, merchant_key) keys across source vs reference."""

    shared_keys: int
    source_only_keys: int
    reference_only_keys: int
    symmetric_difference: int


class ReconciliationReport(TypedDict):
    """Return value of :func:`ledgerlogic.reconciler.reconcile`."""

    matched: list[ReconciliationPair]
    amount_mismatch: list[ReconciliationPair]
    date_mismatch: list[ReconciliationPair]
    suspicious: list[ReconciliationPair]
    unmatched_source: list[ReconciliationRecord]
    unmatched_reference: list[ReconciliationRecord]
    set_summary: ReconciliationSetSummary
    source_total: float
    reference_total: float
    net_difference: float
    match_rate: float
    source_count: int
    reference_count: int


class DuplicateExactItem(TypedDict):
    """One exact-duplicate cluster inside a single file."""

    record: ReconciliationRecord
    count: int


class DuplicateNearItem(TypedDict):
    """Two rows with same merchant/amount and dates within the near window."""

    record: ReconciliationRecord
    next_record: ReconciliationRecord
    gap: int


class DuplicateDetectionResult(TypedDict):
    """Output of :func:`ledgerlogic.reconciler.detect_duplicates`."""

    exact: list[DuplicateExactItem]
    near: list[DuplicateNearItem]


class RunReconciliationResult(TypedDict):
    """Return value of :func:`ledgerlogic.reconciler.run_reconciliation`."""

    report: ReconciliationReport
    report_text: str
    warnings: list[str]
    duplicate_source: DuplicateDetectionResult
    duplicate_reference: DuplicateDetectionResult
    output_path: Path | None
