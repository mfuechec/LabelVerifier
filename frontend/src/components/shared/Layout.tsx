import { Outlet, Link } from 'react-router-dom'

export default function Layout() {
  return (
    <div className="app-layout">
      <header className="app-header">
        <h1><Link to="/">LabelVerify AI</Link></h1>
        <nav>
          <Link to="/">Upload</Link>
          <Link to="/batch">Batch</Link>
          <Link to="/history">History</Link>
        </nav>
      </header>
      <main className="app-main">
        <Outlet />
      </main>
    </div>
  )
}
