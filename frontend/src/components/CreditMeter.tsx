import { useEffect, useRef, useState } from 'react'
import { getCredits } from '../services/recruiterWorkflow'

/** Admin-only live CrustData credit meter. Self-gating: the /credits endpoint
 * 404s for ordinary recruiters, so getCredits() returns null and this renders
 * nothing — non-admins never see it and are never shown they are being gated.
 *
 * Shows the remaining balance, how much has been spent since this session
 * started, and the cost model (person_search ≈ 0.03 credits/result). Polls on a
 * slow interval; /user/credits is itself free, so the meter costs nothing. */
export function CreditMeter() {
  const [balance, setBalance] = useState<number | null>(null)
  const [costPerResult, setCostPerResult] = useState(0.03)
  const sessionStart = useRef<number | null>(null)

  useEffect(() => {
    let cancelled = false
    const poll = async () => {
      const data = await getCredits()
      if (cancelled || !data) return
      if (sessionStart.current === null) sessionStart.current = data.credits
      setBalance(data.credits)
      setCostPerResult(data.cost_per_result)
    }
    poll()
    const id = window.setInterval(poll, 45000)
    return () => {
      cancelled = true
      window.clearInterval(id)
    }
  }, [])

  if (balance === null) return null // not admin, or unavailable — render nothing

  const spent = sessionStart.current !== null ? Math.max(0, sessionStart.current - balance) : 0
  const fmt = (n: number) => (Math.round(n * 100) / 100).toLocaleString()

  return (
    <div className="credit-meter" role="status" aria-label="CrustData credits">
      <div className="credit-meter__row">
        <span className="credit-meter__label">CrustData credits</span>
        <span className="credit-meter__balance">{fmt(balance)}</span>
      </div>
      {spent > 0 ? (
        <div className="credit-meter__row credit-meter__row--muted">
          <span>Spent this session</span>
          <span>−{fmt(spent)}</span>
        </div>
      ) : null}
      <div className="credit-meter__hint">
        person search ≈ {costPerResult} / result · ~{fmt(costPerResult * 50)} per search
      </div>
    </div>
  )
}
