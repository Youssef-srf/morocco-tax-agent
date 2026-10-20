"""Tax and social contribution rates, versioned by year (one YAML file per year).

The values are copied from the official texts, never written from memory,
and tests/test_rates.py finds each of them verbatim in the official text.
"""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import yaml
from pydantic import BaseModel, model_validator

RATES_DIR = Path(__file__).parent


class Bracket(BaseModel):
    up_to: Decimal | None  # None = no upper bound
    percent: Decimal


class ProfessionalExpenses(BaseModel):
    threshold: Decimal
    percent_up_to_threshold: Decimal
    percent_above_threshold: Decimal
    cap: Decimal


class FamilyReduction(BaseModel):
    per_dependent: Decimal
    cap: Decimal


class IncomeTaxRates(BaseModel):
    brackets: list[Bracket]
    professional_expenses: ProfessionalExpenses
    family_reduction: FamilyReduction

    @model_validator(mode="after")
    def brackets_are_ordered(self) -> IncomeTaxRates:
        bounds = [b.up_to for b in self.brackets]
        if bounds[-1] is not None or None in bounds[:-1]:
            raise ValueError("only the last bracket can be open-ended")
        if bounds[:-1] != sorted(bounds[:-1]):
            raise ValueError("bracket bounds must increase")
        return self


class Contribution(BaseModel):
    name: str  # "CNSS", "AMO"
    percent: Decimal  # employee share
    monthly_cap: Decimal | None = None  # None = applies to the whole gross salary


class SocialRates(BaseModel):
    source: str  # official document the rates come from
    contributions: list[Contribution]


class Rates(BaseModel):
    year: int
    income_tax: IncomeTaxRates
    social: SocialRates | None = None


def load_rates(year: int) -> Rates:
    path = RATES_DIR / f"{year}.yaml"
    if not path.exists():
        raise ValueError(f"No rates for {year}: {path.name} not found")
    return Rates.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")))
