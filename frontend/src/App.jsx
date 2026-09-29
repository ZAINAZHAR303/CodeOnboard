import { Link, Route, Routes } from 'react-router-dom'
import HomePage from './pages/HomePage.jsx'
import DashboardPage from './pages/DashboardPage.jsx'
import { LogoMark } from './components/Icons.jsx'

export default function App() {
  return (
    <div className="app">
      <header className="app-header">
        <Link to="/" className="brand">
          <LogoMark />
          <span>CodeOnboard</span>
        </Link>
        <span className="brand-tag">Codebase onboarding accelerator</span>
      </header>
      <Routes>
        <Route path="/" element={<HomePage />} />
        <Route path="/repo/:repoId" element={<DashboardPage />} />
        <Route
          path="*"
          element={
            <main className="page-center">
              <h1>Page not found</h1>
              <Link to="/" className="btn btn-primary">Back to home</Link>
            </main>
          }
        />
      </Routes>
    </div>
  )
}
