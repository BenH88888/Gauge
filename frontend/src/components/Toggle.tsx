interface ToggleProps<T extends string> {
  label: string;
  value: T;
  options: { value: T; label: string }[];
  onChange: (value: T) => void;
}

export function Toggle<T extends string>({
  label,
  value,
  options,
  onChange,
}: ToggleProps<T>) {
  return (
    <div className="flex flex-col gap-1.5 text-sm">
      <span className="font-medium text-slate-700">{label}</span>
      <div className="inline-flex rounded-md border border-slate-300 bg-white p-0.5">
        {options.map((opt) => {
          const selected = opt.value === value;
          return (
            <button
              key={opt.value}
              type="button"
              onClick={() => onChange(opt.value)}
              className={
                "flex-1 rounded px-3 py-1.5 text-sm transition " +
                (selected
                  ? "bg-brand-600 text-white"
                  : "text-slate-700 hover:bg-slate-100")
              }
            >
              {opt.label}
            </button>
          );
        })}
      </div>
    </div>
  );
}
