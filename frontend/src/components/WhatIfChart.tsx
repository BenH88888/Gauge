import { useMemo } from "react";
import {
  Area,
  CartesianGrid,
  ComposedChart,
  Legend,
  Line,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { WhatIfResponse, centsToDollars } from "../api";

interface WhatIfChartProps {
  data: WhatIfResponse | null;
  loading: boolean;
  error: string | null;
  feature: string;
}

interface ChartRow {
  value: number | string;
  /** Median predicted charges in dollars (for Y-axis). */
  chargesMedian: number;
  /** Charge interval lower bound in dollars. */
  chargesLower: number;
  /** Charge interval upper bound in dollars. */
  chargesUpper: number;
  /**
   * OOP lower bound as a dollar value, or null when no plan is selected.
   * Used as the invisible "floor" layer of the stacked OOP band.
   */
  oopFloor: number | null;
  /**
   * Width of the OOP band in dollars (= upper - lower), or null.
   * Stacked on top of oopFloor to produce the shaded interval band.
   */
  oopBand: number | null;
  /** Median OOP in dollars, or null when no plan is selected. */
  oopMedian: number | null;
}

export function WhatIfChart({ data, loading, error, feature }: WhatIfChartProps) {
  const rows: ChartRow[] = useMemo(() => {
    if (!data) return [];
    return data.points.map((p) => {
      const oop = p.oop_interval;
      return {
        value: p.value,
        chargesMedian: p.prediction.median_charges_cents / 100,
        chargesLower: p.prediction.lower_bound_cents / 100,
        chargesUpper: p.prediction.upper_bound_cents / 100,
        oopFloor: oop != null ? oop.lower_cents / 100 : null,
        oopBand: oop != null ? (oop.upper_cents - oop.lower_cents) / 100 : null,
        oopMedian: oop != null ? oop.median_cents / 100 : null,
      };
    });
  }, [data]);

  const hasOop = rows.length > 0 && rows[0].oopMedian !== null;

  if (loading) {
    return (
      <div className="rounded-xl border border-slate-200 bg-white p-6 text-sm text-slate-500">
        Running what-if sweep...
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
  if (rows.length === 0) {
    return (
      <div className="rounded-xl border border-dashed border-slate-200 bg-white p-6 text-sm text-slate-500">
        Pick a feature to sweep and the curve will render here.
      </div>
    );
  }

  return (
    <div className="rounded-xl border border-slate-200 bg-white p-4 shadow-card">
      <div className="mb-2 text-sm text-slate-600">
        {hasOop ? (
          <>
            How your <strong>out-of-pocket cost</strong> changes as{" "}
            <strong>{feature}</strong> varies. The shaded band is the 80%
            confidence interval; the line is the median.
          </>
        ) : (
          <>
            Predicted charges as <strong>{feature}</strong> varies. Select a
            plan to overlay your out-of-pocket estimate.
          </>
        )}
      </div>
      <div className="h-80 w-full">
        <ResponsiveContainer width="100%" height="100%">
          <ComposedChart data={rows} margin={{ top: 10, right: 16, bottom: 0, left: 0 }}>
            <CartesianGrid stroke="#e2e8f0" strokeDasharray="3 3" />
            <XAxis
              dataKey="value"
              tick={{ fontSize: 12, fill: "#475569" }}
              padding={{ left: 8, right: 8 }}
            />
            <YAxis
              tick={{ fontSize: 12, fill: "#475569" }}
              tickFormatter={(v: number) =>
                v >= 1000 ? `$${Math.round(v / 1000)}k` : `$${v}`
              }
              width={56}
            />
            <Tooltip
              formatter={(v: number, name) => [
                centsToDollars(Math.round(v * 100)),
                name,
              ]}
              labelFormatter={(label) => `${feature} = ${label}`}
              contentStyle={{ fontSize: 12 }}
            />
            <Legend wrapperStyle={{ fontSize: 12 }} />

            {/* Charge curve with bounds */}
            <Line
              type="monotone"
              dataKey="chargesMedian"
              name="Median charges"
              stroke="#94a3b8"
              strokeWidth={1.5}
              strokeDasharray="4 3"
              dot={false}
            />

            {/* OOP band (stacked areas: invisible floor + colored band) */}
            {hasOop && (
              <Area
                type="monotone"
                dataKey="oopFloor"
                name="OOP lower"
                stackId="oop"
                fill="transparent"
                stroke="transparent"
                legendType="none"
              />
            )}
            {hasOop && (
              <Area
                type="monotone"
                dataKey="oopBand"
                name="80% OOP interval"
                stackId="oop"
                fill="#dbeafe"
                fillOpacity={0.7}
                stroke="transparent"
              />
            )}

            {/* OOP median line — the hero number */}
            {hasOop && (
              <Line
                type="monotone"
                dataKey="oopMedian"
                name="Median OOP"
                stroke="#1d4ed8"
                strokeWidth={2.5}
                dot={{ r: 3, fill: "#1d4ed8" }}
              />
            )}
          </ComposedChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}
