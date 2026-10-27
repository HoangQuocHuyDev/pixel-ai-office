import type { RefObject } from 'react'

type HeaderProps = {
  isSidebarOpen: boolean
  menuButtonRef: RefObject<HTMLButtonElement | null>
  onOpenSidebar: () => void
}

function Header({
  isSidebarOpen,
  menuButtonRef,
  onOpenSidebar,
}: HeaderProps) {
  return (
    <header className="app-header">
      <div className="app-header__identity">
        <button
          ref={menuButtonRef}
          className="icon-button app-header__menu-button"
          type="button"
          aria-label="Open workspace menu"
          aria-controls="workspace-sidebar"
          aria-expanded={isSidebarOpen}
          onClick={onOpenSidebar}
        >
          <svg viewBox="0 0 24 24" aria-hidden="true">
            <path d="M4 7h16M4 12h16M4 17h16" />
          </svg>
        </button>

        <div className="app-brand">
          <span className="app-brand__mark" aria-hidden="true">
            <svg viewBox="0 0 24 24">
              <path d="M4 4h7v7H4zM13 4h7v7h-7zM4 13h7v7H4zM13 13h7v7h-7z" />
            </svg>
          </span>
          <span className="app-brand__name">Pixel AI Office</span>
        </div>

        <span className="alpha-badge">Alpha</span>
      </div>

      <div className="development-status">
        <span className="development-status__dot" aria-hidden="true" />
        Development
      </div>
    </header>
  )
}

export default Header
