/**
 * Tiny typed client for the health-app FastAPI backend.
 *
 * The base URL is read from the VITE_API_BASE env var at build time so
 * the same bundle can be pointed at a local dev backend or a deployed
 * one without code changes.
 */
const BASE = import.meta.env.VITE_API_BASE ?? "http://localhost:8000";
async function postJSON(path, body) {
    const res = await fetch(`${BASE}${path}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
    });
    if (!res.ok) {
        const detail = await res.text();
        throw new Error(`${res.status} ${res.statusText}: ${detail}`);
    }
    return res.json();
}
async function getJSON(path) {
    const res = await fetch(`${BASE}${path}`);
    if (!res.ok) {
        throw new Error(`${res.status} ${res.statusText}`);
    }
    return res.json();
}
export function predict(features, planId) {
    return postJSON("/predict", {
        features,
        plan_id: planId ?? null,
    });
}
export function whatif(baseline, feature, values, planId) {
    return postJSON("/whatif", {
        baseline,
        feature,
        values,
        plan_id: planId ?? null,
    });
}
export function getPlan(planId) {
    return getJSON(`/plans/${encodeURIComponent(planId)}`);
}
export async function uploadPDF(file) {
    const form = new FormData();
    form.append("file", file);
    const res = await fetch(`${BASE}/documents`, {
        method: "POST",
        body: form,
    });
    if (!res.ok) {
        const detail = await res.text();
        throw new Error(`${res.status} ${res.statusText}: ${detail}`);
    }
    return res.json();
}
export function listDocuments() {
    return getJSON("/documents");
}
export async function deleteDocument(documentId) {
    const res = await fetch(`${BASE}/documents/${encodeURIComponent(documentId)}`, { method: "DELETE" });
    if (!res.ok && res.status !== 204) {
        throw new Error(`${res.status} ${res.statusText}`);
    }
}
export function askChat(documentId, question, topK = 4) {
    return postJSON("/chat", {
        document_id: documentId,
        question,
        top_k: topK,
    });
}
export const KNOWN_PLAN_IDS = ["hdhp_silver", "ppo_gold", "ppo_platinum"];
export function centsToDollars(cents) {
    return (cents / 100).toLocaleString("en-US", {
        style: "currency",
        currency: "USD",
        maximumFractionDigits: 0,
    });
}
