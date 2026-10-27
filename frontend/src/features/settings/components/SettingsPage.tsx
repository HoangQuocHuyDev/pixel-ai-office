import { useSystemStatus } from '../hooks/useSystemStatus'

function StatusBadge({ ok, children }: { ok: boolean; children: string }) {
  return <span className={`settings-status settings-status--${ok ? 'ok' : 'warning'}`}><i />{children}</span>
}

export default function SettingsPage() {
  const state = useSystemStatus()
  const status = state.status
  return <section className="settings-page" aria-labelledby="settings-title">
    <header className="settings-page__header"><div><p className="page-eyebrow">Local application</p><h1 id="settings-title">Settings</h1><p className="page-description">Review local security, AI configuration and service health.</p></div><button onClick={state.refresh} disabled={state.loading}>{state.loading ? 'Checking…' : 'Refresh status'}</button></header>
    {state.error && <div className="settings-state settings-state--error" role="alert"><strong>Backend unavailable</strong><span>{state.error}</span><button onClick={state.refresh}>Retry</button></div>}
    {state.loading && !status && <div className="settings-state">Loading system status…</div>}
    {status && <div className="settings-groups">
      <section className="settings-card"><header><h2>General</h2><p>Application identity and operating mode.</p></header><dl><div><dt>Application</dt><dd>{status.application_name}</dd></div><div><dt>Backend version</dt><dd>{status.backend_version}</dd></div><div><dt>Application mode</dt><dd><StatusBadge ok>Local-first</StatusBadge></dd></div><div><dt>Interface theme</dt><dd>Light</dd></div></dl><p className="settings-note">Theme customization is not enabled in this build, so no inactive preference is shown.</p></section>
      <section className="settings-card"><header><h2>AI Provider</h2><p>Read-only backend configuration. Secrets cannot be viewed or changed here.</p></header><dl><div><dt>Provider</dt><dd>{status.ai_provider}</dd></div><div><dt>Model</dt><dd>{status.ai_model}</dd></div><div><dt>API key</dt><dd><StatusBadge ok={status.api_key_configured}>{status.api_key_configured ? 'Configured' : 'Missing'}</StatusBadge></dd></div><div><dt>Operational status</dt><dd>Not tested — no Gemini request was made</dd></div></dl></section>
      <section className="settings-card"><header><h2>Connection Status</h2><p>Safe health checks without exposing credentials or connection details.</p></header><dl><div><dt>Backend</dt><dd><StatusBadge ok={status.backend_status === 'ok'}>{status.backend_status === 'ok' ? 'Online' : 'Unavailable'}</StatusBadge></dd></div><div><dt>Database</dt><dd><StatusBadge ok={status.database_status === 'connected'}>{status.database_status === 'connected' ? 'Connected' : 'Unavailable'}</StatusBadge></dd></div><div><dt>AI configuration</dt><dd><StatusBadge ok={status.ai_configuration_status === 'configured'}>{status.ai_configuration_status}</StatusBadge></dd></div></dl></section>
      <section className="settings-card settings-card--notice"><header><h2>Application Information</h2><p>Scope and security boundary for this installation.</p></header><dl><div><dt>Registered agents</dt><dd>{status.agents_count}</dd></div><div><dt>Network scope</dt><dd>Loopback only by default</dd></div></dl><div className="local-security-notice"><strong>Trusted local environment only</strong><p>Loopback binding and CORS reduce network exposure, but they are not authentication. Do not expose this application through a LAN bind, proxy or public tunnel.</p></div></section>
    </div>}
  </section>
}
