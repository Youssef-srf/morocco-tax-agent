"""Gross to net calculator, on cases computed by hand from the CGI 2026 rules.

The CNSS/AMO rates below are SYNTHETIC (round numbers chosen to make the hand
computation easy), not the official ones: they test the mechanics. The check
against real payslips (30 cases, 1 MAD tolerance) needs the official rates.
"""

from decimal import Decimal

import pytest

from morocco_tax_agent.rates import Contribution, SocialRates, load_rates
from morocco_tax_agent.tools.salary import MissingRatesError, compute_net_salary, scale_tax

SYNTHETIC = SocialRates(
    source="synthetic test rates, not official",
    contributions=[
        Contribution(name="A", percent=Decimal(4), monthly_cap=Decimal(5000)),
        Contribution(name="B", percent=Decimal(2)),
    ],
)


def net(gross, dependents=0):
    return compute_net_salary(gross, dependents, social=SYNTHETIC)


def test_middle_salary_above_professional_expenses_threshold():
    # A = 4% of 5,000 (capped) = 200 ; B = 2% of 10,000 = 200 ; 400/month, 4,800/year
    # annual gross 120,000 > 78,000 -> expenses 25% = 30,000 (under the 35,000 cap)
    # taxable 120,000 - 30,000 - 4,800 = 85,200
    # tax 10% x 20,000 + 20% x 20,000 + 30% x 5,200 = 7,560/year = 630/month
    r = net(10_000)
    assert r.contributions == {"A": Decimal("200.00"), "B": Decimal("200.00")}
    assert r.professional_expenses == Decimal("2500.00")
    assert r.net_taxable == Decimal("7100.00")
    assert r.income_tax == Decimal("630.00")
    assert r.net_monthly == Decimal("8970.00")


def test_family_reduction_600_per_dependent():
    # same case, 2 dependents: 7,560 - 1,200 = 6,360/year = 530/month
    r = net(10_000, dependents=2)
    assert r.family_reduction == Decimal("100.00")
    assert r.income_tax == Decimal("530.00")
    assert r.net_monthly == Decimal("9070.00")


def test_low_salary_is_not_taxed():
    # annual gross 60,000 <= 78,000 -> expenses 35% = 21,000
    # taxable 60,000 - 21,000 - 3,600 = 35,400 < 40,000 -> no tax
    r = net(5_000, dependents=3)
    assert r.income_tax == 0
    assert r.family_reduction == 0  # never more than the tax itself
    assert r.net_monthly == Decimal("4700.00")


def test_high_salary_hits_expenses_cap_and_top_bracket():
    # contributions 200 + 600 = 800/month, 9,600/year
    # expenses 25% x 360,000 = 90,000 -> capped at 35,000
    # taxable 360,000 - 35,000 - 9,600 = 315,400
    # tax 2,000 + 4,000 + 6,000 + 27,200 + 37% x 135,400 (50,098) = 89,298/year
    r = net(30_000)
    assert r.professional_expenses == Decimal("2916.67")
    assert r.income_tax == Decimal("7441.50")
    assert r.net_monthly == Decimal("21758.50")


def test_family_reduction_is_capped_at_3600():
    # 7 dependents x 600 = 4,200, capped at 3,600: 89,298 - 3,600 = 85,698/year
    assert net(30_000, dependents=7).income_tax == Decimal("7141.50")
    assert net(30_000, dependents=6).income_tax == net(30_000, dependents=7).income_tax


def test_expenses_threshold_is_inclusive():
    # 6,500 x 12 = 78,000 exactly: still 35% (article 59-I-A: "n'excède pas")
    assert net(6_500).professional_expenses == Decimal("2275.00")
    assert net(6_501).professional_expenses == Decimal("1625.25")


def test_net_never_decreases_when_gross_increases():
    nets = [net(g).net_monthly for g in range(3_000, 60_001, 250)]
    assert nets == sorted(nets)


@pytest.mark.parametrize("annual, expected", [
    (40_000, 0), (60_000, 2_000), (80_000, 6_000), (100_000, 12_000), (180_000, 39_200),
])
def test_scale_at_bracket_bounds(annual, expected):
    assert scale_tax(Decimal(annual), load_rates(2026).income_tax.brackets) == expected


def test_refuses_to_compute_without_official_social_rates():
    rates = load_rates(2026)
    if rates.social is not None:
        pytest.skip("official CNSS/AMO rates are loaded")
    with pytest.raises(MissingRatesError):
        compute_net_salary(10_000)


@pytest.mark.parametrize("gross, dependents", [(0, 0), (-1, 0), (10_000, -1)])
def test_invalid_input(gross, dependents):
    with pytest.raises(ValueError):
        net(gross, dependents)
