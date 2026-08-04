export function AssistantPanel() {
  return (
    <section className="rail-card">
      <div className="rail-card__header">
        <h2>AI Assistant</h2>
        <button type="button" aria-label="Assistant options">•••</button>
      </div>
      <div className="rail-card__body">
        <p>Only 8 qualified candidates found.</p>
        <p>Removing location restriction could increase results by 64%.</p>
      </div>
      <button type="button" className="rail-card__button">Review suggestion</button>
    </section>
  )
}
