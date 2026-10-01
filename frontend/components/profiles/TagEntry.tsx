"use client";
import { useId, useState } from "react";

export default function TagEntry({ label, hint, values, onChange }: {
  label: string; hint: string; values: string[]; onChange: (values: string[]) => void;
}) {
  const id = useId();
  const [draft, setDraft] = useState("");
  const [error, setError] = useState("");
  function add() {
    const value = draft.normalize("NFKC").trim().replace(/\s+/g, " ");
    if (!value || value.length > 120) { setError("Enter 1-120 characters."); return; }
    if (values.some((item) => item.toLocaleLowerCase() === value.toLocaleLowerCase())) {
      setError("This entry is already in the list."); return;
    }
    if (values.length >= 50) { setError("You can add up to 50 entries."); return; }
    onChange([...values, value]); setDraft(""); setError("");
  }
  return <div>
    <label htmlFor={id} className="block font-medium">{label}</label>
    <p id={`${id}-hint`} className="mb-2 text-sm text-slate-600">{hint} Use Add or Enter to keep each entry.</p>
    <div className="flex gap-2">
      <input data-entry-draft id={id} value={draft} maxLength={120} aria-describedby={`${id}-hint`} onChange={(event) => setDraft(event.target.value)} onKeyDown={(event) => { if (event.key === "Enter") { event.preventDefault(); add(); } }} />
      <button type="button" onClick={add} className="rounded border border-slate-400 px-4">Add</button>
    </div>
    {error && <p role="alert" className="mt-1 text-sm text-red-700">{error}</p>}
    <ul className="mt-3 flex flex-wrap gap-2">
      {values.map((value, index) => <li key={value} className="flex items-center gap-2 rounded-full bg-slate-100 px-3 py-1 text-sm">
        {value}<button type="button" aria-label={`Remove ${value} from ${label}`} onClick={() => onChange(values.filter((_, position) => index !== position))} className="rounded px-1 font-bold text-slate-600">x</button>
      </li>)}
    </ul>
  </div>;
}
