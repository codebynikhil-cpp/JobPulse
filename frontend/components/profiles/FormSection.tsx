import type { ReactNode } from "react";
export default function FormSection({
  id,
  title,
  description,
  children,
}: {
  id: string;
  title: string;
  description: string;
  children: ReactNode;
}) {
  return (
    <section className="form-section" aria-labelledby={id}>
      <div className="form-section-intro">
        <h2 id={id}>{title}</h2>
        <p>{description}</p>
      </div>
      <div className="form-section-fields">{children}</div>
    </section>
  );
}
