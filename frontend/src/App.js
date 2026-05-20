import { jsx as _jsx, jsxs as _jsxs } from "react/jsx-runtime";
import { useState } from "react";
import { DocChatPage } from "./components/DocChatPage";
import { PredictorPage } from "./components/PredictorPage";
const TABS = [
    {
        id: "predictor",
        label: "Cost predictor",
        description: "ML model trained on the Kaggle insurance dataset. Adjust your details to see annual charges with an 80% interval and what you would actually pay on a chosen plan.",
    },
    {
        id: "docchat",
        label: "Document chat",
        description: "Upload a plan PDF (Summary of Benefits and Coverage, plan documents, anything). Ask questions in plain English; the chatbot retrieves the relevant passages and cites the page they came from.",
    },
];
export default function App() {
    const [tab, setTab] = useState("predictor");
    const active = TABS.find((t) => t.id === tab);
    return (_jsxs("div", { className: "mx-auto max-w-6xl px-6 py-10", children: [_jsxs("header", { className: "mb-6", children: [_jsx("h1", { className: "text-3xl font-semibold tracking-tight text-slate-900", children: "Health app" }), _jsx("nav", { className: "mt-4 inline-flex rounded-md border border-slate-300 bg-white p-0.5", children: TABS.map((t) => {
                            const selected = t.id === tab;
                            return (_jsx("button", { type: "button", onClick: () => setTab(t.id), className: "rounded px-4 py-1.5 text-sm transition " +
                                    (selected
                                        ? "bg-brand-600 text-white"
                                        : "text-slate-700 hover:bg-slate-100"), children: t.label }, t.id));
                        }) }), _jsx("p", { className: "mt-3 max-w-3xl text-sm text-slate-600", children: active.description }), _jsx("p", { className: "mt-2 max-w-3xl text-xs text-slate-500", children: "Illustrative prototype. Not a substitute for an actual insurance quote or for advice from your insurer." })] }), tab === "predictor" ? _jsx(PredictorPage, {}) : _jsx(DocChatPage, {}), _jsxs("footer", { className: "mt-10 text-xs text-slate-500", children: ["Backend at", " ", _jsx("code", { className: "rounded bg-slate-100 px-1.5 py-0.5", children: import.meta.env.VITE_API_BASE ?? "http://localhost:8000" }), ". Set ", _jsx("code", { children: "VITE_API_BASE" }), " at build time to point elsewhere."] })] }));
}
