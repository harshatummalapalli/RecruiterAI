// Feature A — the dual-source reconciliation panel. Shown atop the brief when
// the recruiter supplied a hiring-manager brief alongside the JD. It explains
// WHY each requirement landed where it did (in both / HM surfaced it / JD-only
// boilerplate) and carries the soft years sanity-catch. Tier changes themselves
// happen in the brief's own editor below — this panel is the provenance view.
import type { ReconciledRequirement, Reconciliation } from '../models/intake'
import { reconciliationGroups } from '../models/intake'
import './ReconciliationPanel.css'

const TIER_LABEL: Record<string, string> = {
  core: 'Core',
  supporting: 'Supporting',
  differentiator: 'Differentiator',
}

type Props = {
  reconciliation: Reconciliation
  boundaryMinYears: number | null
  onEditBoundary?: () => void
}

function Row({ req, badge, note }: { req: ReconciledRequirement; badge: string; note?: string | null }) {
  return (
    <li className={`recon-row recon-row--${req.source}`}>
      <div className="recon-row__main">
        <div className="recon-row__top">
          <span className="recon-row__req">{req.text}</span>
          <span className={`recon-badge recon-badge--${req.source}`}>{badge}</span>
          {req.when === 'current' ? <span className="recon-now">current role</span> : null}
        </div>
        {note ? <p className="recon-row__note">{note}</p> : null}
      </div>
      <span className="recon-tier">{TIER_LABEL[req.tier] ?? req.tier}</span>
    </li>
  )
}

export function ReconciliationPanel({ reconciliation, boundaryMinYears, onEditBoundary }: Props) {
  const { both, hm, jd } = reconciliationGroups(reconciliation)
  const exp = reconciliation.experience
  // Recompute against the LIVE boundary so editing the filter clears the note.
  const yearsMismatch = exp != null && boundaryMinYears != null && boundaryMinYears !== exp.hm_mentioned_years

  return (
    <section className="recon" aria-label="How the JD and hiring-manager notes line up">
      <header className="recon__head">
        <h3 className="recon__title">How the JD and hiring-manager notes line up</h3>
        <p className="recon__sub">Nothing is locked in — this is what I proposed. Adjust any tier in the brief below.</p>
      </header>

      <div className="recon__pips">
        <span className="recon-pip recon-pip--both"><strong>{both.length}</strong> in both</span>
        <span className="recon-pip recon-pip--hm"><strong>{hm.length}</strong> the HM added</span>
        <span className="recon-pip recon-pip--jd"><strong>{jd.length}</strong> JD-only, demoted</span>
      </div>

      {both.length ? (
        <div className="recon-group">
          <div className="recon-group__head"><span className="recon-group__title">In both sources</span><span className="recon-group__note">kept as Core — highest confidence</span></div>
          <ul className="recon-rows">
            {both.map((r) => (
              <Row key={r.text} req={r} badge="In both"
                   note={r.hm_tier && r.jd_tier && r.text && r.source === 'both' && r.evidence ? r.evidence : null} />
            ))}
          </ul>
        </div>
      ) : null}

      {hm.length ? (
        <div className="recon-group">
          <div className="recon-group__head"><span className="recon-group__title">Surfaced by the hiring manager</span><span className="recon-group__note">the real nuance — promoted to Core</span></div>
          <ul className="recon-rows">
            {hm.map((r) => <Row key={r.text} req={r} badge="From the HM" note={r.evidence ?? null} />)}
          </ul>
        </div>
      ) : null}

      {jd.length ? (
        <div className="recon-group">
          <div className="recon-group__head"><span className="recon-group__title">Only in the job description</span><span className="recon-group__note">demoted to Supporting — restore any that still matter</span></div>
          <ul className="recon-rows">
            {jd.map((r) => <Row key={r.text} req={r} badge="JD only" note="Only in the published JD — likely boilerplate." />)}
          </ul>
        </div>
      ) : null}

      {yearsMismatch ? (
        <div className="recon-years">
          <p className="recon-years__q">
            Quick check — your experience filter is <strong>{boundaryMinYears}+ years</strong>, but the hiring manager's notes mention <strong>{exp!.hm_mentioned_years}</strong>. Your filter stays as you set it.
          </p>
          {onEditBoundary ? (
            <button type="button" className="recon-years__edit" onClick={onEditBoundary}>Edit the filter</button>
          ) : null}
        </div>
      ) : null}
    </section>
  )
}
