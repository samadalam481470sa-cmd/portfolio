import { BrowserRouter, HashRouter, Navigate, Route, Routes } from 'react-router-dom'
import { AuthProvider } from '@/auth/AuthContext'
import { ProtectedRoute } from '@/auth/ProtectedRoute'
import { DataProvider } from '@/data/DataContext'
import { AppShell } from '@/components/layout/AppShell'
import { Dashboard } from '@/pages/Dashboard'
import { LoginPage } from '@/pages/LoginPage'
import { OpportunitiesPage } from '@/pages/OpportunitiesPage'
import { ProjectsPage } from '@/pages/ProjectsPage'
import { SecurityPage } from '@/pages/SecurityPage'
import { RelationshipsPage } from '@/pages/RelationshipsPage'
import { TasksPage } from '@/pages/TasksPage'
import { SourcesPage } from '@/pages/SourcesPage'
import { CarriersPage } from '@/pages/CarriersPage'
import { PortfolioPage } from '@/pages/PortfolioPage'
import { DocumentsPage } from '@/pages/DocumentsPage'
import { ReportsPage } from '@/pages/ReportsPage'

// Hash routing keeps the static demo working from any CDN subpath
const Router = import.meta.env.VITE_STATIC_DEMO ? HashRouter : BrowserRouter

export default function App() {
  return (
    <AuthProvider>
      <Router basename={import.meta.env.VITE_STATIC_DEMO ? undefined : import.meta.env.BASE_URL}>
        <Routes>
          <Route path="/login" element={<LoginPage />} />
          <Route element={<ProtectedRoute />}>
            <Route
              element={
                <DataProvider>
                  <AppShell />
                </DataProvider>
              }
            >
              <Route index element={<Dashboard />} />
              <Route path="opportunities" element={<OpportunitiesPage />} />
              <Route path="projects" element={<ProjectsPage />} />
              <Route path="security" element={<SecurityPage />} />
              <Route path="relationships" element={<RelationshipsPage />} />
              <Route path="tasks" element={<TasksPage />} />
              <Route path="sources" element={<SourcesPage />} />
              <Route path="carriers" element={<CarriersPage />} />
              <Route path="portfolio" element={<PortfolioPage />} />
              <Route path="documents" element={<DocumentsPage />} />
              <Route path="reports" element={<ReportsPage />} />
              <Route path="*" element={<Navigate to="/" replace />} />
            </Route>
          </Route>
        </Routes>
      </Router>
    </AuthProvider>
  )
}
