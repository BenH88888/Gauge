"""Bridge predicted annual charges into the benefits engine.

The benefits calculator works at the per-procedure level. To produce an
annual out-of-pocket estimate we make one simplifying assumption: treat
the predicted total charges as a single lump that hits the plan over the
year. That ignores per-visit copays (we don't know visit counts) but
captures deductible plus coinsurance behaviour accurately, which is the
dominant driver of annual cost-share for higher-spend members.

OOP interval propagation
------------------------
``apply_plan_to_annual_spend`` is monotone non-decreasing in charges: a
higher charge cannot produce a lower member OOP cost. The proof is
immediate — each of deductible_applied, coinsurance, and the OOP cap are
non-decreasing functions of charges, and the cap prevents the total from
ever decreasing.

Because the plan function is monotone, the q-th quantile of charges maps
to the q-th quantile of OOP. Concretely:

    OOP(lower_bound) ≤ OOP(median) ≤ OOP(upper_bound)

This means we can propagate a conformal charge interval ``[q_lo, q_hi]``
directly through the plan function to obtain a valid OOP interval — no
Monte-Carlo simulation needed. The marginal coverage guarantee of the
source CQR interval is inherited by the OOP interval.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from gauge.benefits.models import Plan
from gauge.predictor.model import CostPrediction


class AnnualPlanShare(BaseModel):
    """Member and plan share of a single annual charges figure.

    Parameters
    ----------
    charges_cents : int
        Gross annual charges that were distributed through the plan, in cents.
    deductible_applied_cents : int
        Portion of charges absorbed by the deductible.
    coinsurance_cents : int
        Member coinsurance paid after the deductible.
    member_pays_cents : int
        Total member responsibility (deductible + coinsurance, capped at OOP max).
    plan_pays_cents : int
        Residual paid by the plan (charges minus member responsibility).
    capped_at_oop_max : bool
        ``True`` when the member cost was capped at the plan's OOP maximum.
    """

    model_config = ConfigDict(frozen=True)

    charges_cents: int = Field(ge=0)
    deductible_applied_cents: int = Field(ge=0)
    coinsurance_cents: int = Field(ge=0)
    member_pays_cents: int = Field(ge=0)
    plan_pays_cents: int = Field(ge=0)
    capped_at_oop_max: bool = False


class OopInterval(BaseModel):
    """Conformal out-of-pocket interval derived from a CQR charge interval.

    Produced by applying the plan's cost-share function to the lower bound,
    median, and upper bound of a conformal charge prediction. Because the
    plan function is monotone non-decreasing, the coverage guarantee of
    the source CQR interval carries over to the OOP interval without any
    simulation.

    Parameters
    ----------
    lower_cents : int
        Member OOP at the lower conformal charge bound, in cents.
    median_cents : int
        Member OOP at the median charge prediction.
    upper_cents : int
        Member OOP at the upper conformal charge bound.
    coverage : float or None
        Nominal marginal coverage of the source CQR interval (e.g. ``0.80``).
        ``None`` when the source prediction was not conformal-calibrated.
    capped_at_oop_max_lower : bool
        ``True`` when the lower-bound OOP reached the plan's OOP maximum.
    capped_at_oop_max_upper : bool
        ``True`` when the upper-bound OOP reached the plan's OOP maximum.
    """

    model_config = ConfigDict(frozen=True)

    lower_cents: int = Field(ge=0)
    median_cents: int = Field(ge=0)
    upper_cents: int = Field(ge=0)
    coverage: float | None = None
    capped_at_oop_max_lower: bool = False
    capped_at_oop_max_upper: bool = False

    @property
    def width_cents(self) -> int:
        """Interval width in cents (``upper_cents - lower_cents``).

        Returns
        -------
        int
            Always non-negative because the plan function is monotone.
        """
        return self.upper_cents - self.lower_cents


def apply_plan_to_annual_spend(plan: Plan, charges_cents: int) -> AnnualPlanShare:
    """Distribute annual charges across deductible, coinsurance, and OOP cap.

    Parameters
    ----------
    plan : Plan
        The plan whose cost-share rules apply.
    charges_cents : int
        Predicted annual gross charges in cents. Must be non-negative.

    Returns
    -------
    AnnualPlanShare
        Breakdown of deductible applied, coinsurance, and total member vs.
        plan responsibility for the given annual spend.

    Raises
    ------
    ValueError
        If ``charges_cents`` is negative.
    """
    if charges_cents < 0:
        raise ValueError("charges_cents must be non-negative.")

    deductible_applied = min(charges_cents, plan.deductible_cents)
    after_deductible = charges_cents - deductible_applied
    coinsurance = round(after_deductible * plan.coinsurance_rate)
    gross_member = deductible_applied + coinsurance

    capped = False
    if gross_member > plan.out_of_pocket_max_cents:
        excess = gross_member - plan.out_of_pocket_max_cents
        # Reduce coinsurance first; deductible only if coinsurance can't absorb.
        if coinsurance >= excess:
            coinsurance -= excess
        else:
            excess -= coinsurance
            coinsurance = 0
            deductible_applied = max(0, deductible_applied - excess)
        capped = True

    member_pays = deductible_applied + coinsurance
    plan_pays = charges_cents - member_pays

    return AnnualPlanShare(
        charges_cents=charges_cents,
        deductible_applied_cents=deductible_applied,
        coinsurance_cents=coinsurance,
        member_pays_cents=member_pays,
        plan_pays_cents=plan_pays,
        capped_at_oop_max=capped,
    )


def oop_interval_from_prediction(
    plan: Plan, prediction: CostPrediction
) -> OopInterval:
    """Derive the OOP interval from a conformal charge prediction.

    Applies the plan's cost-share function monotonically to the lower bound,
    median, and upper bound of ``prediction``. The monotonicity of
    ``apply_plan_to_annual_spend`` guarantees that the resulting OOP interval
    is valid: if the true charges fall in ``[lower_bound, upper_bound]``, the
    true OOP falls in ``[lower_oop, upper_oop]``.

    Parameters
    ----------
    plan : Plan
        The plan whose cost-share rules apply.
    prediction : CostPrediction
        A fitted prediction, typically conformal-calibrated. The fields
        ``lower_bound_cents``, ``median_charges_cents``, ``upper_bound_cents``,
        and ``calibration_coverage`` are used.

    Returns
    -------
    OopInterval
        Conformal OOP interval with the same nominal coverage as
        ``prediction.calibration_coverage``.
    """
    lower_share = apply_plan_to_annual_spend(plan, prediction.lower_bound_cents)
    median_share = apply_plan_to_annual_spend(plan, prediction.median_charges_cents)
    upper_share = apply_plan_to_annual_spend(plan, prediction.upper_bound_cents)
    return OopInterval(
        lower_cents=lower_share.member_pays_cents,
        median_cents=median_share.member_pays_cents,
        upper_cents=upper_share.member_pays_cents,
        coverage=prediction.calibration_coverage,
        capped_at_oop_max_lower=lower_share.capped_at_oop_max,
        capped_at_oop_max_upper=upper_share.capped_at_oop_max,
    )
