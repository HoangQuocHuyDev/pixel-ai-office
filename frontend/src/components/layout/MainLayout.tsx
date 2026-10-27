import { useEffect, useRef, useState, type ReactNode } from 'react'

import Header from './Header'
import Sidebar from './Sidebar'
import type { WorkspacePage } from './Sidebar'

type MainLayoutProps = {
  children: ReactNode
  activePage: WorkspacePage
  onNavigate: (page: WorkspacePage) => void
}

function MainLayout({ children, activePage, onNavigate }: MainLayoutProps) {
  const [isSidebarOpen, setIsSidebarOpen] = useState(false)
  const menuButtonRef = useRef<HTMLButtonElement>(null)
  const closeButtonRef = useRef<HTMLButtonElement>(null)
  const sidebarRef = useRef<HTMLElement>(null)
  const wasOpenRef = useRef(false)

  useEffect(() => {
    if (!isSidebarOpen) {
      document.body.classList.remove('drawer-open')
      if (wasOpenRef.current) menuButtonRef.current?.focus()
      wasOpenRef.current = false
      return
    }

    wasOpenRef.current = true
    document.body.classList.add('drawer-open')
    closeButtonRef.current?.focus()

    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        setIsSidebarOpen(false)
        return
      }

      if (event.key !== 'Tab' || !sidebarRef.current) return

      const focusableElements = Array.from(
        sidebarRef.current.querySelectorAll<HTMLElement>(
          'button:not([disabled]), [href], [tabindex]:not([tabindex="-1"])',
        ),
      )
      const firstElement = focusableElements[0]
      const lastElement = focusableElements.at(-1)

      if (event.shiftKey && document.activeElement === firstElement) {
        event.preventDefault()
        lastElement?.focus()
      } else if (!event.shiftKey && document.activeElement === lastElement) {
        event.preventDefault()
        firstElement?.focus()
      }
    }

    document.addEventListener('keydown', handleKeyDown)
    return () => {
      document.removeEventListener('keydown', handleKeyDown)
      document.body.classList.remove('drawer-open')
    }
  }, [isSidebarOpen])

  return (
    <div className="app-shell">
      <Header
        isSidebarOpen={isSidebarOpen}
        menuButtonRef={menuButtonRef}
        onOpenSidebar={() => setIsSidebarOpen(true)}
      />

      <div className="app-layout">
        <Sidebar
          closeButtonRef={closeButtonRef}
          isOpen={isSidebarOpen}
          sidebarRef={sidebarRef}
          onClose={() => setIsSidebarOpen(false)}
          activePage={activePage}
          onNavigate={onNavigate}
        />

        {isSidebarOpen && (
          <button
            className="drawer-overlay"
            type="button"
            aria-label="Close workspace menu"
            onClick={() => setIsSidebarOpen(false)}
          />
        )}

        <main className="main-content">{children}</main>
      </div>
    </div>
  )
}

export default MainLayout
