import { jsx as _jsx, jsxs as _jsxs } from "react/jsx-runtime";
export function Toggle({ label, value, options, onChange, }) {
    return (_jsxs("div", { className: "flex flex-col gap-1.5 text-sm", children: [_jsx("span", { className: "font-medium text-slate-700", children: label }), _jsx("div", { className: "inline-flex rounded-md border border-slate-300 bg-white p-0.5", children: options.map((opt) => {
                    const selected = opt.value === value;
                    return (_jsx("button", { type: "button", onClick: () => onChange(opt.value), className: "flex-1 rounded px-3 py-1.5 text-sm transition " +
                            (selected
                                ? "bg-brand-600 text-white"
                                : "text-slate-700 hover:bg-slate-100"), children: opt.label }, opt.value));
                }) })] }));
}
