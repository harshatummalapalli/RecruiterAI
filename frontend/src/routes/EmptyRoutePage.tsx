type EmptyRoutePageProps = {
  title: string
}

export function EmptyRoutePage({ title }: EmptyRoutePageProps) {
  return <section className="route-shell"><div className="route-shell__card"><h1>{title}</h1></div></section>
}
