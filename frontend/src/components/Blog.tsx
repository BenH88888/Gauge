/**
 * Blog page: how Gauge works.
 *
 * Covers the project motivation, system architecture, data pipeline, and
 * the conformal prediction approach — written for a technical recruiter
 * audience. Diagrams are inline SVGs so they render without any external
 * dependency.
 */

export default function Blog() {
  return (
    <div className="mx-auto max-w-3xl px-6 py-16 text-slate-800">
      {/* Header */}
      <header className="mb-14">
        <p className="mb-3 text-sm font-semibold uppercase tracking-widest text-brand-600">
          Project writeup
        </p>
        <h1 className="text-4xl font-bold leading-tight text-slate-900">
          How Gauge works
        </h1>
        <p className="mt-4 text-lg leading-relaxed text-slate-600">
          A data based cost estimator so that uncertainty is never expected.
        </p>
      </header>

      {/* ------------------------------------------------------------------ */}
      {/* 1. Motivation                                                        */}
      {/* ------------------------------------------------------------------ */}
      <section className="mb-16">
        <h2 className="mb-4 text-2xl font-semibold text-slate-900">
          Why I built this
        </h2>
        <p className="mb-4 leading-relaxed">
          I recently had to change insurances and learned firsthand how confusing it can be. You pick a plan based on
          the premium, but the premium is only part of what you actually pay.
          Deductibles, coinsurance, copays, and the out-of-pocket maximum
          interact in ways that are hard to reason about without plugging in
          real numbers. The documents are also so dense and complicated that it is hard
          to find the information that you need.
        </p>
        <p className="mb-4 leading-relaxed">
          Most cost estimators give you a single number — "you'll spend about
          $4,200 this year" — with no indication of how confident they are.
          That bothers me. Healthcare costs have a heavy right tail. A "typical"
          year and a "bad" year look very different, and a tool that collapses
          that into one figure is hiding something important.
        </p>
        <p className="leading-relaxed">
          Gauge predicts a range, not a point, and the range has a formal
          statistical guarantee: it covers the true value 80% of the time for
          anyone with your demographics. That guarantee comes from conformal
          prediction, which I'll explain below.
        </p>
      </section>

      {/* ------------------------------------------------------------------ */}
      {/* 2. System Architecture                                               */}
      {/* ------------------------------------------------------------------ */}
      <section className="mb-16">
        <h2 className="mb-4 text-2xl font-semibold text-slate-900">
          System architecture
        </h2>
        <p className="mb-6 leading-relaxed">
          The app has a React frontend with a FastAPI backend. The backend
          trains an ML model on startup (first checking if there is a cache to load), 
          then serves predictions over a REST API. Sessions are persisted in
          SQLite so estimates survive server restarts.
        </p>

        <ArchDiagram />

        <div className="mt-6 space-y-3 text-sm leading-relaxed text-slate-600">
          <p>
            <span className="font-semibold text-slate-800">Frontend (React + Vite + Tailwind).</span>{" "}
            A four-step program asks you to input demographics, upload a PDF,
            review the plan fields, and view your final estimate. The what-if chart
            lets you sweep any input and see how the prediction changes. The chatbot is there
            to answer any questions about the plan that was uploaded.
          </p>
          <p>
            <span className="font-semibold text-slate-800">FastAPI backend.</span>{" "}
            Sessions are created on step one and carry state through the flow.
            The plan extractor uses an LLM (Anthropic Claude with an
            echo stub for tests) to pull structured fields out of the uploaded PDF.
            RAG-based chat lets you ask Natural Language questions against that
            same document.
          </p>
          <p>
            <span className="font-semibold text-slate-800">SQLite persistence.</span>{" "}
            Sessions, uploaded document chunks, and saved estimates all live in
            a single WAL-mode SQLite database. Nested Pydantic models are stored
            as JSON blobs — keeps the schema flat and makes the stores easy to
            test.
          </p>
          <p>
            <span className="font-semibold text-slate-800">Anonymous identity.</span>{" "}
            The browser generates a UUID on first visit and sends it as
            an <code className="rounded bg-slate-100 px-1 py-0.5 text-xs">X-Gauge-User-Id</code> header
            on every request. No login required, but estimates are scoped to
            your browser.
          </p>
        </div>
      </section>

      {/* ------------------------------------------------------------------ */}
      {/* 3. Data pipeline                                                     */}
      {/* ------------------------------------------------------------------ */}
      <section className="mb-16">
        <h2 className="mb-4 text-2xl font-semibold text-slate-900">
          The data pipeline
        </h2>
        <p className="mb-4 leading-relaxed">
          The model trains on the{" "}
          <a
            href="https://meps.ahrq.gov/mepsweb/"
            target="_blank"
            rel="noreferrer"
            className="text-brand-600 underline underline-offset-2 hover:text-brand-700"
          >
            Medical Expenditure Panel Survey (MEPS)
          </a>
          , a nationally representative survey of American families that
          records actual out-of-pocket and total medical spending. It's the
          best public data source for this kind of model — real insurance
          claims, not simulated figures.
        </p>
        <p className="mb-6 leading-relaxed">
          The MEPS data doesn't come clean. Variable names change between
          survey years (AGE21X in 2021 → AGE22X in 2022) and  BMI lives in a
          separate Self-Administered Questionnaire file. The loader handles all of that
          with a priority-ordered candidate list for each role and an optional
          SAQ merge on the shared respondent ID.
        </p>

        <DataPipelineDiagram />

        <p className="mt-6 leading-relaxed">
          When the MEPS file isn't present, the app falls back to the Kaggle
          insurance dataset, and if that's also missing, it generates a
          deterministic synthetic dataset so there's always something to train
          on. The dataset source is hashed into the model cache filename, so
          swapping inputs forces a clean retrain instead of silently reusing
          the old model. Healthcare costdistributions are heavily right-skewed 
          the log transform makes the gradient boosting work much better in the tail.
        </p>
      </section>

      {/* ------------------------------------------------------------------ */}
      {/* 4. Conformal prediction                                              */}
      {/* ------------------------------------------------------------------ */}
      <section className="mb-16">
        <h2 className="mb-4 text-2xl font-semibold text-slate-900">
          How the prediction interval actually works
        </h2>
        <p className="mb-4 leading-relaxed">
          The model is four separate gradient-boosted regressors trained on the
          same features. Three of them are quantile regressors — they learn to
          predict the 10th, 50th, and 90th percentiles of the cost
          distribution. The fourth minimises squared error and predicts the
          mean. Showing both median and mean matters: healthcare costs are
          right-skewed, so in a bad year the mean is significantly above the
          median.
        </p>
        <p className="mb-4 leading-relaxed">
          The problem with raw quantile intervals is that they're not
          calibrated. A model trained to predict the 10th and 90th percentiles
          doesn't necessarily cover 80% of held-out data — it could be too
          narrow or too wide, and there's no guarantee it gets better as the
          dataset grows.
        </p>
        <p className="mb-6 leading-relaxed">
          Conformal Quantile Regression (CQR) fixes this. Here's the procedure:
        </p>

        <CQRDiagram />

        <ol className="mt-6 space-y-3 pl-5 text-sm leading-relaxed text-slate-600 list-decimal">
          <li>
            Hold out 20% of the data before training. The model never sees
            these rows during fitting.
          </li>
          <li>
            On the held-out set, compute a <em>nonconformity score</em> for
            each row:{" "}
            <code className="rounded bg-slate-100 px-1 py-0.5 text-xs">
              score = max(q_lo(x) − y, y − q_hi(x))
            </code>
            . If the true value was already inside the raw interval, the score
            is negative. If it fell outside, the score is positive and records
            by how much.
          </li>
          <li>
            Take the empirical quantile of those scores at level{" "}
            <code className="rounded bg-slate-100 px-1 py-0.5 text-xs">
              ⌈(n+1)·(1−α)⌉ / n
            </code>
            . Call it <em>q̂</em>. The small finite-sample correction ensures
            the guarantee holds even on small calibration sets.
          </li>
          <li>
            At prediction time, expand the raw interval symmetrically:{" "}
            <code className="rounded bg-slate-100 px-1 py-0.5 text-xs">
              [q_lo(x) − q̂, q_hi(x) + q̂]
            </code>
            . This is the conformal interval, and it's guaranteed to cover the
            true cost at least 80% of the time for any data distribution —
            no normality assumption, no parametric model.
          </li>
        </ol>

        <h3 className="mb-3 mt-10 text-lg font-semibold text-slate-900">
          Propagating the interval through the plan
        </h3>
        <p className="mb-4 leading-relaxed">
          Once I have a conformal interval on total charges, I need to convert
          it into an out-of-pocket interval under the user's actual plan. The
          plan's cost-share function — deductible, then coinsurance, capped at
          the OOP max — is monotone: higher charges never produce lower
          member cost.
        </p>
        <p className="leading-relaxed">
          Because the function is monotone, I can just apply it to the lower
          bound, median, and upper bound of the charge interval and the
          ordering is preserved. The resulting OOP interval inherits the same
          80% coverage guarantee, with no simulation required. If you've hit
          your deductible and are approaching the OOP max, the upper bound
          collapses toward the cap — the interval correctly narrows.
        </p>
      </section>

      {/* ------------------------------------------------------------------ */}
      {/* 5. Stack / closing                                                   */}
      {/* ------------------------------------------------------------------ */}
      <section className="mb-8">
        <h2 className="mb-4 text-2xl font-semibold text-slate-900">
          Stack and tooling
        </h2>
        <div className="grid grid-cols-2 gap-3 text-sm sm:grid-cols-3">
          {[
            ["ML", "scikit-learn, HistGradientBoosting"],
            ["Backend", "Python, FastAPI, Pydantic v2"],
            ["Persistence", "SQLite (WAL), joblib cache"],
            ["LLM / RAG", "Anthropic Claude, TF-IDF retrieval"],
            ["Frontend", "React, TypeScript, Vite, Tailwind"],
            ["Testing", "pytest, FastAPI TestClient"],
          ].map(([label, detail]) => (
            <div
              key={label}
              className="rounded-lg border border-slate-200 bg-white p-3 shadow-sm"
            >
              <p className="font-semibold text-slate-700">{label}</p>
              <p className="mt-0.5 text-slate-500">{detail}</p>
            </div>
          ))}
        </div>
      </section>
    </div>
  );
}

/* ============================================================================
   Inline SVG diagrams
   ============================================================================ */

/** System architecture: browser ↔ FastAPI ↔ SQLite + ML model */
function ArchDiagram() {
  return (
    <div className="overflow-x-auto rounded-xl border border-slate-200 bg-slate-50 p-4">
      <svg
        viewBox="0 0 680 280"
        xmlns="http://www.w3.org/2000/svg"
        className="mx-auto w-full max-w-2xl"
        aria-label="System architecture diagram"
      >
        {/* ── colour palette ───────────────────────────────────────────── */}
        <defs>
          <marker id="arrowhead" markerWidth="8" markerHeight="6" refX="8" refY="3" orient="auto">
            <polygon points="0 0, 8 3, 0 6" fill="#94a3b8" />
          </marker>
          <marker id="arrowhead-rev" markerWidth="8" markerHeight="6" refX="0" refY="3" orient="auto">
            <polygon points="8 0, 0 3, 8 6" fill="#94a3b8" />
          </marker>
        </defs>

        {/* ── Browser box ──────────────────────────────────────────────── */}
        <rect x="20" y="100" width="140" height="80" rx="10" fill="#eff6ff" stroke="#bfdbfe" strokeWidth="1.5" />
        <text x="90" y="132" textAnchor="middle" fontSize="11" fontWeight="600" fill="#1d4ed8">Browser</text>
        <text x="90" y="149" textAnchor="middle" fontSize="9.5" fill="#3b82f6">React + Vite</text>
        <text x="90" y="164" textAnchor="middle" fontSize="9.5" fill="#3b82f6">TypeScript</text>

        {/* ── Arrow browser ↔ FastAPI ──────────────────────────────────── */}
        <line x1="162" y1="135" x2="238" y2="135" stroke="#94a3b8" strokeWidth="1.5" markerEnd="url(#arrowhead)" />
        <line x1="238" y1="148" x2="162" y2="148" stroke="#94a3b8" strokeWidth="1.5" markerEnd="url(#arrowhead-rev)" />
        <text x="200" y="127" textAnchor="middle" fontSize="8.5" fill="#94a3b8">REST / JSON</text>

        {/* ── FastAPI box ──────────────────────────────────────────────── */}
        <rect x="240" y="60" width="200" height="164" rx="10" fill="#f0fdf4" stroke="#bbf7d0" strokeWidth="1.5" />
        <text x="340" y="88" textAnchor="middle" fontSize="11" fontWeight="600" fill="#166534">FastAPI backend</text>
        <rect x="256" y="98" width="168" height="26" rx="6" fill="#dcfce7" />
        <text x="340" y="115" textAnchor="middle" fontSize="9" fill="#166534">Session store (guided flow)</text>
        <rect x="256" y="130" width="168" height="26" rx="6" fill="#dcfce7" />
        <text x="340" y="147" textAnchor="middle" fontSize="9" fill="#166534">Plan extractor (LLM + PDF)</text>
        <rect x="256" y="162" width="168" height="26" rx="6" fill="#dcfce7" />
        <text x="340" y="179" textAnchor="middle" fontSize="9" fill="#166534">Document chat (RAG)</text>
        <rect x="256" y="194" width="168" height="20" rx="6" fill="#dcfce7" />
        <text x="340" y="208" textAnchor="middle" fontSize="9" fill="#166534">Saved-estimate CRUD</text>

        {/* ── Arrow FastAPI ↔ SQLite ────────────────────────────────────── */}
        <line x1="442" y1="135" x2="498" y2="135" stroke="#94a3b8" strokeWidth="1.5" markerEnd="url(#arrowhead)" />
        <line x1="498" y1="148" x2="442" y2="148" stroke="#94a3b8" strokeWidth="1.5" markerEnd="url(#arrowhead-rev)" />
        <text x="470" y="127" textAnchor="middle" fontSize="8.5" fill="#94a3b8">WAL</text>

        {/* ── SQLite box ───────────────────────────────────────────────── */}
        <rect x="500" y="100" width="120" height="80" rx="10" fill="#faf5ff" stroke="#e9d5ff" strokeWidth="1.5" />
        <text x="560" y="132" textAnchor="middle" fontSize="11" fontWeight="600" fill="#7e22ce">SQLite</text>
        <text x="560" y="149" textAnchor="middle" fontSize="9.5" fill="#9333ea">sessions</text>
        <text x="560" y="164" textAnchor="middle" fontSize="9.5" fill="#9333ea">documents · estimates</text>

        {/* ── Arrow FastAPI ↔ ML model ─────────────────────────────────── */}
        <line x1="340" y1="226" x2="340" y2="252" stroke="#94a3b8" strokeWidth="1.5" markerEnd="url(#arrowhead)" />

        {/* ── ML model box ─────────────────────────────────────────────── */}
        <rect x="220" y="254" width="240" height="22" rx="6" fill="#fff7ed" stroke="#fed7aa" strokeWidth="1.5" />
        <text x="340" y="269" textAnchor="middle" fontSize="9" fill="#c2410c">
          CostPredictor · 4× GBT · CQR calibration
        </text>

        {/* ── LLM cloud ────────────────────────────────────────────────── */}
        <ellipse cx="630" cy="50" rx="44" ry="24" fill="#fefce8" stroke="#fde68a" strokeWidth="1.5" />
        <text x="630" y="46" textAnchor="middle" fontSize="9" fontWeight="600" fill="#92400e">LLM API</text>
        <text x="630" y="60" textAnchor="middle" fontSize="8.5" fill="#b45309">Claude / OpenAI</text>
        <line x1="440" y1="105" x2="587" y2="60" stroke="#94a3b8" strokeWidth="1" strokeDasharray="4 3" markerEnd="url(#arrowhead)" />
      </svg>
    </div>
  );
}

/** Data pipeline: MEPS → clean → features → train / calibrate → serve */
function DataPipelineDiagram() {
  const steps = [
    { label: "MEPS HC file\n+ SAQ supplement", color: "#eff6ff", border: "#bfdbfe", text: "#1d4ed8" },
    { label: "Column\nresolution", color: "#f0fdf4", border: "#bbf7d0", text: "#166534" },
    { label: "Filter · merge\nwinsorise · log", color: "#f0fdf4", border: "#bbf7d0", text: "#166534" },
    { label: "Train 80%\nCalibrate 20%", color: "#fff7ed", border: "#fed7aa", text: "#c2410c" },
    { label: "joblib cache\n(keyed by source)", color: "#faf5ff", border: "#e9d5ff", text: "#7e22ce" },
  ];

  const W = 680;
  const boxW = 100;
  const boxH = 56;
  const gap = (W - steps.length * boxW) / (steps.length + 1);
  const y = 60;

  return (
    <div className="overflow-x-auto rounded-xl border border-slate-200 bg-slate-50 p-4">
      <svg
        viewBox={`0 0 ${W} 160`}
        xmlns="http://www.w3.org/2000/svg"
        className="mx-auto w-full max-w-2xl"
        aria-label="Data pipeline diagram"
      >
        <defs>
          <marker id="pipe-arrow" markerWidth="7" markerHeight="5" refX="7" refY="2.5" orient="auto">
            <polygon points="0 0, 7 2.5, 0 5" fill="#94a3b8" />
          </marker>
        </defs>

        {steps.map((step, i) => {
          const x = gap + i * (boxW + gap);
          const lines = step.label.split("\n");
          return (
            <g key={i}>
              {i < steps.length - 1 && (
                <line
                  x1={x + boxW}
                  y1={y + boxH / 2}
                  x2={x + boxW + gap}
                  y2={y + boxH / 2}
                  stroke="#94a3b8"
                  strokeWidth="1.5"
                  markerEnd="url(#pipe-arrow)"
                />
              )}
              <rect x={x} y={y} width={boxW} height={boxH} rx="8"
                fill={step.color} stroke={step.border} strokeWidth="1.5" />
              {lines.map((line, li) => (
                <text
                  key={li}
                  x={x + boxW / 2}
                  y={y + 20 + li * 14}
                  textAnchor="middle"
                  fontSize="9"
                  fontWeight={li === 0 ? "600" : "400"}
                  fill={step.text}
                >
                  {line}
                </text>
              ))}
            </g>
          );
        })}

        {/* Fallback note */}
        <text x={W / 2} y={148} textAnchor="middle" fontSize="9" fill="#94a3b8">
          Falls back to Kaggle CSV → synthetic dataset when MEPS is absent
        </text>
      </svg>
    </div>
  );
}

/** CQR diagram: calibration set scores → q̂ → expanded interval */
function CQRDiagram() {
  return (
    <div className="overflow-x-auto rounded-xl border border-slate-200 bg-slate-50 p-6">
      <svg
        viewBox="0 0 680 210"
        xmlns="http://www.w3.org/2000/svg"
        className="mx-auto w-full max-w-2xl"
        aria-label="Conformal quantile regression diagram"
      >
        <defs>
          <marker id="cqr-arrow" markerWidth="7" markerHeight="5" refX="7" refY="2.5" orient="auto">
            <polygon points="0 0, 7 2.5, 0 5" fill="#94a3b8" />
          </marker>
        </defs>

        {/* ── Left panel: score distribution ───────────────────────────── */}
        {/* axis */}
        <line x1="40" y1="160" x2="280" y2="160" stroke="#cbd5e1" strokeWidth="1" />
        <line x1="40" y1="30" x2="40" y2="160" stroke="#cbd5e1" strokeWidth="1" />
        <text x="160" y="185" textAnchor="middle" fontSize="9" fill="#64748b">Nonconformity score</text>
        <text x="160" y="18" textAnchor="middle" fontSize="10" fontWeight="600" fill="#334155">
          Calibration set scores
        </text>

        {/* histogram bars */}
        {[
          [55, 90, 40], [75, 110, 60], [95, 120, 70], [115, 130, 55],
          [135, 120, 45], [155, 100, 30], [175, 80, 22], [195, 55, 15],
          [215, 35, 10], [235, 18, 7],
        ].map(([bx, height, opacity], i) => (
          <rect
            key={i}
            x={bx}
            y={160 - height}
            width={16}
            height={height}
            fill={`rgba(59,130,246,${opacity / 100})`}
            stroke="#93c5fd"
            strokeWidth="0.5"
          />
        ))}

        {/* q̂ line */}
        <line x1="205" y1="32" x2="205" y2="158" stroke="#ef4444" strokeWidth="2" strokeDasharray="4 3" />
        <text x="210" y="48" fontSize="9" fontWeight="600" fill="#ef4444">q̂ (80th pct)</text>

        {/* zero line label */}
        <text x="53" y="173" fontSize="8" fill="#94a3b8">0</text>
        <line x1="96" y1="155" x2="96" y2="163" stroke="#94a3b8" strokeWidth="1" />
        <text x="96" y="173" textAnchor="middle" fontSize="8" fill="#94a3b8">inside</text>
        <text x="180" y="173" textAnchor="middle" fontSize="8" fill="#94a3b8">outside →</text>

        {/* ── Arrow in the middle ───────────────────────────────────────── */}
        <line x1="295" y1="100" x2="345" y2="100" stroke="#94a3b8" strokeWidth="1.5" markerEnd="url(#cqr-arrow)" />
        <text x="320" y="92" textAnchor="middle" fontSize="8.5" fill="#94a3b8">expand by q̂</text>

        {/* ── Right panel: raw vs conformal interval ────────────────────── */}
        <text x="520" y="18" textAnchor="middle" fontSize="10" fontWeight="600" fill="#334155">
          Prediction interval
        </text>

        {/* Raw interval */}
        <text x="400" y="52" fontSize="9" fill="#64748b">Raw (q10 – q90)</text>
        <rect x="400" y="60" width="120" height="18" rx="4" fill="#dbeafe" stroke="#93c5fd" strokeWidth="1.5" />
        <line x1="460" y1="60" x2="460" y2="78" stroke="#1d4ed8" strokeWidth="1.5" />
        <text x="460" y="92" textAnchor="middle" fontSize="8" fill="#1d4ed8">median</text>

        {/* Conformal interval */}
        <text x="383" y="122" fontSize="9" fill="#64748b">Conformal (±q̂)</text>
        <rect x="375" y="130" width="170" height="18" rx="4" fill="#dcfce7" stroke="#86efac" strokeWidth="1.5" />
        <line x1="460" y1="130" x2="460" y2="148" stroke="#166534" strokeWidth="1.5" />
        <text x="460" y="164" textAnchor="middle" fontSize="8" fill="#166534">median</text>

        {/* bracket showing expansion */}
        <line x1="375" y1="109" x2="400" y2="109" stroke="#94a3b8" strokeWidth="1" />
        <line x1="375" y1="105" x2="375" y2="113" stroke="#94a3b8" strokeWidth="1" />
        <text x="388" y="120" textAnchor="middle" fontSize="7.5" fill="#94a3b8">q̂</text>
        <line x1="520" y1="109" x2="545" y2="109" stroke="#94a3b8" strokeWidth="1" />
        <line x1="545" y1="105" x2="545" y2="113" stroke="#94a3b8" strokeWidth="1" />
        <text x="533" y="120" textAnchor="middle" fontSize="7.5" fill="#94a3b8">q̂</text>

        {/* Coverage badge */}
        <rect x="404" y="182" width="112" height="20" rx="6" fill="#f0fdf4" stroke="#86efac" strokeWidth="1.5" />
        <text x="460" y="196" textAnchor="middle" fontSize="9" fontWeight="600" fill="#166534">
          ≥ 80% coverage guaranteed
        </text>
      </svg>
    </div>
  );
}
