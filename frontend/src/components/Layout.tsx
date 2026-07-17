// App shell: header with brand, current user, and logout.

import { Link, Outlet } from "react-router-dom";
import { useAuth } from "../auth/AuthContext";

export function Layout() {
  const { user, logout } = useAuth();
  return (
    <div className="app-shell">
      <header className="app-header">
        <Link to="/" className="brand">
          <span className="brand-mark">◍</span> Virtual Cell Studio
        </Link>
        <div className="header-right">
          {user ? (
            <>
              <span className="user-email">{user.email}</span>
              <button className="btn btn-small" onClick={logout}>
                Log out
              </button>
            </>
          ) : null}
        </div>
      </header>
      <main className="app-main">
        <Outlet />
      </main>
    </div>
  );
}
