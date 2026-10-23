import { Route, Routes } from 'react-router-dom'

import { AppShell } from '@/components/AppShell'
import { EmptyState } from '@/components/common'
import { AnalystsPage } from '@/pages/AnalystsPage'
import { DashboardPage } from '@/pages/DashboardPage'
import { GeneratorPage } from '@/pages/GeneratorPage'
import { ImportExportPage } from '@/pages/ImportExportPage'
import { LeavePage } from '@/pages/LeavePage'
import { ProjectsPage } from '@/pages/ProjectsPage'
import { RosterPage } from '@/pages/RosterPage'
import { RostersPage } from '@/pages/RostersPage'
import { SettingsPage } from '@/pages/SettingsPage'

export function App() {
  return (
    <AppShell>
      <Routes>
        <Route path="/" element={<DashboardPage />} />
        <Route path="/generate" element={<GeneratorPage />} />
        <Route path="/rosters" element={<RostersPage />} />
        <Route path="/rosters/:id" element={<RosterPage />} />
        <Route path="/leave" element={<LeavePage />} />
        <Route path="/analysts" element={<AnalystsPage />} />
        <Route path="/projects" element={<ProjectsPage />} />
        <Route path="/import-export" element={<ImportExportPage />} />
        <Route path="/settings" element={<SettingsPage />} />
        <Route path="*" element={<EmptyState title="Page not found" />} />
      </Routes>
    </AppShell>
  )
}
