interface SliderProps {
  label: string;
  value: number;
  onChange: (value: number) => void;
  min: number;
  max: number;
  step?: number;
  format?: (value: number) => string;
}

export function Slider({
  label,
  value,
  onChange,
  min,
  max,
  step = 1,
  format = (v) => String(v),
}: SliderProps) {
  return (
    <label className="flex flex-col gap-1.5 text-sm">
      <div className="flex items-baseline justify-between">
        <span className="font-medium text-slate-700">{label}</span>
        <span className="tabular-nums text-slate-900">{format(value)}</span>
      </div>
      <input
        type="range"
        min={min}
        max={max}
        step={step}
        value={value}
        onChange={(e) => onChange(Number(e.target.value))}
      />
    </label>
  );
}
