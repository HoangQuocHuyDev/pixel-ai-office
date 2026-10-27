export type SystemStatus = {
  backend_status: 'ok'
  database_status: 'connected' | 'unavailable'
  ai_provider: string
  ai_model: string
  api_key_configured: boolean
  ai_configuration_status: 'configured' | 'missing'
  application_mode: 'local-first'
  application_name: string
  backend_version: string
  agents_count: number
}
