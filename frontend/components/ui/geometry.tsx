/** Hand-drawn sketch mark and working-sheet composition. */
export function BrandMark() {
  return (
    <svg className="brand-mark" width="48" height="24" viewBox="0 0 48 24" fill="none" aria-hidden="true">
      {/* Hand-drawn pencil pulse line */}
      <path
        d="M2 13 C6 12.5, 9 13.5, 12 13 L16.5 6 L21.5 18.5 L26 7.5 L30 15 L34 12.5 C38 12, 42 13, 46 12.5"
        stroke="var(--dp-color-ink)"
        strokeWidth="2.2"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      {/* Sketched red accent correction dot */}
      <circle cx="21.5" cy="18.5" r="2.5" fill="var(--dp-color-accent)" />
      {/* Soft yellow highlighter swipe */}
      <path
        d="M8 20 C18 19.5, 28 20.5, 40 20"
        stroke="var(--dp-color-highlight)"
        strokeWidth="4"
        strokeLinecap="round"
        opacity="0.85"
      />
    </svg>
  );
}

export function GeometricComposition() {
  return (
    <div className="sketch-composition" aria-hidden="true">
      {/* Taped paper mount with pencil line drawing */}
      <div className="sketch-mount">
        <div className="tape-strip tape-top" />
        <svg className="sketch-drawing" viewBox="0 0 260 170" fill="none">
          {/* Hand drawn document / radar drawing with uneven pencil strokes */}
          <rect
            x="20"
            y="15"
            width="220"
            height="135"
            rx="6"
            stroke="var(--dp-color-ink)"
            strokeWidth="1.8"
            strokeDasharray="5 2"
          />
          <path d="M40 40 C75 39, 110 42, 160 40" stroke="var(--dp-color-ink)" strokeWidth="2" strokeLinecap="round" />
          <path d="M40 62 C70 61, 100 63, 135 61" stroke="var(--dp-color-line)" strokeWidth="1.6" strokeLinecap="round" />
          <path d="M40 84 C85 83, 125 85, 175 83" stroke="var(--dp-color-line)" strokeWidth="1.6" strokeLinecap="round" />
          <path d="M40 106 C65 107, 90 105, 125 106" stroke="var(--dp-color-line)" strokeWidth="1.6" strokeLinecap="round" />
          {/* Hand-drawn search lens */}
          <circle cx="175" cy="100" r="26" stroke="var(--dp-color-annotation)" strokeWidth="2.2" fill="none" />
          <line x1="193" y1="118" x2="220" y2="145" stroke="var(--dp-color-annotation)" strokeWidth="2.8" strokeLinecap="round" />
          {/* Sketched red checkmark */}
          <path d="M165 99 L172 107 L186 90" stroke="var(--dp-color-accent)" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" />
        </svg>
        <span className="sketch-mount-caption">fig. 01 — direct source monitor</span>
      </div>

      {/* Blue annotation note with taped corner */}
      <div className="sketch-note blue-note">
        <div className="tape-strip tape-corner" />
        <span className="note-tag">NOTE:</span>
        <p>Direct sync from official careers. Zero aggregator noise.</p>
      </div>

      {/* Yellow highlight note */}
      <div className="sketch-note yellow-note">
        <span className="note-star">★</span>
        <p>Profile match: <strong>96% fit</strong></p>
      </div>

      {/* Drawn bracket with facts beneath it */}
      <div className="sketch-bracket-group">
        <svg className="drawn-bracket" viewBox="0 0 240 24" fill="none">
          <path
            d="M4 18 C4 8, 10 4, 22 4 L110 4 C116 4, 118 1, 120 0 C122 1, 124 4, 130 4 L218 4 C230 4, 236 8, 236 18"
            stroke="var(--dp-color-ink)"
            strokeWidth="1.8"
            strokeLinecap="round"
          />
        </svg>
        <div className="drawn-bracket-facts">
          <span>Official sources</span>
          <span className="bracket-dot">•</span>
          <span>Zero spam</span>
          <span className="bracket-dot">•</span>
          <span>Personal matches</span>
        </div>
      </div>
    </div>
  );
}
