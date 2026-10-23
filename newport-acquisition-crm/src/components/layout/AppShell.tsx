import { useState } from 'react'
import { Outlet } from 'react-router-dom'
import { Sidebar } from './Sidebar'

export function AppShell() {
  const [collapsed, setCollapsed] = useState(false)

  return (
    <div className="flex min-h-full bg-canvas">
      <Sidebar collapsed={collapsed} onToggle={() => setCollapsed((c) => !c)} />
      <div
        className={`flex min-h-full min-w-0 flex-1 flex-col transition-[margin] duration-200 ${
          collapsed ? 'ml-[72px]' : 'ml-60'
        }`}
      >
        <Outlet context={{ sidebarCollapsed: collapsed }} />
      </div>
    </div>
  )
}
