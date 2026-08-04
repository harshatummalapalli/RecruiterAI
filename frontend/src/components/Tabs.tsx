import type { ReactNode } from 'react'

type TabsProps = {
  tabs: Array<{ id: string; label: string }>
  activeTab: string
  onChange: (tabId: string) => void
  children: ReactNode
}

export function Tabs({ tabs, activeTab, onChange, children }: TabsProps) {
  return (
    <div className="tabs">
      <div className="tabs__list" role="tablist" aria-label="Candidate detail sections">
        {tabs.map((tab) => (
          <button
            key={tab.id}
            className={`tabs__trigger ${activeTab === tab.id ? 'is-active' : ''}`}
            role="tab"
            aria-selected={activeTab === tab.id}
            onClick={() => onChange(tab.id)}
          >
            {tab.label}
          </button>
        ))}
      </div>
      <div className="tabs__panel" role="tabpanel">
        {children}
      </div>
    </div>
  )
}
