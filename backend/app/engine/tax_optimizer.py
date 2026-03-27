"""
tax_optimizer.py
================
India income tax computation (FY 2024-25) and HRA exemption utilities
for the Gaara AI Finance Engine.

Covers:
  - Old Regime & New Regime tax slabs
  - Surcharge, Health & Education Cess
  - Rebate u/s 87A
  - Section 80C, 80CCD(1B), 80D, 24(b), HRA exemption

Author : Gaara Platform – Financial Engine v1.0
Python : 3.9+
"""

from __future__ import annotations

from app.engine.utils import _round2, _success, _error


# ---------------------------------------------------------------------------
# Tax slab definitions
# ---------------------------------------------------------------------------

_OLD_REGIME_SLABS = [
    # (lower, upper, rate)  — upper=None means unlimited
    (0,         250_000,  0.00),
    (250_001,   500_000,  0.05),
    (500_001, 1_000_000,  0.20),
    (1_000_001,    None,  0.30),
]

_NEW_REGIME_SLABS_FY25 = [          # Budget 2023, applicable FY 2024-25
    (0,           300_000,  0.00),
    (300_001,     600_000,  0.05),
    (600_001,     900_000,  0.10),
    (900_001,   1_200_000,  0.15),
    (1_200_001, 1_500_000,  0.20),
    (1_500_001,      None,  0.30),
]

_SURCHARGE_RATES = [
    # (income_threshold, surcharge_rate)
    (5_000_000,  0.00),
    (10_000_000, 0.10),
    (20_000_000, 0.15),
    (50_000_000, 0.25),
    (None,       0.37),   # >5 Cr (old regime) — capped at 25% under new
]

_CESS_RATE = 0.04   # Health & Education cess


# ---------------------------------------------------------------------------
# Private computation helpers
# ---------------------------------------------------------------------------

def _compute_slab_tax(income: float, slabs: list) -> float:
    tax = 0.0
    for lower, upper, rate in slabs:
        if income <= lower:
            break
        taxable = income - lower if upper is None else min(income, upper) - lower
        taxable = max(taxable, 0)
        tax += taxable * rate
    return tax


def _marginal_relief(income: float, tax: float, threshold: float,
                     slabs: list) -> float:
    """Marginal relief: excess tax over threshold income is capped."""
    if income <= threshold:
        return tax
    tax_at_threshold = _compute_slab_tax(threshold, slabs)
    excess_income = income - threshold
    max_additional_tax = excess_income
    if (tax - tax_at_threshold) > max_additional_tax:
        return tax_at_threshold + max_additional_tax
    return tax


def _compute_surcharge(income: float, tax: float, new_regime: bool) -> float:
    if income <= 5_000_000:
        return 0.0
    if new_regime and income > 20_000_000:
        return tax * 0.25     # capped at 25% under new regime
    for threshold, rate in _SURCHARGE_RATES:
        if threshold is None or income <= threshold:
            return tax * rate
    return 0.0


# ---------------------------------------------------------------------------
# 5. India Tax Calculator (FY 2024-25)
# ---------------------------------------------------------------------------

def india_tax_calculator(
    gross_annual_income: float,
    # Old-regime deductions
    section_80c: float = 0.0,         # max ₹1,50,000
    section_80d_self: float = 0.0,    # max ₹25,000 (₹50,000 if senior)
    section_80d_parents: float = 0.0, # max ₹25,000 / ₹50,000 senior parents
    parents_senior: bool = False,
    self_senior: bool = False,         # age ≥ 60
    hra_exemption: float = 0.0,        # pre-computed HRA exemption
    standard_deduction: float = 50_000.0,  # ₹50,000 for salaried
    other_deductions_80c_cap: float = 0.0, # NPS 80CCD(1B) etc., max ₹50,000
    home_loan_interest: float = 0.0,   # Sec 24(b), max ₹2,00,000
    basic_salary: float = 0.0,         # for HRA auto-computation
    actual_hra_received: float = 0.0,
    actual_rent_paid: float = 0.0,
    metro_city: bool = False,
    new_regime: bool = False,
) -> dict:
    """
    Compute India income tax for FY 2024-25 under Old or New regime.

    OLD REGIME Deductions applied:
        • Standard deduction         : ₹50,000 (salaried)
        • Section 80C                : up to ₹1,50,000
        • Section 80CCD(1B) NPS      : up to ₹50,000
        • Section 80D (self)         : ₹25,000 / ₹50,000 (senior)
        • Section 80D (parents)      : ₹25,000 / ₹50,000 (senior parents)
        • HRA exemption              : min(actual_hra, 50%/40% of basic,
                                       rent - 10% of basic)
        • Home loan interest 24(b)   : up to ₹2,00,000

    NEW REGIME (FY 2024-25):
        • Only standard deduction ₹50,000 allowed.
        • Rebate u/s 87A up to ₹7,00,000 taxable income.

    Tax slabs, surcharge, and 4% cess applied after deductions.

    Rebate u/s 87A:
        Old: ₹12,500 if taxable ≤ ₹5,00,000
        New: ₹25,000 if taxable ≤ ₹7,00,000

    Parameters
    ----------
    gross_annual_income : float  CTC / gross annual income in INR.
    new_regime          : bool   True = New Tax Regime, False = Old Regime.
    (others)            : Deduction inputs (ignored under new regime).
    """
    # ── Edge-case guards ──────────────────────────────────────────────────
    if gross_annual_income < 0:
        return _error("INVALID_INCOME", "gross_annual_income must be >= 0.")
    if gross_annual_income == 0:
        return _success({
            "gross_income": 0,
            "taxable_income": 0,
            "total_tax": 0,
            "effective_rate_pct": 0,
            "regime": "new" if new_regime else "old",
            "note": "Zero income — no tax liability.",
        })

    deductions_detail: dict[str, float] = {}
    total_deductions = 0.0

    if new_regime:
        # New regime: only standard deduction
        std_ded = min(standard_deduction, 50_000)
        total_deductions = std_ded
        deductions_detail["standard_deduction"] = std_ded
        slabs = _NEW_REGIME_SLABS_FY25
    else:
        # ── OLD REGIME ───────────────────────────────────────────────────
        # Standard deduction
        std_ded = min(standard_deduction, 50_000)
        deductions_detail["standard_deduction"] = std_ded

        # HRA Exemption  (auto-compute if not provided)
        if hra_exemption == 0 and basic_salary > 0 and actual_hra_received > 0:
            hra_pct = 0.50 if metro_city else 0.40
            hra_exemption = min(
                actual_hra_received,
                hra_pct * basic_salary,
                actual_rent_paid - 0.10 * basic_salary,
            )
            hra_exemption = max(hra_exemption, 0)
        deductions_detail["hra_exemption"] = _round2(hra_exemption)

        # Section 80C (cap ₹1,50,000)
        ded_80c = min(section_80c, 150_000)
        deductions_detail["section_80c"] = _round2(ded_80c)

        # NPS 80CCD(1B) (cap ₹50,000)
        ded_nps = min(other_deductions_80c_cap, 50_000)
        deductions_detail["section_80ccd_1b_nps"] = _round2(ded_nps)

        # Section 80D
        limit_self = 50_000 if self_senior else 25_000
        limit_parents = 50_000 if parents_senior else 25_000
        ded_80d_self = min(section_80d_self, limit_self)
        ded_80d_parents = min(section_80d_parents, limit_parents)
        deductions_detail["section_80d_self"] = _round2(ded_80d_self)
        deductions_detail["section_80d_parents"] = _round2(ded_80d_parents)

        # Section 24(b) home loan interest
        ded_hl = min(home_loan_interest, 200_000)
        deductions_detail["home_loan_interest_24b"] = _round2(ded_hl)

        total_deductions = (
            std_ded + hra_exemption + ded_80c + ded_nps
            + ded_80d_self + ded_80d_parents + ded_hl
        )
        slabs = _OLD_REGIME_SLABS

    deductions_detail["total_deductions"] = _round2(total_deductions)
    taxable_income = max(0.0, gross_annual_income - total_deductions)

    # ── Tax Computation ──────────────────────────────────────────────────
    tax_before_rebate = _compute_slab_tax(taxable_income, slabs)

    # Marginal relief at ₹5L (old) / ₹7L (new)
    if not new_regime and taxable_income > 500_000:
        tax_before_rebate = _marginal_relief(
            taxable_income, tax_before_rebate, 500_000, slabs)

    # Rebate u/s 87A
    rebate = 0.0
    if new_regime and taxable_income <= 700_000:
        rebate = min(tax_before_rebate, 25_000)
    elif not new_regime and taxable_income <= 500_000:
        rebate = min(tax_before_rebate, 12_500)

    tax_after_rebate = max(0.0, tax_before_rebate - rebate)

    # Surcharge
    surcharge = _compute_surcharge(taxable_income, tax_after_rebate, new_regime)

    # Health & Education Cess
    cess = (tax_after_rebate + surcharge) * _CESS_RATE

    total_tax = tax_after_rebate + surcharge + cess
    effective_rate = (total_tax / gross_annual_income * 100) if gross_annual_income > 0 else 0
    marginal_rate = slabs[-1][2] * 100  # simplified: top slab rate

    # In-hand monthly (approximate)
    monthly_in_hand = _round2((gross_annual_income - total_tax) / 12)

    return _success({
        "regime": "new" if new_regime else "old",
        "fy": "2024-25",
        "gross_income": _round2(gross_annual_income),
        "deductions": deductions_detail,
        "taxable_income": _round2(taxable_income),
        "tax_breakdown": {
            "tax_on_slabs": _round2(tax_before_rebate),
            "rebate_87a": _round2(rebate),
            "tax_after_rebate": _round2(tax_after_rebate),
            "surcharge": _round2(surcharge),
            "cess_4pct": _round2(cess),
        },
        "total_tax_payable": _round2(total_tax),
        "effective_tax_rate_pct": _round2(effective_rate),
        "marginal_tax_rate_pct": _round2(marginal_rate * 100),
        "monthly_in_hand_approx": monthly_in_hand,
    })


# ---------------------------------------------------------------------------
# HRA Exemption Helper (standalone)
# ---------------------------------------------------------------------------

def hra_exemption_calculator(
    basic_salary_annual: float,
    hra_received_annual: float,
    rent_paid_annual: float,
    metro_city: bool = False,
) -> dict:
    """
    Compute HRA exemption under Section 10(13A).

    Exempt = Minimum of:
        (a) Actual HRA received
        (b) 50% of Basic (metro) OR 40% (non-metro)
        (c) Rent paid - 10% of Basic Salary

    Parameters
    ----------
    basic_salary_annual  : float  Annual basic salary.
    hra_received_annual  : float  Annual HRA component received from employer.
    rent_paid_annual     : float  Actual annual rent paid.
    metro_city           : bool   True for Delhi/Mumbai/Kolkata/Chennai.
    """
    if any(v < 0 for v in [basic_salary_annual, hra_received_annual, rent_paid_annual]):
        return _error("INVALID_INPUT", "All inputs must be >= 0.")
    if basic_salary_annual == 0:
        return _error("ZERO_BASIC", "Basic salary cannot be zero for HRA computation.")
    if rent_paid_annual == 0:
        return _success({
            "hra_exemption": 0,
            "note": "No rent paid — HRA exemption is nil.",
        })

    hra_pct = 0.50 if metro_city else 0.40
    a = hra_received_annual
    b = hra_pct * basic_salary_annual
    c = max(0.0, rent_paid_annual - 0.10 * basic_salary_annual)

    exempt = min(a, b, c)
    taxable_hra = max(0.0, hra_received_annual - exempt)

    return _success({
        "hra_received": _round2(hra_received_annual),
        "city_type": "metro" if metro_city else "non-metro",
        "components": {
            "a_actual_hra": _round2(a),
            "b_pct_of_basic": _round2(b),
            "c_rent_minus_10pct_basic": _round2(c),
        },
        "hra_exemption": _round2(exempt),
        "taxable_hra": _round2(taxable_hra),
    })