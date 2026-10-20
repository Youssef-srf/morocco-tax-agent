"""Gross to net monthly salary for an employee, from the official rates of the year.

The LLM never computes: the agent calls this function and quotes its result.

Steps (CGI 2026):
  1. employee social contributions (CNSS, AMO), deductible under article 59-II/III;
  2. professional expenses, flat rate of article 59-I-A, on the annual gross;
  3. income tax: scale of article 73-I on the annual net taxable income;
  4. family reduction of article 74, deducted from the annual tax;
  5. the annual tax is withheld in twelve equal monthly amounts.

Out of scope for v1: tax-exempt allowances (article 57), benefits in kind,
the professions of article 59-I-B/C, pensions (article 60).
"""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal

from pydantic import BaseModel

from morocco_tax_agent.rates import Bracket, IncomeTaxRates, Rates, SocialRates, load_rates

CENT = Decimal("0.01")
MONTHS = 12


class MissingRatesError(RuntimeError):
    pass


class SalaryBreakdown(BaseModel):
    year: int
    gross_monthly: Decimal
    dependents: int
    contributions: dict[str, Decimal]  # monthly, by name
    professional_expenses: Decimal  # monthly
    net_taxable: Decimal  # monthly
    income_tax_before_reduction: Decimal  # monthly
    family_reduction: Decimal  # monthly
    income_tax: Decimal  # monthly
    net_monthly: Decimal
    social_source: str
    articles: list[str] = ["Article 59", "Article 73", "Article 74"]


def _round(value: Decimal) -> Decimal:
    return value.quantize(CENT, rounding=ROUND_HALF_UP)


def scale_tax(annual_taxable: Decimal, brackets: list[Bracket]) -> Decimal:
    """Progressive tax of article 73-I on an annual net taxable income."""
    tax, lower = Decimal(0), Decimal(0)
    for bracket in brackets:
        upper = annual_taxable if bracket.up_to is None else min(annual_taxable, bracket.up_to)
        if upper > lower:
            tax += (upper - lower) * bracket.percent / 100
        if bracket.up_to is None or annual_taxable <= bracket.up_to:
            break
        lower = bracket.up_to
    return tax


def professional_expenses(annual_gross: Decimal, rates: IncomeTaxRates) -> Decimal:
    pe = rates.professional_expenses
    if annual_gross <= pe.threshold:
        return annual_gross * pe.percent_up_to_threshold / 100
    return min(annual_gross * pe.percent_above_threshold / 100, pe.cap)


def compute_net_salary(
    gross_monthly: Decimal | float | str,
    dependents: int = 0,
    year: int = 2026,
    rates: Rates | None = None,
    social: SocialRates | None = None,
) -> SalaryBreakdown:
    """Net monthly salary of an employee paid `gross_monthly` dirhams.

    `dependents`: spouse and children counting for the family reduction (article 74).
    `social` overrides the CNSS/AMO rates of the year (used by the tests).
    """
    gross = Decimal(str(gross_monthly))
    if gross <= 0:
        raise ValueError("gross_monthly must be positive")
    if dependents < 0:
        raise ValueError("dependents must be zero or more")

    rates = rates or load_rates(year)
    social = social or rates.social
    if social is None:
        raise MissingRatesError(
            f"CNSS/AMO rates for {rates.year} are not loaded yet (rates/{rates.year}.yaml)"
        )
    it = rates.income_tax

    contributions = {
        c.name: _round(min(gross, c.monthly_cap or gross) * c.percent / 100)
        for c in social.contributions
    }
    annual_gross = gross * MONTHS
    annual_contributions = sum(contributions.values(), Decimal(0)) * MONTHS
    annual_expenses = professional_expenses(annual_gross, it)
    annual_taxable = max(annual_gross - annual_expenses - annual_contributions, Decimal(0))

    tax_before = scale_tax(annual_taxable, it.brackets)
    fr = it.family_reduction
    reduction = min(min(fr.per_dependent * dependents, fr.cap), tax_before)
    income_tax = _round((tax_before - reduction) / MONTHS)

    return SalaryBreakdown(
        year=rates.year,
        gross_monthly=_round(gross),
        dependents=dependents,
        contributions=contributions,
        professional_expenses=_round(annual_expenses / MONTHS),
        net_taxable=_round(annual_taxable / MONTHS),
        income_tax_before_reduction=_round(tax_before / MONTHS),
        family_reduction=_round(reduction / MONTHS),
        income_tax=income_tax,
        net_monthly=_round(gross - sum(contributions.values(), Decimal(0)) - income_tax),
        social_source=social.source,
    )
