type RoutePageProps = {
  title: string
  description?: string
}

export function RoutePage({ title, description }: RoutePageProps) {
  return (
    <section className="route-page">
      <div className="route-page__card">
        <p className="route-page__eyebrow">Empty route</p>
        <h1>{title}</h1>
        {description ? <p>{description}</p> : null}
      </div>
    </section>
  )
}
