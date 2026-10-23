import { useQuery } from '@tanstack/react-query'
import {
  CalendarDays,
  CalendarPlus,
  FileSpreadsheet,
  FolderKanban,
  LayoutDashboard,
  Menu,
  Palmtree,
  Settings,
  ShieldCheck,
  Users,
} from 'lucide-react'
import { useState, type ReactNode } from 'react'
import { NavLink } from 'react-router-dom'

import { Button } from '@/components/ui/button'
import { Sheet, SheetContent, SheetTitle, SheetTrigger } from '@/components/ui/sheet'
import { cn } from '@/lib/utils'
import { api } from '@/services/api'

const NAV = [
  { to: '/', label: 'Dashboard', icon: LayoutDashboard, end: true },
  { to: '/generate', label: 'Generate roster', icon: CalendarPlus },
  { to: '/rosters', label: 'Rosters', icon: CalendarDays },
  { to: '/leave', label: 'Leave', icon: Palmtree },
  { to: '/analysts', label: 'Analysts', icon: Users },
  { to: '/projects', label: 'Projects & shifts', icon: FolderKanban },
  { to: '/import-export', label: 'Import / Export', icon: FileSpreadsheet },
  { to: '/settings', label: 'Settings & data', icon: Settings },
]

function Brand() {
  return (
    <div className="flex items-center gap-2 px-3 py-4">
      <img src="/favicon.svg" alt="" className="size-8" />
      <div className="leading-tight">
        <p className="text-sm font-semibold text-white">ZTB ShiftOrbit</p>
        <p className="text-[11px] text-sidebar-foreground/70">Zero Trust Bastion</p>
      </div>
    </div>
  )
}

function Nav({ onNavigate }: { onNavigate?: () => void }) {
  return (
    <nav className="flex flex-col gap-1 px-2" aria-label="Main">
      {NAV.map(({ to, label, icon: Icon, end }) => (
        <NavLink
          key={to}
          to={to}
          end={end}
          onClick={onNavigate}
          className={({ isActive }) =>
            cn('flex items-center gap-3 rounded-lg px-3 py-2 text-sm text-sidebar-foreground/85 transition-colors',
              'hover:bg-sidebar-accent hover:text-white',
              isActive && 'bg-sidebar-primary text-white hover:bg-sidebar-primary')
          }
        >
          <Icon className="size-4" /> {label}
        </NavLink>
      ))}
    </nav>
  )
}

function LocalBadge() {
  const health = useQuery({
    queryKey: ['health'],
    queryFn: () => api.get<{ version: string; solver: string }>('/health'),
    refetchInterval: 30_000,
  })
  return (
    <div className="m-3 rounded-lg border border-sidebar-border bg-sidebar-accent/40 p-3 text-[11px] text-sidebar-foreground/80">
      <p className="flex items-center gap-1 font-medium text-sidebar-foreground">
        <ShieldCheck className="size-3.5 text-emerald-400" /> Local-only
      </p>
      <p className="mt-1">Data stays in a SQLite file on this computer.</p>
      <p className="mt-1">
        {health.isError ? <span className="text-rose-400">Backend unreachable</span>
          : health.data ? `v${health.data.version} · ${health.data.solver}` : 'Checking backend…'}
      </p>
    </div>
  )
}

export function AppShell({ children }: { children: ReactNode }) {
  const [open, setOpen] = useState(false)
  return (
    <div className="min-h-screen bg-background">
      <aside className="fixed inset-y-0 left-0 hidden w-60 flex-col justify-between border-r border-sidebar-border bg-sidebar lg:flex">
        <div>
          <Brand />
          <Nav />
        </div>
        <LocalBadge />
      </aside>
      <header className="sticky top-0 z-30 flex items-center gap-2 border-b bg-sidebar px-3 py-2 lg:hidden">
        <Sheet open={open} onOpenChange={setOpen}>
          <SheetTrigger asChild>
            <Button variant="ghost" size="icon" aria-label="Open navigation">
              <Menu />
            </Button>
          </SheetTrigger>
          <SheetContent side="left" className="w-64 border-sidebar-border bg-sidebar p-0">
            <SheetTitle className="sr-only">Navigation</SheetTitle>
            <Brand />
            <Nav onNavigate={() => setOpen(false)} />
            <LocalBadge />
          </SheetContent>
        </Sheet>
        <img src="/favicon.svg" alt="" className="size-6" />
        <span className="text-sm font-semibold">ZTB ShiftOrbit</span>
      </header>
      <main className="px-4 py-6 sm:px-6 lg:ml-60 lg:px-8">{children}</main>
    </div>
  )
}
