/**
 * App — root component for Gauge.
 *
 * Renders a persistent brand header and footer. The header includes a "How it
 * works" nav link that toggles between the intake wizard and the blog page.
 * No router dependency — a single boolean state is enough for two views.
 */

import { useState } from "react";
import Blog from "./components/Blog";
import { IntakeWizard } from "./components/IntakeWizard";

/** Shield-plus brand mark used in the header. */
function BrandIcon() {
  return (
    <svg
      viewBox="0 0 32 32"
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
      className="h-8 w-8 flex-shrink-0"
      aria-hidden="true"
    >
      <rect width="32" height="32" rx="8" fill="#2563eb" />
      <path
        d="M16 6 L24 9.5 V17 C24 21.5 20.5 25 16 26 C11.5 25 8 21.5 8 17 V9.5 Z"
        fill="white"
        fillOpacity="0.18"
        stroke="white"
        strokeWidth="1.4"
        strokeLinejoin="round"
      />
      <path
        d="M16 12 V20 M12 16 H20"
        stroke="white"
        strokeWidth="2"
        strokeLinecap="round"
      />
    </svg>
  );
}

export default function App() {
  const [showBlog, setShowBlog] = useState(false);

  return (
    <div className="min-h-screen">
      {/* Brand header */}
      <header className="border-b border-slate-200 bg-white">
        <div className="mx-auto flex max-w-5xl items-center gap-3 px-6 py-5">
          {/* Logo + wordmark — clicking always returns to the tool */}
          <button
            onClick={() => setShowBlog(false)}
            className="flex items-center gap-3 focus:outline-none"
            aria-label="Go to Gauge home"
          >
            <BrandIcon />
            <div className="text-left">
              <p className="text-lg font-semibold leading-none tracking-tight text-slate-900">
                Gauge
              </p>
            </div>
          </button>

          {/* Nav */}
          <nav className="ml-auto flex items-center gap-1">
            <NavLink active={!showBlog} onClick={() => setShowBlog(false)}>
              Estimator
            </NavLink>
            <NavLink active={showBlog} onClick={() => setShowBlog(true)}>
              How it works
            </NavLink>
          </nav>
        </div>
      </header>

      <main className={showBlog ? "" : "mx-auto max-w-5xl px-6 py-8"}>
        {showBlog ? <Blog /> : <IntakeWizard />}
      </main>

      <footer className="mx-auto max-w-5xl px-6 pb-8">
        <p className="text-xs text-slate-400">
          Illustrative prototype — not a substitute for an actual insurance
          quote or advice from your insurer.
        </p>
      </footer>
    </div>
  );
}

function NavLink({
  active,
  onClick,
  children,
}: {
  active: boolean;
  onClick: () => void;
  children: React.ReactNode;
}) {
  return (
    <button
      onClick={onClick}
      className={[
        "rounded-md px-3 py-1.5 text-sm font-medium transition-colors",
        active
          ? "bg-brand-50 text-brand-700"
          : "text-slate-600 hover:bg-slate-100 hover:text-slate-900",
      ].join(" ")}
    >
      {children}
    </button>
  );
}
