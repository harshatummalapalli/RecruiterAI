const items = [
  'Resume uploaded',
  'Candidate shortlisted',
  'Search completed',
  'Role paused',
  'Duplicate merged',
]

export function ActivityFeed() {
  return (
    <section className="rail-card">
      <div className="rail-card__header">
        <h2>Recent Activity</h2>
        <button type="button" aria-label="View all activity">View all</button>
      </div>
      <div className="rail-card__feed">
        {items.map((item) => <div key={item} className="rail-card__feed-item">{item}</div>)}
      </div>
    </section>
  )
}
