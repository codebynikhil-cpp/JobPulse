import Link from "next/link";
import { ArrowRight, Check, SlidersHorizontal, Building2, Bell } from "lucide-react";
import { BrandMark, GeometricComposition } from "@/components/ui/geometry";

const steps = [
  {
    title: "Define your direction",
    text: "Build profiles around your roles, skills, experience, and location preferences.",
    icon: SlidersHorizontal,
  },
  {
    title: "Choose your companies",
    text: "Select companies to monitor through their official career sources.",
    icon: Building2,
  },
  {
    title: "Find your next move",
    text: "Review personal matches, receive alerts, and keep saved and applied jobs organized.",
    icon: Bell,
  },
];

export default function Home() {
  return (
    <div className="landing">
      <a className="skip-link" href="#main-content">
        Skip to content
      </a>
      <header className="landing-nav">
        <Link href="/" className="brand">
          <BrandMark />
          <span>JobPulse.</span>
        </Link>
        <nav aria-label="Main navigation">
          <a href="#how-it-works">How it works</a>
          <Link href="/login">Log in</Link>
          <Link className="button button-primary" href="/signup">
            Get started <ArrowRight size={18} />
          </Link>
        </nav>
      </header>
      <main id="main-content">
        <section className="landing-hero">
          <div className="hero-copy">
            <span className="eyebrow">A CLEAR WORKING SHEET FOR YOUR SEARCH</span>
            <h1>
              Your search.<br />
              In <span className="highlight-sketch">focus.</span>
            </h1>
            <p>
              Good opportunities deserve your attention. Monitor official company careers and find roles that fit your direction.
            </p>
            <div className="hero-action-group">
              <Link className="button button-primary" href="/signup">
                Build your profile <ArrowRight size={20} />
              </Link>
              <div className="hero-drawn-arrow" aria-hidden="true">
                <svg width="44" height="28" viewBox="0 0 44 28" fill="none">
                  <path d="M4 6 C14 5, 26 8, 34 20" stroke="var(--dp-color-accent)" strokeWidth="2.2" strokeLinecap="round" />
                  <path d="M24 19 L35 21 L33 11" stroke="var(--dp-color-accent)" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round" />
                </svg>
                <span>start here</span>
              </div>
            </div>
            <span className="hero-footnote">OFFICIAL CAREERS. PERSONAL MATCHES.</span>
          </div>
          <GeometricComposition />
        </section>
        <div className="landing-principles">
          <span><i className="shape-circle" /> YOUR ROLES</span>
          <span><i className="shape-square" /> YOUR COMPANIES</span>
          <span><i className="shape-triangle" /> YOUR NEXT MOVE</span>
        </div>
        <section id="how-it-works" className="landing-section">
          <div className="landing-section-heading">
            <span className="eyebrow">01 / THE PROCESS</span>
            <h2>A search built<br />around you.</h2>
            <p>Three deliberate steps.<br />One clear direction.</p>
          </div>
          <div className="feature-grid">
            {steps.map(({ title, text, icon: Icon }, i) => (
              <article className="feature-card" key={title}>
                <div className="feature-top">
                  <span className="step-number"><span>0{i + 1}</span></span>
                  <Icon size={28} aria-hidden="true" />
                </div>
                <h3>{title}</h3>
                <p>{text}</p>
              </article>
            ))}
          </div>
        </section>
        <section className="landing-benefits">
          <div>
            <span className="eyebrow">02 / LESS NOISE. MORE DIRECTION.</span>
            <h2>Make room for<br />the right role.</h2>
          </div>
          <ul>
            {[
              "Matches shaped by your profiles",
              "Official company career sources",
              "One place for saved and applied jobs",
            ].map((text) => (
              <li key={text}>
                <span><Check size={22} aria-hidden="true" /></span>
                {text}
              </li>
            ))}
          </ul>
        </section>
        <section className="landing-section landing-faq">
          <span className="eyebrow">03 / THE DETAILS</span>
          <h2>A few clear answers.</h2>
          <details>
            <summary>How do profiles shape my matches?</summary>
            <p>Your target roles, skills, experience, and location preferences define your search. Matching jobs show their scores and the evidence behind them.</p>
          </details>
          <details>
            <summary>Can I choose which companies to monitor?</summary>
            <p>Yes. Select companies from the workspace and associate them with your active profiles. Monitoring availability depends on supported career sources.</p>
          </details>
          <details>
            <summary>Can I organize jobs after a match?</summary>
            <p>Save interesting jobs, mark applications, or ignore roles that do not fit. Your job actions stay personal to your account.</p>
          </details>
        </section>
        <section className="landing-cta">
          <span className="eyebrow">YOUR NEXT CHAPTER STARTS WITH A DIRECTION</span>
          <h2>Find your<br />next move.</h2>
          <Link href="/signup" className="button button-primary">
            Create your account <ArrowRight size={20} />
          </Link>
        </section>
      </main>
      <footer className="landing-footer">
        <Link href="/" className="brand">
          <BrandMark />
          <span>JobPulse.</span>
        </Link>
        <p>A personal working sheet.<br />Your search follows you.</p>
        <Link href="/login">
          Enter your workspace <ArrowRight size={16} />
        </Link>
      </footer>
    </div>
  );
}
