import { centsToDollars, PredictResponse } from "../api";

interface ResultCardProps {
  result: PredictResponse | null;
  loading: boolean;
  error: string | null;
}

export function ResultCard({ result, loading, error }: ResultCardProps) {
  if (loading) {
    return (
      <div className="rounded-lg border border-slate-200 bg-white p-6 text-sm text-slate-500">
        Predicting...
      </div>
    );
  }
  if (error) {
    return (
      <div className="rounded-lg border border-red-200 bg-red-50 p-6 text-sm text-red-700">
        {error}
      </div>
    );
  }
  if (!result) {
    return (
      <div className="rounded-lg border border-dashed border-slate-300 bg-white p-6 text-sm text-slate-500">
        Adjust the inputs on the left and the prediction will appear here.
      </div>
    );
  }

  const { prediction, annual_plan_share } = result;

  return (
    <div className="rounded-lg border border-slate-200 bg-white p-6 shadow-sm">
      <div className="mb-4">
        <div className="text-xs font-semibold uppercase tracking-wide text-slate-500">
          Predicted annual medical charges
        </div>
        <div className="mt-1 text-3xl font-semibold text-slate-900 tabular-nums">
          {centsToDollars(prediction.predicted_charges_cents)}
        </div>
        <div className="mt-1 text-sm text-slate-600">
          80% interval:&nbsp;
          <span className="tabular-nums">
            {centsToDollars(prediction.lower_bound_cents)}
          </span>
          &nbsp;to&nbsp;
          <span className="tabular-nums">
            {centsToDollars(prediction.upper_bound_cents)}
          </span>
        </div>
      </div>

      {annual_plan_share ? (
        <div className="border-t border-slate-200 pt-4">
          <div className="text-xs font-semibold uppercase tracking-wide text-slate-500">
            On this plan, you would pay
          </div>
          <div className="mt-1 text-2xl font-semibold text-brand-700 tabular-nums">
            {centsToDollars(annual_plan_share.member_pays_cents)}
          </div>
          <dl className="mt-3 grid grid-cols-2 gap-y-1 text-sm">
            <dt className="text-slate-500">Deductible</dt>
            <dd className="tabular-nums text-right">
              {centsToDollars(annual_plan_share.deductible_applied_cents)}
            </dd>
            <dt className="text-slate-500">Coinsurance</dt>
            <dd className="tabular-nums text-right">
              {centsToDollars(annual_plan_share.coinsurance_cents)}
            </dd>
            <dt className="text-slate-500">Plan pays</dt>
            <dd className="tabular-nums text-right">
              {centsToDollars(annual_plan_share.plan_pays_cents)}
            </dd>
          </dl>
          {annual_plan_share.capped_at_oop_max && (
            <div className="mt-3 rounded bg-emerald-50 px-3 py-2 text-xs text-emerald-700">
              Out-of-pocket maximum reached; the plan absorbs the remainder.
            </div>
          )}
        </div>
      ) : (
        <div className="border-t border-slate-200 pt-4 text-sm text-slate-500">
          Pick a plan to see annual out-of-pocket.
        </div>
      )}
    </div>
  );
}
