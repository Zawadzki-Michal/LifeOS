import { useEffect, useRef, useState } from "react";
import { Check, ChevronDown } from "lucide-react";

export default function ModelPicker({ value, options, onChange }) {
  const [open, setOpen] = useState(false);
  const menuRef = useRef(null);

  useEffect(() => {
    if (!open) return;
    function onDocClick(e) {
      if (!menuRef.current?.contains(e.target)) setOpen(false);
    }
    document.addEventListener("mousedown", onDocClick);
    return () => document.removeEventListener("mousedown", onDocClick);
  }, [open]);

  const current = options.find((o) => o.key === value);

  return (
    <div className="relative" ref={menuRef}>
      <button
        onClick={() => setOpen((o) => !o)}
        className="flex items-center gap-1.5 rounded-full border border-border bg-surface px-3 py-1.5 text-xs font-medium text-ink hover:border-border-strong"
      >
        {current?.label || "Auto"}
        <ChevronDown size={14} className="text-faint" />
      </button>
      {open && (
        <div className="absolute right-0 top-full z-10 mt-1 w-48 overflow-hidden rounded-lg border border-border bg-raised py-1 shadow-lg">
          {options.map((option) => (
            <button
              key={option.key}
              onClick={() => {
                setOpen(false);
                if (option.key !== value) onChange(option.key);
              }}
              className="flex w-full items-center justify-between gap-2 px-3 py-1.5 text-left text-sm text-ink hover:bg-surface"
            >
              {option.label}
              {option.key === value && <Check size={14} className="text-accent" />}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
