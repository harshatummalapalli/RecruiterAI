type StatusBannerProps = {
  tone: 'error' | 'success' | 'info'
  message: string
}

export function StatusBanner({ tone, message }: StatusBannerProps) {
  return (
    <div className={`status ${tone}`} role="status" aria-live="polite">
      <span className="status__marker" aria-hidden="true">
        {tone === 'success' ? '✓' : tone === 'error' ? '!' : 'i'}
      </span>
      <span>{message}</span>
    </div>
  )
}
