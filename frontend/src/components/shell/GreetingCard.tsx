type GreetingCardProps = {
  greeting: string
  onStartSearch: () => void
  onContinueLastSearch: () => void
}

export function GreetingCard({ greeting, onStartSearch, onContinueLastSearch }: GreetingCardProps) {
  return (
    <section className="greeting-card">
      <h1>{greeting}</h1>
      <p>Let&apos;s find exceptional talent today.</p>
      <div className="greeting-card__composer">
        <div className="greeting-card__title">
          <strong>What are you hiring for?</strong>
          <span>Describe the role or paste a job description.</span>
        </div>
        <textarea placeholder="Describe the role or paste a job description..." rows={6} />
        <div className="greeting-card__actions">
          <button type="button" className="button button--primary" onClick={onStartSearch}>Start Search</button>
          <button type="button" className="button button--secondary" onClick={onContinueLastSearch}>Continue Last Search</button>
        </div>
      </div>
    </section>
  )
}
