import { jsx as _jsx, jsxs as _jsxs } from "react/jsx-runtime";
import { centsToDollars } from "../api";
export function ResultCard({ result, loading, error }) {
    if (loading) {
        return (_jsx("div", { className: "rounded-lg border border-slate-200 bg-white p-6 text-sm text-slate-500", children: "Predicting..." }));
    }
    if (error) {
        return (_jsx("div", { className: "rounded-lg border border-red-200 bg-red-50 p-6 text-sm text-red-700", children: error }));
    }
    if (!result) {
        return (_jsx("div", { className: "rounded-lg border border-dashed border-slate-300 bg-white p-6 text-sm text-slate-500", children: "Adjust the inputs on the left and the prediction will appear here." }));
    }
    const { prediction, annual_plan_share } = result;
    return (_jsxs("div", { className: "rounded-lg border border-slate-200 bg-white p-6 shadow-sm", children: [_jsxs("div", { className: "mb-4", children: [_jsx("div", { className: "text-xs font-semibold uppercase tracking-wide text-slate-500", children: "Predicted annual medical charges" }), _jsx("div", { className: "mt-1 text-3xl font-semibold text-slate-900 tabular-nums", children: centsToDollars(prediction.predicted_charges_cents) }), _jsxs("div", { className: "mt-1 text-sm text-slate-600", children: ["80% interval:\u00A0", _jsx("span", { className: "tabular-nums", children: centsToDollars(prediction.lower_bound_cents) }), "\u00A0to\u00A0", _jsx("span", { className: "tabular-nums", children: centsToDollars(prediction.upper_bound_cents) })] })] }), annual_plan_share ? (_jsxs("div", { className: "border-t border-slate-200 pt-4", children: [_jsx("div", { className: "text-xs font-semibold uppercase tracking-wide text-slate-500", children: "On this plan, you would pay" }), _jsx("div", { className: "mt-1 text-2xl font-semibold text-brand-700 tabular-nums", children: centsToDollars(annual_plan_share.member_pays_cents) }), _jsxs("dl", { className: "mt-3 grid grid-cols-2 gap-y-1 text-sm", children: [_jsx("dt", { className: "text-slate-500", children: "Deductible" }), _jsx("dd", { className: "tabular-nums text-right", children: centsToDollars(annual_plan_share.deductible_applied_cents) }), _jsx("dt", { className: "text-slate-500", children: "Coinsurance" }), _jsx("dd", { className: "tabular-nums text-right", children: centsToDollars(annual_plan_share.coinsurance_cents) }), _jsx("dt", { className: "text-slate-500", children: "Plan pays" }), _jsx("dd", { className: "tabular-nums text-right", children: centsToDollars(annual_plan_share.plan_pays_cents) })] }), annual_plan_share.capped_at_oop_max && (_jsx("div", { className: "mt-3 rounded bg-emerald-50 px-3 py-2 text-xs text-emerald-700", children: "Out-of-pocket maximum reached; the plan absorbs the remainder." }))] })) : (_jsx("div", { className: "border-t border-slate-200 pt-4 text-sm text-slate-500", children: "Pick a plan to see annual out-of-pocket." }))] }));
}
