import { NavLink } from 'react-router-dom'
import {
  LayoutDashboard,
  Briefcase,
  Users,
  CheckSquare,
  Building2,
  Shield,
  Landmark,
  FileText,
  BarChart3,
  FolderKanban,
  ShieldCheck,
  LogOut,
  PanelLeftClose,
  PanelLeftOpen,
} from 'lucide-react'
import { NAV_ITEMS } from '@/data/constants'
import { useAuth } from '@/auth/AuthContext'
import { useNavigate } from 'react-router-dom'
import type { LucideIcon } from 'lucide-react'

const ICONS: Record<string, LucideIcon> = {
  dashboard: LayoutDashboard,
  opportunities: Briefcase,
  projects: FolderKanban,
  relationships: Users,
  tasks: CheckSquare,
  sources: Building2,
  carriers: Shield,
  portfolio: Landmark,
  documents: FileText,
  reports: BarChart3,
  security: ShieldCheck,
}

interface SidebarProps {
  collapsed: boolean
  onToggle: () => void
}

export function Sidebar({ collapsed, onToggle }: SidebarProps) {
  const { signOut, user } = useAuth()
  const navigate = useNavigate()

  return (
    <aside
      className={`fixed inset-y-0 left-0 z-40 flex flex-col border-r border-navy-800 bg-navy-900 text-white transition-[width] duration-200 ${
        collapsed ? 'w-[72px]' : 'w-60'
      }`}
    >
      <div className={`flex items-start gap-3 border-b border-navy-800 ${collapsed ? 'px-3 py-4' : 'px-4 py-5'}`}>
        <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-accent/20 text-sm font-bold tracking-tight text-accent-soft">
          N
        </div>
        {!collapsed && (
          <div className="min-w-0 pt-0.5">
            <p className="font-brand text-[13px] leading-snug font-bold tracking-wide text-white">
              NEWPORT
            </p>
            <p className="mt-0.5 text-[10px] leading-tight tracking-[0.08em] text-accent-muted uppercase">
              Specialty Partners
            </p>
          </div>
        )}
      </div>

      <nav className="custom-scroll flex-1 overflow-y-auto px-2 py-3">
        <ul className="space-y-0.5">
          {NAV_ITEMS.map((item) => {
            const Icon = ICONS[item.id] ?? Briefcase
            return (
              <li key={item.id}>
                <NavLink
                  to={item.path}
                  end={item.path === '/'}
                  title={collapsed ? item.label : undefined}
                  className={({ isActive }) =>
                    `flex items-center gap-3 rounded-lg px-3 py-2.5 text-[13px] transition-colors ${
                      collapsed ? 'justify-center px-2' : ''
                    } ${
                      isActive
                        ? 'bg-accent/20 font-semibold text-white shadow-[inset_3px_0_0_0_#3d7eb8]'
                        : 'text-white/70 hover:bg-white/5 hover:text-white'
                    }`
                  }
                >
                  <Icon className="h-[18px] w-[18px] shrink-0" strokeWidth={1.75} />
                  {!collapsed && <span className="truncate">{item.label}</span>}
                </NavLink>
              </li>
            )
          })}
        </ul>
      </nav>

      <div className="border-t border-navy-800 p-2">
        {!collapsed && user && (
          <p className="mb-1 truncate px-3 text-[11px] text-white/40">{user.name}</p>
        )}
        <button
          type="button"
          onClick={() => {
            void signOut().then(() => navigate('/login'))
          }}
          className={`flex w-full items-center gap-3 rounded-lg px-3 py-2.5 text-[13px] text-white/55 transition-colors hover:bg-white/5 hover:text-white ${
            collapsed ? 'justify-center px-2' : ''
          }`}
          title={collapsed ? 'Sign out' : undefined}
        >
          <LogOut className="h-[18px] w-[18px] shrink-0" strokeWidth={1.75} />
          {!collapsed && <span>Sign out</span>}
        </button>
        <button
          type="button"
          onClick={onToggle}
          className={`mt-1 flex w-full items-center gap-3 rounded-lg px-3 py-2.5 text-[13px] text-white/55 transition-colors hover:bg-white/5 hover:text-white ${
            collapsed ? 'justify-center px-2' : ''
          }`}
          aria-label={collapsed ? 'Expand sidebar' : 'Collapse sidebar'}
        >
          {collapsed ? (
            <PanelLeftOpen className="h-[18px] w-[18px]" strokeWidth={1.75} />
          ) : (
            <>
              <PanelLeftClose className="h-[18px] w-[18px]" strokeWidth={1.75} />
              <span>Collapse</span>
            </>
          )}
        </button>
      </div>
    </aside>
  )
}
