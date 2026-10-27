import { useRef, useState } from 'react'

import MainLayout from '../components/layout/MainLayout'
import type { WorkspacePage } from '../components/layout/Sidebar'
import ChatPanel from '../features/chat/components/ChatPanel'
import OfficeViewport from '../features/office/components/OfficeViewport'
import TasksPage from '../features/tasks/components/TasksPage'
import AgentsPage from '../features/agents/components/AgentsPage'
import WorkspaceArtifactsPage from '../features/workspace/components/WorkspacePage'
import SettingsPage from '../features/settings/components/SettingsPage'

function App() {
  const [isChatOpen, setIsChatOpen] = useState(true)
  const [activePage, setActivePage] = useState<WorkspacePage>('office')
  const [workspaceArtifactId, setWorkspaceArtifactId] = useState<number | null>(null)
  const chatButtonRef = useRef<HTMLButtonElement>(null)

  return (
    <MainLayout activePage={activePage} onNavigate={setActivePage}>
      {activePage === 'tasks' ? <TasksPage onOpenArtifact={(artifactId) => { setWorkspaceArtifactId(artifactId); setActivePage('workspace') }} /> : activePage === 'agents' ? <AgentsPage onOpenTasks={() => setActivePage('tasks')} /> : activePage === 'workspace' ? <WorkspaceArtifactsPage initialArtifactId={workspaceArtifactId} onOpenTasks={() => setActivePage('tasks')} /> : activePage === 'settings' ? <SettingsPage /> : <>
      <section className="page-intro" aria-labelledby="workspace-title">
        <p className="page-eyebrow">Office overview</p>
        <h1 id="workspace-title">Your AI Workspace</h1>
        <p className="page-description">
          Manage your AI-powered office and direct agents from one place.
        </p>
      </section>

      <div className="workspace-layout">
        <div className="workspace-layout__viewport">
          <OfficeViewport
            isChatOpen={isChatOpen}
            chatButtonRef={chatButtonRef}
            onToggleChat={() => setIsChatOpen((prev) => !prev)}
          />
        </div>

        <ChatPanel
          isOpen={isChatOpen}
          toggleButtonRef={chatButtonRef}
          onClose={() => setIsChatOpen(false)}
        />
      </div>
      </>}
    </MainLayout>
  )
}

export default App
