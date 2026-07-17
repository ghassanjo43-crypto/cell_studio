// A collapsible accordion section for the analysis sidebar.

import { useState, type ReactNode } from "react";

interface Props {
  title: string;
  icon: string;
  defaultOpen?: boolean;
  /** Controlled open state (with onToggle). If omitted, the section manages itself. */
  open?: boolean;
  onToggle?: () => void;
  /** Keep the body mounted (hidden via CSS) when closed — used for the inspector
   * portal target, which must stay in the DOM. */
  keepMounted?: boolean;
  children: ReactNode;
}

export function SidebarSection({ title, icon, defaultOpen = true, open: openProp, onToggle, keepMounted = false, children }: Props) {
  const [internalOpen, setInternalOpen] = useState(defaultOpen);
  const controlled = openProp !== undefined;
  const open = controlled ? openProp! : internalOpen;
  const setOpen = () => (controlled ? onToggle?.() : setInternalOpen((o) => !o));
  return (
    <div className={`side-section ${open ? "is-open" : ""}`}>
      <button className="side-section-head" onClick={setOpen}>
        <span className="side-section-title">
          <span className="side-icon">{icon}</span> {title}
        </span>
        <span className="side-chev">{open ? "▾" : "▸"}</span>
      </button>
      {open ? (
        <div className="side-section-body">{children}</div>
      ) : keepMounted ? (
        <div className="side-section-body" style={{ display: "none" }}>{children}</div>
      ) : null}
    </div>
  );
}
