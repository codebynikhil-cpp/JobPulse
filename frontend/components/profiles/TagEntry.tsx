"use client";
import { useId, useState } from "react";
import { X } from "lucide-react";
import { Button } from "@/components/ui/primitives";
export default function TagEntry({
  label,
  hint,
  values,
  onChange,
}: {
  label: string;
  hint: string;
  values: string[];
  onChange: (values: string[]) => void;
}) {
  const id = useId(),
    [draft, setDraft] = useState(""),
    [error, setError] = useState("");
  function add() {
    const value = draft.normalize("NFKC").trim().replace(/\s+/g, " ");
    if (!value || value.length > 120) {
      setError("Enter 1-120 characters.");
      return;
    }
    if (
      values.some(
        (item) => item.toLocaleLowerCase() === value.toLocaleLowerCase(),
      )
    ) {
      setError("This entry is already in the list.");
      return;
    }
    if (values.length >= 50) {
      setError("You can add up to 50 entries.");
      return;
    }
    onChange([...values, value]);
    setDraft("");
    setError("");
  }
  return (
    <div>
      <label htmlFor={id}>{label}</label>
      <p id={`${id}-hint`} className="field-hint">
        {hint} Use Add or Enter to keep each entry.
      </p>
      <div className="tag-input-row">
        <input
          data-entry-draft
          id={id}
          value={draft}
          maxLength={120}
          aria-invalid={!!error}
          aria-describedby={`${id}-hint${error ? ` ${id}-error` : ""}`}
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter") {
              e.preventDefault();
              add();
            }
          }}
        />
        <Button type="button" onClick={add}>
          Add
        </Button>
      </div>
      {error && (
        <p
          id={`${id}-error`}
          role="alert"
          className="field-hint"
          style={{ color: "var(--error)" }}
        >
          {error}
        </p>
      )}
      <ul className="tag-list">
        {values.map((value, index) => (
          <li key={value}>
            {value}
            <button
              type="button"
              aria-label={`Remove ${value} from ${label}`}
              onClick={() =>
                onChange(values.filter((_, position) => index !== position))
              }
            >
              <X size={13} aria-hidden="true" />
            </button>
          </li>
        ))}
      </ul>
    </div>
  );
}
