/**
 * API Client for DexAI Dashboard
 *
 * Provides typed fetch wrappers for all dashboard API endpoints.
 */

// API URL configuration:
// - With Caddy proxy: use '' (empty) for relative URLs - recommended
// - Without proxy: set NEXT_PUBLIC_API_URL to browser-accessible URL (e.g., http://hostname:8080)
const API_URL = process.env.NEXT_PUBLIC_API_URL ?? '';

// Types
export interface ApiResponse<T> {
  success: boolean;
  data?: T;
  error?: string;
}

export interface DexStatus {
  state: string;
  currentTask?: string;
  lastActivity?: string;
  uptime?: number;
}

export interface Task {
  id: string;
  status: 'pending' | 'running' | 'completed' | 'failed';
  request: string;
  channel?: string;
  startTime?: string;
  endTime?: string;
  duration?: number;
  cost?: number;
  toolsUsed?: string[];
  response?: string;
  error?: string;
}

export interface ActivityEvent {
  id: string;
  type: 'message' | 'task' | 'system' | 'error' | 'llm' | 'security';
  timestamp: string;
  summary: string;
  channel?: string;
  details?: string;
  severity?: 'info' | 'warning' | 'error';
}

export interface MetricsSummary {
  tasksToday: number;
  tasksWeek: number;
  messagesToday: number;
  messagesWeek: number;
  costToday: number;
  costWeek: number;
  costMonth: number;
  avgResponseTime: number;
  taskCompletionRate: number;
  errorRate: number;
}

export interface TimeSeriesPoint {
  timestamp: string;
  value: number;
}

export interface TimeSeriesData {
  metric: string;
  data: TimeSeriesPoint[];
}

export interface AuditEvent {
  id: string;
  eventType: string;
  timestamp: string;
  userId?: string;
  action: string;
  resource?: string;
  status: 'success' | 'failure';
  details?: string;
  ipAddress?: string;
}

export interface Settings {
  general: {
    displayName: string;
    timezone: string;
    language: string;
  };
  notifications: {
    activeHoursStart: string;
    activeHoursEnd: string;
    hyperfocusEnabled: boolean;
    urgentBypassHyperfocus: boolean;
  };
  privacy: {
    dataRetentionDays: number;
    rememberConversations: boolean;
    rememberPreferences: boolean;
  };
  advanced: {
    defaultModel: string;
    costLimitDaily: number;
    costLimitMonthly: number;
    debugMode: boolean;
  };
}

export interface HealthCheck {
  service: string;
  status: 'healthy' | 'degraded' | 'unhealthy';
  latency?: number;
  message?: string;
}

export interface SystemInfo {
  version: string;
  uptime_seconds: number;
  python_version: string;
  platform: string;
  databases: Record<string, number>;
  channels: string[];
  active_tasks: number;
  environment: string;
  debug_mode: boolean;
  timestamp: string;
}

// Channel token types
export interface ChannelTokensResponse {
  telegram: {
    configured: boolean;
    masked_token: string;
  };
  discord: {
    configured: boolean;
    masked_token: string;
  };
  slack: {
    configured: boolean;
    masked_bot_token: string;
    masked_app_token: string;
  };
  anthropic: {
    configured: boolean;
    masked_key: string;
  };
  openrouter: {
    configured: boolean;
    masked_key: string;
  };
  openai: {
    configured: boolean;
    masked_key: string;
  };
  google: {
    configured: boolean;
    masked_key: string;
  };
}

export interface ChannelTokensUpdateRequest {
  telegram_token?: string;
  discord_token?: string;
  slack_bot_token?: string;
  slack_app_token?: string;
  anthropic_key?: string;
  openrouter_key?: string;
  openai_key?: string;
  google_key?: string;
}

// Setup wizard types
export interface SetupState {
  is_complete: boolean;
  current_step: string;
  completed_steps: string[];
  progress_percent: number;
  primary_channel: string | null;
  user_name: string | null;
  started_at: string | null;
  last_updated: string | null;
  detected_timezone: string;
}

export interface ChannelValidateRequest {
  channel: string;
  token?: string;
  bot_token?: string;
  app_token?: string;
}

export interface ChannelValidateResponse {
  success: boolean;
  bot_id?: string;
  bot_username?: string;
  bot_name?: string;
  team_name?: string;
  error?: string;
}

export interface SetupPreferences {
  user_name?: string;
  timezone: string;
  active_hours_start: string;
  active_hours_end: string;
}

export interface CompleteSetupRequest {
  channel?: string;
  channel_config?: Record<string, string>;
  preferences?: SetupPreferences;
  api_key?: string;
  skip_api_key?: boolean;
}

// Office Integration types (Phase 12b)
export interface OfficeAccount {
  id: string;
  provider: 'google' | 'microsoft';
  email_address: string;
  integration_level: number;
  integration_level_name: string;
  is_active: boolean;
  last_sync: string | null;
  created_at: string;
}

export interface OfficeDraft {
  id: string;
  account_id: string;
  provider_draft_id: string | null;
  subject: string | null;
  recipients: string[];
  cc: string[] | null;
  bcc: string[] | null;
  body_text: string | null;
  body_preview: string | null;
  status: 'pending' | 'approved' | 'sent' | 'deleted';
  sentiment_score: number | null;
  sentiment_flags: string[] | null;
  created_at: string;
  updated_at: string;
}

export interface MeetingProposal {
  id: string;
  account_id: string;
  provider_event_id: string | null;
  title: string;
  description: string | null;
  location: string | null;
  start_time: string;
  end_time: string;
  timezone: string | null;
  attendees: string[] | null;
  organizer_email: string | null;
  status: 'proposed' | 'confirmed' | 'cancelled';
  conflicts: MeetingConflict[] | null;
  created_at: string;
}

export interface MeetingConflict {
  event_id: string;
  title: string;
  start_time: string;
  end_time: string;
}

export interface TimeSuggestion {
  start: string;
  end: string;
  score: number;
  reason: string;
}

export interface DraftCreateRequest {
  account_id: string;
  to: string[];
  subject: string;
  body: string;
  cc?: string[];
  bcc?: string[];
  reply_to_message_id?: string;
  check_sentiment?: boolean;
}

export interface MeetingProposalRequest {
  account_id: string;
  title: string;
  start_time: string;
  end_time?: string;
  duration_minutes?: number;
  attendees?: string[];
  description?: string;
  location?: string;
  timezone?: string;
  check_availability?: boolean;
}

// Chat types
export interface ChatMessageResponse {
  conversation_id: string;
  message_id: string;
  content: string;
  role: 'assistant';
  model?: string;
  complexity?: string;
  cost_usd?: number;
  tool_uses?: { tool: string; input: unknown }[];
  error?: string;
  created_at?: string;
}

export interface ChatHistoryMessage {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  model?: string;
  complexity?: string;
  cost_usd?: number;
  tool_uses?: { tool: string; input: unknown }[];
  created_at: string;
}

export interface ChatHistoryResponse {
  conversation_id: string;
  messages: ChatHistoryMessage[];
  total: number;
}

export interface ChatConversation {
  id: string;
  title?: string;
  last_message?: string;
  created_at: string;
  updated_at: string;
}

// Memory types
export interface MemorySearchResult {
  id: string;
  content: string;
  score: number;
  entry_type?: string;
  source?: string;
  created_at?: string;
}

export interface MemorySearchResponse {
  query: string;
  results: MemorySearchResult[];
  total: number;
  method: string;
}

export interface MemoryCommitment {
  id: string;
  content: string;
  target_person?: string;
  due_date?: string;
  status: string;
  created_at: string;
  source?: string;
}

export interface MemoryContext {
  id: string;
  title: string;
  summary?: string;
  task_description?: string;
  created_at: string;
  restored_at?: string;
}

export interface MemoryProvider {
  name: string;
  status: 'active' | 'inactive' | 'error';
  is_primary: boolean;
  storage_used?: string;
  health_score?: number;
  last_sync?: string;
  error?: string;
}

// Task action types
export interface CurrentTask {
  id: string;
  title: string;
  description?: string;
  status: string;
  energy_required: string;
  estimated_time?: string;
  category?: string;
  created_at: string;
}

export interface FrictionItem {
  task_id: string;
  task_title: string;
  blocker: string;
  suggested_action?: string;
  confidence: number;
}

export interface FlowState {
  is_in_flow: boolean;
  flow_start_time?: string;
  duration_minutes: number;
  intensity: 'none' | 'building' | 'deep' | 'fading';
}

// Pagination params
export interface PaginationParams {
  page?: number;
  limit?: number;
}

// Filter params
export interface TaskFilters extends PaginationParams {
  status?: string;
  channel?: string;
  startDate?: string;
  endDate?: string;
}

export interface ActivityFilters extends PaginationParams {
  type?: string;
  severity?: string;
  search?: string;
  startDate?: string;
  endDate?: string;
}

export interface AuditFilters extends PaginationParams {
  eventType?: string;
  userId?: string;
  status?: string;
  startDate?: string;
  endDate?: string;
}

// API Client class
class ApiClient {
  private baseUrl: string;

  constructor(baseUrl: string = API_URL) {
    this.baseUrl = baseUrl;
  }

  private async request<T>(
    endpoint: string,
    options: RequestInit = {}
  ): Promise<ApiResponse<T>> {
    try {
      const url = `${this.baseUrl}${endpoint}`;
      const response = await fetch(url, {
        ...options,
        headers: {
          'Content-Type': 'application/json',
          ...options.headers,
        },
        credentials: 'include',
      });

      if (!response.ok) {
        const error = await response.text();
        return { success: false, error: error || `HTTP ${response.status}` };
      }

      const data = await response.json();
      return { success: true, data };
    } catch (error) {
      return {
        success: false,
        error: error instanceof Error ? error.message : 'Unknown error',
      };
    }
  }

  private buildQuery(params: Record<string, unknown>): string {
    const filtered = Object.entries(params)
      .filter(([, v]) => v !== undefined && v !== null && v !== '')
      .map(([k, v]) => `${encodeURIComponent(k)}=${encodeURIComponent(String(v))}`);
    return filtered.length > 0 ? `?${filtered.join('&')}` : '';
  }

  // Status endpoints
  async getStatus(): Promise<ApiResponse<DexStatus>> {
    return this.request<DexStatus>('/api/status');
  }

  // ==========================================================================
  // Chat endpoints
  // ==========================================================================

  async sendChatMessage(
    message: string,
    conversationId?: string
  ): Promise<ApiResponse<ChatMessageResponse>> {
    return this.request<ChatMessageResponse>('/api/chat/message', {
      method: 'POST',
      body: JSON.stringify({ message, conversation_id: conversationId }),
    });
  }

  async getChatHistory(
    conversationId: string,
    limit?: number
  ): Promise<ApiResponse<ChatHistoryResponse>> {
    const query = this.buildQuery({ conversation_id: conversationId, limit });
    return this.request<ChatHistoryResponse>(`/api/chat/history${query}`);
  }

  async getChatConversations(
    limit?: number
  ): Promise<ApiResponse<{ conversations: ChatConversation[]; total: number }>> {
    const query = this.buildQuery({ limit });
    return this.request<{ conversations: ChatConversation[]; total: number }>(
      `/api/chat/conversations${query}`
    );
  }

  async createChatConversation(): Promise<ApiResponse<{ success: boolean; conversation_id: string }>> {
    return this.request<{ success: boolean; conversation_id: string }>(
      '/api/chat/conversations',
      { method: 'POST' }
    );
  }

  async deleteChatConversation(
    conversationId: string
  ): Promise<ApiResponse<{ success: boolean }>> {
    return this.request<{ success: boolean }>(
      `/api/chat/conversations/${conversationId}`,
      { method: 'DELETE' }
    );
  }

  // ==========================================================================
  // Memory endpoints
  // ==========================================================================

  async searchMemory(
    query: string,
    limit?: number,
    method?: string
  ): Promise<ApiResponse<MemorySearchResponse>> {
    const params = this.buildQuery({ q: query, limit, method });
    return this.request<MemorySearchResponse>(`/api/memory/search${params}`);
  }

  async getCommitments(
    status?: string,
    limit?: number
  ): Promise<ApiResponse<{ commitments: MemoryCommitment[]; total: number }>> {
    const params = this.buildQuery({ status, limit });
    return this.request<{ commitments: MemoryCommitment[]; total: number }>(
      `/api/memory/commitments${params}`
    );
  }

  async getCommitmentsCount(): Promise<ApiResponse<{ count: number }>> {
    return this.request<{ count: number }>('/api/memory/commitments/count');
  }

  async getContextSnapshots(
    limit?: number
  ): Promise<ApiResponse<{ contexts: MemoryContext[]; total: number }>> {
    const params = this.buildQuery({ limit });
    return this.request<{ contexts: MemoryContext[]; total: number }>(
      `/api/memory/contexts${params}`
    );
  }

  async restoreContext(
    contextId: string
  ): Promise<ApiResponse<{ success: boolean; context: MemoryContext }>> {
    return this.request<{ success: boolean; context: MemoryContext }>(
      `/api/memory/contexts/${contextId}/restore`,
      { method: 'POST' }
    );
  }

  async getMemoryProviders(): Promise<
    ApiResponse<{ providers: MemoryProvider[]; active_count: number; primary_provider?: string }>
  > {
    return this.request<{
      providers: MemoryProvider[];
      active_count: number;
      primary_provider?: string;
    }>('/api/memory/providers');
  }

  // ==========================================================================
  // Extended Task endpoints
  // ==========================================================================

  async getCurrentTask(): Promise<ApiResponse<{ current_task: CurrentTask | null; message?: string }>> {
    return this.request<{ current_task: CurrentTask | null; message?: string }>('/api/tasks/current');
  }

  async createTask(data: {
    title: string;
    description?: string;
    energy_required?: string;
    estimated_time?: string;
    category?: string;
  }): Promise<ApiResponse<{ success: boolean; task_id: string; action: string; message?: string }>> {
    return this.request<{ success: boolean; task_id: string; action: string; message?: string }>(
      '/api/tasks',
      {
        method: 'POST',
        body: JSON.stringify(data),
      }
    );
  }

  async markTaskStuck(
    taskId: string
  ): Promise<ApiResponse<{ success: boolean; task_id: string; action: string; data?: unknown }>> {
    return this.request<{ success: boolean; task_id: string; action: string; data?: unknown }>(
      `/api/tasks/${taskId}/stuck`,
      { method: 'POST' }
    );
  }

  async decomposeTask(
    taskId: string
  ): Promise<
    ApiResponse<{ success: boolean; task_id: string; action: string; data?: { subtasks: unknown[] } }>
  > {
    return this.request<{
      success: boolean;
      task_id: string;
      action: string;
      data?: { subtasks: unknown[] };
    }>(`/api/tasks/${taskId}/decompose`, { method: 'POST' });
  }

  async skipTask(
    taskId: string
  ): Promise<ApiResponse<{ success: boolean; task_id: string; action: string; message?: string }>> {
    return this.request<{ success: boolean; task_id: string; action: string; message?: string }>(
      `/api/tasks/${taskId}/skip`,
      { method: 'PATCH' }
    );
  }

  async completeTask(
    taskId: string
  ): Promise<ApiResponse<{ success: boolean; task_id: string; action: string; message?: string }>> {
    return this.request<{ success: boolean; task_id: string; action: string; message?: string }>(
      `/api/tasks/${taskId}/complete`,
      { method: 'PATCH' }
    );
  }

  async getTaskFriction(): Promise<ApiResponse<{ friction_items: FrictionItem[]; total: number }>> {
    return this.request<{ friction_items: FrictionItem[]; total: number }>('/api/tasks/friction');
  }

  // ==========================================================================
  // Settings extensions
  // ==========================================================================

  async getEnergyLevel(): Promise<ApiResponse<{ level: string; options: string[] }>> {
    return this.request<{ level: string; options: string[] }>('/api/settings/energy');
  }

  async setEnergyLevel(
    level: string
  ): Promise<ApiResponse<{ success: boolean; level: string; message?: string }>> {
    return this.request<{ success: boolean; level: string; message?: string }>(
      '/api/settings/energy',
      {
        method: 'POST',
        body: JSON.stringify({ level }),
      }
    );
  }

  // ==========================================================================
  // Metrics extensions
  // ==========================================================================

  async getFlowState(): Promise<ApiResponse<FlowState>> {
    return this.request<FlowState>('/api/metrics/flow');
  }

  // Task endpoints
  async getTasks(filters?: TaskFilters): Promise<ApiResponse<{ tasks: Task[]; total: number }>> {
    const query = this.buildQuery((filters || {}) as Record<string, unknown>);
    return this.request<{ tasks: Task[]; total: number }>(`/api/tasks${query}`);
  }

  async getTask(id: string): Promise<ApiResponse<Task>> {
    return this.request<Task>(`/api/tasks/${id}`);
  }

  // Activity endpoints
  async getActivity(
    filters?: ActivityFilters
  ): Promise<ApiResponse<{ events: ActivityEvent[]; total: number }>> {
    const query = this.buildQuery((filters || {}) as Record<string, unknown>);
    return this.request<{ events: ActivityEvent[]; total: number }>(`/api/activity${query}`);
  }

  // Metrics endpoints
  async getMetricsSummary(): Promise<ApiResponse<MetricsSummary>> {
    return this.request<MetricsSummary>('/api/metrics/summary');
  }

  async getTimeSeries(
    metric: string,
    startDate?: string,
    endDate?: string
  ): Promise<ApiResponse<TimeSeriesData>> {
    const query = this.buildQuery({ metric, startDate, endDate });
    return this.request<TimeSeriesData>(`/api/metrics/timeseries${query}`);
  }

  // Audit endpoints
  async getAuditLog(
    filters?: AuditFilters
  ): Promise<ApiResponse<{ events: AuditEvent[]; total: number }>> {
    const query = this.buildQuery((filters || {}) as Record<string, unknown>);
    return this.request<{ events: AuditEvent[]; total: number }>(`/api/audit${query}`);
  }

  // Settings endpoints
  async getSettings(): Promise<ApiResponse<Settings>> {
    return this.request<Settings>('/api/settings');
  }

  async updateSettings(settings: Partial<Settings>): Promise<ApiResponse<Settings>> {
    return this.request<Settings>('/api/settings', {
      method: 'PATCH',
      body: JSON.stringify(settings),
    });
  }

  // Channel token endpoints
  async getChannelTokens(): Promise<ApiResponse<ChannelTokensResponse>> {
    return this.request<ChannelTokensResponse>('/api/settings/tokens');
  }

  async updateChannelTokens(
    tokens: ChannelTokensUpdateRequest
  ): Promise<ApiResponse<{ success: boolean; message?: string; error?: string; updated: string[] }>> {
    return this.request<{ success: boolean; message?: string; error?: string; updated: string[] }>(
      '/api/settings/tokens',
      {
        method: 'PUT',
        body: JSON.stringify(tokens),
      }
    );
  }

  // Health endpoints
  async getHealth(): Promise<ApiResponse<{ checks: HealthCheck[] }>> {
    return this.request<{ checks: HealthCheck[] }>('/api/health');
  }

  // Audit statistics
  async getAuditStats(
    days?: number
  ): Promise<ApiResponse<{
    period_days: number;
    total_events: number;
    by_type: Record<string, number>;
    by_severity: Record<string, number>;
    by_day: { day: string; count: number }[];
  }>> {
    const query = this.buildQuery({ days });
    return this.request<{
      period_days: number;
      total_events: number;
      by_type: Record<string, number>;
      by_severity: Record<string, number>;
      by_day: { day: string; count: number }[];
    }>(`/api/audit/stats${query}`);
  }

  // Debug endpoints (admin only)
  async getSystemInfo(): Promise<ApiResponse<SystemInfo>> {
    return this.request<SystemInfo>('/api/debug/system');
  }

  async getLogs(
    lines?: number,
    level?: string,
    source?: string
  ): Promise<ApiResponse<{ logs: string[]; total: number; source: string }>> {
    const query = this.buildQuery({ lines, level, source });
    return this.request<{ logs: string[]; total: number; source: string }>(`/api/debug/logs${query}`);
  }

  async runDebugTool(
    toolName: string
  ): Promise<ApiResponse<{ tool: string; success: boolean; message: string; results?: unknown }>> {
    return this.request<{ tool: string; success: boolean; message: string; results?: unknown }>(
      `/api/debug/tools/${toolName}`,
      { method: 'POST' }
    );
  }

  async queryDatabase(
    table: string,
    limit?: number
  ): Promise<ApiResponse<{ rows: Record<string, unknown>[]; columns: string[]; table: string; total: number; error?: string }>> {
    const query = this.buildQuery({ table, limit });
    return this.request<{ rows: Record<string, unknown>[]; columns: string[]; table: string; total: number; error?: string }>(
      `/api/debug/db${query}`
    );
  }

  async getDebugMetrics(): Promise<ApiResponse<{
    timestamp: string;
    memory: Record<string, number | string>;
    requests: Record<string, number | string>;
    performance: Record<string, number | string>;
  }>> {
    return this.request<{
      timestamp: string;
      memory: Record<string, number | string>;
      requests: Record<string, number | string>;
      performance: Record<string, number | string>;
    }>('/api/debug/metrics');
  }

  // Setup wizard endpoints
  async getSetupState(): Promise<ApiResponse<SetupState>> {
    return this.request<SetupState>('/api/setup/state');
  }

  async validateChannel(
    request: ChannelValidateRequest
  ): Promise<ApiResponse<ChannelValidateResponse>> {
    return this.request<ChannelValidateResponse>('/api/setup/channel/validate', {
      method: 'POST',
      body: JSON.stringify(request),
    });
  }

  async validateApiKey(
    api_key: string,
    provider: string = 'anthropic'
  ): Promise<ApiResponse<{ success: boolean; error?: string }>> {
    return this.request<{ success: boolean; error?: string }>('/api/setup/apikey/validate', {
      method: 'POST',
      body: JSON.stringify({ api_key, provider }),
    });
  }

  async completeSetup(
    request: CompleteSetupRequest
  ): Promise<ApiResponse<{ success: boolean; message?: string; error?: string }>> {
    return this.request<{ success: boolean; message?: string; error?: string }>(
      '/api/setup/complete',
      {
        method: 'POST',
        body: JSON.stringify(request),
      }
    );
  }

  async resetSetup(): Promise<ApiResponse<{ success: boolean; message?: string }>> {
    return this.request<{ success: boolean; message?: string }>('/api/setup/reset', {
      method: 'POST',
    });
  }

  // ==========================================================================
  // Office Integration endpoints (Phase 12b)
  // ==========================================================================

  // Accounts
  async getOfficeAccounts(): Promise<ApiResponse<OfficeAccount[]>> {
    return this.request<OfficeAccount[]>('/api/office/accounts');
  }

  async getOfficeAccount(accountId: string): Promise<ApiResponse<OfficeAccount>> {
    return this.request<OfficeAccount>(`/api/office/accounts/${accountId}`);
  }

  async updateOfficeAccountLevel(
    accountId: string,
    level: number
  ): Promise<ApiResponse<{ success: boolean; integration_level: number }>> {
    return this.request<{ success: boolean; integration_level: number }>(
      `/api/office/accounts/${accountId}/level?level=${level}`,
      { method: 'PUT' }
    );
  }

  // Drafts
  async getOfficeDrafts(
    accountId: string,
    status: string = 'pending',
    limit: number = 20
  ): Promise<ApiResponse<{ drafts: OfficeDraft[]; total: number }>> {
    const query = this.buildQuery({ account_id: accountId, status, limit });
    return this.request<{ drafts: OfficeDraft[]; total: number }>(`/api/office/drafts${query}`);
  }

  async getOfficeDraft(draftId: string): Promise<ApiResponse<OfficeDraft>> {
    return this.request<OfficeDraft>(`/api/office/drafts/${draftId}`);
  }

  async createOfficeDraft(
    request: DraftCreateRequest
  ): Promise<ApiResponse<{ success: boolean; draft_id: string; sentiment_analysis: unknown }>> {
    return this.request<{ success: boolean; draft_id: string; sentiment_analysis: unknown }>(
      '/api/office/drafts',
      {
        method: 'POST',
        body: JSON.stringify(request),
      }
    );
  }

  async approveOfficeDraft(
    draftId: string,
    sendImmediately: boolean = false
  ): Promise<ApiResponse<{ success: boolean; status: string }>> {
    return this.request<{ success: boolean; status: string }>(
      `/api/office/drafts/${draftId}/approve?send_immediately=${sendImmediately}`,
      { method: 'POST' }
    );
  }

  async deleteOfficeDraft(draftId: string): Promise<ApiResponse<{ success: boolean }>> {
    return this.request<{ success: boolean }>(`/api/office/drafts/${draftId}`, {
      method: 'DELETE',
    });
  }

  // Meetings
  async getOfficeMeetings(
    accountId: string,
    status: string = 'proposed',
    limit: number = 20
  ): Promise<ApiResponse<{ proposals: MeetingProposal[]; total: number }>> {
    const query = this.buildQuery({ account_id: accountId, status, limit });
    return this.request<{ proposals: MeetingProposal[]; total: number }>(
      `/api/office/meetings${query}`
    );
  }

  async getOfficeMeeting(proposalId: string): Promise<ApiResponse<MeetingProposal>> {
    return this.request<MeetingProposal>(`/api/office/meetings/${proposalId}`);
  }

  async createOfficeMeeting(
    request: MeetingProposalRequest
  ): Promise<ApiResponse<{ success: boolean; proposal_id: string; conflicts: MeetingConflict[] }>> {
    return this.request<{
      success: boolean;
      proposal_id: string;
      conflicts: MeetingConflict[];
    }>('/api/office/meetings', {
      method: 'POST',
      body: JSON.stringify(request),
    });
  }

  async confirmOfficeMeeting(
    proposalId: string
  ): Promise<ApiResponse<{ success: boolean; event_id: string; status: string }>> {
    return this.request<{ success: boolean; event_id: string; status: string }>(
      `/api/office/meetings/${proposalId}/confirm`,
      { method: 'POST' }
    );
  }

  async cancelOfficeMeeting(proposalId: string): Promise<ApiResponse<{ success: boolean }>> {
    return this.request<{ success: boolean }>(`/api/office/meetings/${proposalId}`, {
      method: 'DELETE',
    });
  }

  async getOfficeMeetingSuggestions(
    accountId: string,
    durationMinutes: number = 30,
    daysAhead: number = 7
  ): Promise<ApiResponse<TimeSuggestion[]>> {
    const query = this.buildQuery({
      account_id: accountId,
      duration_minutes: durationMinutes,
      days_ahead: daysAhead,
    });
    return this.request<TimeSuggestion[]>(`/api/office/suggest-times${query}`);
  }

  // OAuth
  async getOAuthAuthorizationUrl(
    provider: 'google' | 'microsoft',
    integrationLevel: number = 2
  ): Promise<ApiResponse<{ authorization_url: string }>> {
    return this.request<{ authorization_url: string }>(
      `/api/oauth/authorize/${provider}?integration_level=${integrationLevel}`
    );
  }

  async getOAuthStatus(): Promise<
    ApiResponse<
      {
        provider: string;
        connected: boolean;
        email: string | null;
        integration_level: number | null;
      }[]
    >
  > {
    return this.request<
      {
        provider: string;
        connected: boolean;
        email: string | null;
        integration_level: number | null;
      }[]
    >('/api/oauth/status');
  }

  async revokeOAuth(accountId: string): Promise<ApiResponse<{ success: boolean; message: string }>> {
    return this.request<{ success: boolean; message: string }>('/api/oauth/revoke', {
      method: 'POST',
      body: JSON.stringify({ account_id: accountId }),
    });
  }

  // ==========================================================================
  // Push Notification endpoints (Phase 10a)
  // ==========================================================================

  async getVapidKey(): Promise<ApiResponse<{ public_key: string }>> {
    return this.request<{ public_key: string }>('/api/push/vapid-key');
  }

  async subscribePush(
    userId: string,
    subscription: {
      endpoint: string;
      p256dh: string;
      auth: string;
      device_name?: string;
      device_type?: string;
      browser?: string;
    }
  ): Promise<ApiResponse<{ success: boolean; subscription_id: string }>> {
    return this.request<{ success: boolean; subscription_id: string }>(
      `/api/push/subscribe?user_id=${userId}`,
      {
        method: 'POST',
        body: JSON.stringify(subscription),
      }
    );
  }

  async unsubscribePush(
    subscriptionId: string
  ): Promise<ApiResponse<{ success: boolean }>> {
    return this.request<{ success: boolean }>(
      `/api/push/subscribe/${subscriptionId}`,
      { method: 'DELETE' }
    );
  }

  async getPushSubscriptions(
    userId: string
  ): Promise<ApiResponse<PushSubscription[]>> {
    return this.request<PushSubscription[]>(
      `/api/push/subscriptions?user_id=${userId}`
    );
  }

  async sendTestPush(
    userId: string,
    title?: string,
    body?: string
  ): Promise<ApiResponse<{ success: boolean; sent_to: number }>> {
    return this.request<{ success: boolean; sent_to: number }>(
      `/api/push/test?user_id=${userId}`,
      {
        method: 'POST',
        body: JSON.stringify({ title, body }),
      }
    );
  }

  async getPushPreferences(userId: string): Promise<ApiResponse<PushPreferences>> {
    return this.request<PushPreferences>(
      `/api/push/preferences?user_id=${userId}`
    );
  }

  async updatePushPreferences(
    userId: string,
    preferences: Partial<PushPreferences>
  ): Promise<ApiResponse<PushPreferences>> {
    return this.request<PushPreferences>(
      `/api/push/preferences?user_id=${userId}`,
      {
        method: 'PUT',
        body: JSON.stringify(preferences),
      }
    );
  }

  async getPushCategories(): Promise<
    ApiResponse<{ categories: PushCategory[] }>
  > {
    return this.request<{ categories: PushCategory[] }>('/api/push/categories');
  }

  async updatePushCategoryPreference(
    userId: string,
    categoryId: string,
    setting: { enabled: boolean; priority_threshold?: number; batch?: boolean }
  ): Promise<ApiResponse<{ success: boolean }>> {
    return this.request<{ success: boolean }>(
      `/api/push/categories/${categoryId}?user_id=${userId}`,
      {
        method: 'PUT',
        body: JSON.stringify(setting),
      }
    );
  }

  async getPushHistory(
    userId: string,
    limit?: number
  ): Promise<ApiResponse<{ notifications: PushNotification[]; total: number }>> {
    const query = this.buildQuery({ user_id: userId, limit });
    return this.request<{ notifications: PushNotification[]; total: number }>(
      `/api/push/history${query}`
    );
  }

  async getPushStats(
    userId?: string,
    days?: number
  ): Promise<ApiResponse<PushStats>> {
    const query = this.buildQuery({ user_id: userId, days });
    return this.request<PushStats>(`/api/push/stats${query}`);
  }

  // ==========================================================================
  // Service Management endpoints
  // ==========================================================================

  async getServices(): Promise<ApiResponse<ServiceStatus[]>> {
    return this.request<ServiceStatus[]>('/api/services');
  }

  async getServiceStatus(name: string): Promise<ApiResponse<ServiceStatus>> {
    return this.request<ServiceStatus>(`/api/services/${name}`);
  }

  async startService(name: string): Promise<ApiResponse<ServiceAction>> {
    return this.request<ServiceAction>(`/api/services/${name}/start`, {
      method: 'POST',
    });
  }

  async stopService(name: string): Promise<ApiResponse<ServiceAction>> {
    return this.request<ServiceAction>(`/api/services/${name}/stop`, {
      method: 'POST',
    });
  }

  async restartService(name: string): Promise<ApiResponse<ServiceAction>> {
    return this.request<ServiceAction>(`/api/services/${name}/restart`, {
      method: 'POST',
    });
  }

  async getServiceHealth(name: string): Promise<ApiResponse<ServiceHealth>> {
    return this.request<ServiceHealth>(`/api/services/${name}/health`);
  }
}

// Push notification types
export interface PushSubscription {
  id: string;
  device_name: string | null;
  device_type: string;
  browser: string | null;
  is_active: boolean;
  created_at: string;
  last_used_at: string | null;
}

export interface PushPreferences {
  enabled: boolean;
  quiet_hours_start: string | null;
  quiet_hours_end: string | null;
  timezone: string;
  respect_flow_state: boolean;
  flow_interrupt_threshold: number;
  batch_notifications: boolean;
  batch_window_minutes: number;
  max_notifications_per_hour: number;
  category_settings: Record<string, { enabled: boolean; priority_threshold: number; batch?: boolean }>;
}

export interface PushCategory {
  id: string;
  name: string;
  description: string;
  default_priority: number;
  can_batch: boolean;
  can_suppress: boolean;
  color: string;
}

export interface PushNotification {
  id: string;
  category: string;
  title: string;
  body: string | null;
  priority: number;
  created_at: string;
  delivery_status: string;
  sent_at: string | null;
  clicked_at: string | null;
}

export interface PushStats {
  period_days: number;
  total_sent: number;
  total_delivered: number;
  total_clicked: number;
  total_dismissed: number;
  delivery_rate: number;
  click_rate: number;
  dismiss_rate: number;
  by_category: Record<string, { total: number; clicked: number; click_rate: number }>;
  by_day: { day: string; total: number; clicked: number }[];
}

// Service Management types
export interface ServiceStatus {
  name: string;
  display_name: string;
  status: 'running' | 'stopped' | 'error' | 'unknown';
  connected: boolean;
  last_activity: string | null;
  error: string | null;
  config_status: 'configured' | 'unconfigured' | 'partial';
  uptime_seconds: number | null;
}

export interface ServiceAction {
  success: boolean;
  service: string;
  action: string;
  message: string | null;
  error: string | null;
}

export interface ServiceHealth {
  service: string;
  timestamp: string;
  overall: 'healthy' | 'unhealthy' | 'degraded';
  checks: Record<string, { status: string; detail: unknown }>;
}

// Export singleton instance
export const api = new ApiClient();

// Export class for custom instances
export { ApiClient };
