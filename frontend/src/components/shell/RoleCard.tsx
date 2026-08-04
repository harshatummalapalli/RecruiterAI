type RoleCardProps = {
  title: string
  location: string
  status: string
  details: string
  actionLabel: string
}

export function RoleCard({ title, location, status, details, actionLabel }: RoleCardProps) {
  return (
    <article className="role-card">
      <div>
        <h3>{title}</h3>
        <p>{location}</p>
      </div>
      <div className="role-card__status">{status}</div>
      <div className="role-card__details">{details}</div>
      <button type="button" className="role-card__action">{actionLabel} →</button>
    </article>
  )
}
