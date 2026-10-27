import type { ReactNode, RefObject } from 'react'

type IconName = 'office' | 'tasks' | 'agents' | 'workspace' | 'settings'
export type WorkspacePage = 'office' | 'tasks' | 'agents' | 'workspace' | 'settings'

type SidebarProps = {
  closeButtonRef: RefObject<HTMLButtonElement | null>
  isOpen: boolean
  sidebarRef: RefObject<HTMLElement | null>
  onClose: () => void
  activePage: WorkspacePage
  onNavigate: (page: WorkspacePage) => void
}

const menuItems: Array<{ label: string; icon: IconName; page?: WorkspacePage }> = [
  { label: 'Office', icon: 'office', page: 'office' },
  { label: 'Tasks', icon: 'tasks', page: 'tasks' },
  { label: 'Agents', icon: 'agents', page: 'agents' },
  { label: 'Workspace', icon: 'workspace', page: 'workspace' },
  { label: 'Settings', icon: 'settings', page: 'settings' },
]

function NavigationIcon({ name }: { name: IconName }) {
  const paths: Record<IconName, ReactNode> = {
    office: (
      <>
        <path d="M4 20V8l8-4 8 4v12" />
        <path d="M9 20v-6h6v6M8 10h.01M16 10h.01" />
      </>
    ),
    tasks: (
      <>
        <path d="M9 6h11M9 12h11M9 18h11" />
        <path d="m4 6 1 1 2-2M4 12l1 1 2-2M4 18l1 1 2-2" />
      </>
    ),
    agents: (
      <>
        <circle cx="12" cy="8" r="3" />
        <path d="M5 20a7 7 0 0 1 14 0M4 9H2m20 0h-2" />
      </>
    ),
    workspace: (
      <>
        <rect x="3" y="4" width="18" height="16" rx="2" />
        <path d="M3 9h18M9 9v11" />
      </>
    ),
    settings: (
      <>
        <circle cx="12" cy="12" r="3" />
        <path d="M19.4 15a1.7 1.7 0 0 0 .34 1.88l.06.06-2.83 2.83-.06-.06A1.7 1.7 0 0 0 15 19.4a1.7 1.7 0 0 0-1 .6 1.7 1.7 0 0 0-.4 1V21h-4v-.09A1.7 1.7 0 0 0 8.6 19.4a1.7 1.7 0 0 0-1.88.34l-.06.06-2.83-2.83.06-.06A1.7 1.7 0 0 0 4.6 15a1.7 1.7 0 0 0-.6-1 1.7 1.7 0 0 0-1-.4H3v-4h.09A1.7 1.7 0 0 0 4.6 8.6a1.7 1.7 0 0 0-.34-1.88l-.06-.06 2.83-2.83.06.06A1.7 1.7 0 0 0 9 4.6a1.7 1.7 0 0 0 1-.6 1.7 1.7 0 0 0 .4-1V3h4v.09A1.7 1.7 0 0 0 15.4 4.6a1.7 1.7 0 0 0 1.88-.34l.06-.06 2.83 2.83-.06.06A1.7 1.7 0 0 0 19.4 9c.14.38.35.72.6 1 .27.28.62.42 1 .4h.09v4H21a1.7 1.7 0 0 0-1.6.6Z" />
      </>
    ),
  }

  return (
    <svg className="sidebar-nav__icon" viewBox="0 0 24 24" aria-hidden="true">
      {paths[name]}
    </svg>
  )
}

function Sidebar({
  closeButtonRef,
  isOpen,
  sidebarRef,
  onClose,
  activePage,
  onNavigate,
}: SidebarProps) {
  return (
    <aside
      ref={sidebarRef}
      id="workspace-sidebar"
      className={`app-sidebar${isOpen ? ' app-sidebar--open' : ''}`}
      aria-label="Workspace navigation"
    >
      <div className="app-sidebar__mobile-header">
        <span>Workspace</span>
        <button
          ref={closeButtonRef}
          className="icon-button"
          type="button"
          tabIndex={isOpen ? 0 : -1}
          aria-label="Close workspace menu"
          onClick={onClose}
        >
          <svg viewBox="0 0 24 24" aria-hidden="true">
            <path d="m6 6 12 12M18 6 6 18" />
          </svg>
        </button>
      </div>

      <nav aria-label="Primary">
        <p className="app-sidebar__label">Workspace</p>
        <ul className="sidebar-nav">
          {menuItems.map(({ label, icon, page }) => (
            <li key={label}>
              {page ? (
                <button
                  className={`sidebar-nav__item${activePage === page ? ' sidebar-nav__item--active' : ''}`}
                  aria-current={activePage === page ? 'page' : undefined}
                  type="button"
                  onClick={() => { onNavigate(page); onClose() }}
                >
                  <NavigationIcon name={icon} />
                  <span>{label}</span>
                </button>
              ) : (
                <button className="sidebar-nav__item" type="button" disabled>
                  <NavigationIcon name={icon} />
                  <span>{label}</span>
                  <span className="coming-soon">Soon</span>
                </button>
              )}
            </li>
          ))}
        </ul>
      </nav>

      <p className="app-sidebar__footer">Pixel AI Office · Alpha</p>
    </aside>
  )
}

export default Sidebar
