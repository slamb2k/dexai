/**
 * API Client for DexAI Dashboard
 *
 * Provides typed fetch wrappers for all dashboard API endpoints.
 */

const API_URL = process.env.API_URL || 'http://localhost:8080';

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

  // Health endpoints
  async getHealth(): Promise<ApiResponse<{ checks: HealthCheck[] }>> {
    return this.request<{ checks: HealthCheck[] }>('/api/health');
  }

  // Debug endpoints (admin only)
  async getLogs(
    lines?: number,
    level?: string
  ): Promise<ApiResponse<{ logs: string[] }>> {
    const query = this.buildQuery({ lines, level });
    return this.request<{ logs: string[] }>(`/api/debug/logs${query}`);
  }

  async queryDatabase(
    table: string,
    limit?: number
  ): Promise<ApiResponse<{ rows: Record<string, unknown>[]; columns: string[] }>> {
    const query = this.buildQuery({ table, limit });
    return this.request<{ rows: Record<string, unknown>[]; columns: string[] }>(
      `/api/debug/db${query}`
    );
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

  async validateApiKey(api_key: string): Promise<ApiResponse<{ success: boolean; error?: string }>> {
    return this.request<{ success: boolean; error?: string }>('/api/setup/apikey/validate', {
      method: 'POST',
      body: JSON.stringify({ api_key }),
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
}

// Export singleton instance
export const api = new ApiClient();

// Export class for custom instances
export { ApiClient };
