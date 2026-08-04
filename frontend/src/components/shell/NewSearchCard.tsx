import { GreetingCard } from './GreetingCard'

type NewSearchCardProps = {
  greeting: string
  onStartSearch: () => void
  onContinueLastSearch: () => void
}

export function NewSearchCard({ greeting, onStartSearch, onContinueLastSearch }: NewSearchCardProps) {
  return (
    <GreetingCard
      greeting={greeting}
      onStartSearch={onStartSearch}
      onContinueLastSearch={onContinueLastSearch}
    />
  )
}
