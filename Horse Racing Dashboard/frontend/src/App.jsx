import { BrowserRouter, Routes, Route, NavLink } from "react-router-dom";
import DashboardPage from "./pages/DashboardPage";
import RaceDetailPage from "./pages/RaceDetailPage";
import ROIPage from "./pages/ROIPage";
import "./index.css";

export default function App() {
  return (
    <BrowserRouter>
      <div className="app-layout">
        <header className="app-header">
          <div className="app-header__left">
            <NavLink
              to="/"
              className="app-header__logo"
              style={{
                textDecoration: "none",
                display: "flex",
                alignItems: "center",
                gap: "8px",
              }}
            >
              <span style={{ fontSize: "1.4rem" }}>🏇</span>
              <span style={{ fontWeight: "800", letterSpacing: "-0.02em" }}>
                旺財
              </span>
            </NavLink>
          </div>
          <nav className="app-header__nav-capsule">
            <NavLink
              to="/"
              end
              className={({ isActive }) =>
                `nav-pill ${isActive ? "nav-pill--active" : ""}`
              }
            >
              <svg
                xmlns="http://www.w3.org/2000/svg"
                width="16"
                height="16"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                strokeWidth="2.5"
                strokeLinecap="round"
                strokeLinejoin="round"
                style={{ marginRight: "6px", verticalAlign: "text-bottom" }}
              >
                <rect width="18" height="18" x="3" y="3" rx="2" />
                <path d="M3 9h18" />
                <path d="M9 21V9" />
              </svg>
              賽事
            </NavLink>
            <NavLink
              to="/roi"
              className={({ isActive }) =>
                `nav-pill ${isActive ? "nav-pill--active" : ""}`
              }
            >
              <svg
                xmlns="http://www.w3.org/2000/svg"
                width="16"
                height="16"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                strokeWidth="2.5"
                strokeLinecap="round"
                strokeLinejoin="round"
                style={{ marginRight: "6px", verticalAlign: "text-bottom" }}
              >
                <path d="M3 3v18h18" />
                <path d="m19 9-5 5-4-4-3 3" />
              </svg>
              ROI
            </NavLink>
          </nav>
        </header>

        <main className="app-main">
          <Routes>
            <Route path="/" element={<DashboardPage />} />
            <Route
              path="/race/:date/:venue/:raceNumber"
              element={<RaceDetailPage />}
            />
            <Route path="/roi" element={<ROIPage />} />
          </Routes>
        </main>

        <footer
          style={{
            textAlign: "center",
            padding: "12px",
            fontSize: "0.7rem",
            color: "#94A3B8",
            borderTop: "1px solid #E2E8F0",
          }}
        >
          旺財 Racing Dashboard · Powered by Antigravity
        </footer>
      </div>
    </BrowserRouter>
  );
}
