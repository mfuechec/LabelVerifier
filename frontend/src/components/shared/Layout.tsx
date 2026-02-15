import { Outlet, Link } from 'react-router-dom';

export default function Layout() {
  return (
    <div>
      <header className="app-header">
        <div className="header-inner">
          <div className="logo-group">
            <Link to="/" className="logo">
              <span className="logo-mark">Label</span>Verify
            </Link>
            <div className="logo-divider" />
            <span className="logo-subtitle">TTB Compliance Division</span>
          </div>
          <nav className="header-nav">
            <Link to="/" className="nav-link">Single Verify</Link>
            <Link to="/batch" className="nav-link">Batch Upload</Link>
            <Link to="/history" className="nav-link">History</Link>
          </nav>
          <div className="header-status">
            <span className="status-dot" />
            System Online
          </div>
        </div>
      </header>
      <main className="app-main">
        <Outlet />
      </main>
    </div>
  );
}
