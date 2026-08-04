import { Search } from 'lucide-react'

export function TopSearchBar() {
  return (
    <div className="app-topbar">
      <label className="app-topbar__search" aria-label="Search roles">
        <Search size={16} />
        <input placeholder="Search roles..." type="text" />
      </label>
    </div>
  )
}
