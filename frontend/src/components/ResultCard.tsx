import { OopInterval, PredictResponse, centsToDollars } from "../api";

interface ResultCardProps {
  result: PredictResponse | null;
  loading: boolean;
  error: string | null;
}

export function ResultCard({ result, loading, error }: ResultCardProps) {
  if (loading) {
    return (
      <div className="overflow-hidden rounded-xl border border-slate-200 bg-white shadow-card">
        <div className="p-6 space-y-3">
          <div className="skeleton h-3 w-40" />
          <div className="skeleton h-10 w-56" />
          <div className="skeleton h-3 w-64" />
        </div>
        <div className="border-t border-slate-100 px-6 py-3">
          <div className="skeleton h-3 w-64" />
        </div>
      </div>
    );
  }
  if (error) {
    return (
      <div className="rounded-xl border border-red-200 bg-red-50 p-6 text-sm text-red-700">
        {error}
      </div>
    );
  }
  if (!result) {
    return (
      <div className="rounded-xl border border-dashed border-slate-300 bg-white p-6 text-sm text-slate-500">
        Adjust the inputs on the left and your prediction will appear here.
      </div>
    );
  }

  const { prediction, oop_interval } = result;

  return (
    <div className="overflow-hidden rounded-xl border border-slate-200 bg-white shadow-card">
      {/* OOP interval hero — shown when a plan is selected */}
      {oop_interval ? (
        <OopHero interval={oop_interval} />
      ) : (
        <div className="p-6">
          <div className="text-xs font-semibold uppercase tracking-wider text-slate-400">
            Predicted annual charges
          </div>
          <div className="mt-1 text-4xl font-bold tracking-tight text-slate-900 tabular-nums">
            {centsToDollars(prediction.median_charges_cents)}
          </div>
          <div className="mt-0.5 text-sm text-slate-500">
            median — select a plan to see your out-of-pocket cost
          </div>
        </div>
      )}

      {/* Charge interval footer */}
      <div className="border-t border-slate-100 bg-slate-50 px-6 py-3 text-xs text-slate-500">
        80% charge interval:{" "}
        <span className="tabular-nums font-medium text-slate-700">
          {centsToDollars(prediction.lower_bound_cents)}
        </span>{" "}
        to{" "}
        <span className="tabular-nums font-medium text-slate-700">
          {centsToDollars(prediction.upper_bound_cents)}
        </span>{" "}
        · median{" "}
        <span className="tabular-nums font-medium text-slate-700">
          {centsToDollars(prediction.median_charges_cents)}
        </span>
        {oop_interval && (
          <>
            {" "}· charges before plan cost-share
          </>
        )}
      </div>
    </div>
  );
}

/** Hero block displaying the OOP interval as the primary output. */
function OopHero({ interval }: { interval: OopInterval }) {
  return (
    <div className="p-6">
      <div className="text-xs font-semibold uppercase tracking-wider text-slate-400">
        You'll likely pay out of pocket
      </div>
      <div className="mt-2 flex items-baseline gap-2">
        <span className="text-4xl font-bold tracking-tight text-brand-600 tabular-nums">
          {centsToDollars(interval.lower_cents)}
        </span>
        <span className="text-xl font-medium text-slate-400">to</span>
        <span className="text-4xl font-bold tracking-tight text-brand-600 tabular-nums">
          {centsToDollars(interval.upper_cents)}
        </span>
      </div>
      <div className="mt-1 text-sm text-slate-500">
        80% confidence interval · median{" "}
        <span className="tabular-nums font-medium text-slate-700">
          {centsToDollars(interval.median_cents)}
        </span>
      </div>
      {(interval.capped_at_oop_max_lower || interval.capped_at_oop_max_upper) && (
        <div className="mt-3 rounded-lg bg-emerald-50 px-3 py-2 text-xs font-medium text-emerald-700">
          {interval.capped_at_oop_max_upper
            ? "Upper bound capped at your plan's out-of-pocket maximum."
            : "Upper end of the range is capped at your plan's OOP max."}
        </div>
      )}
    </div>
  );
}
