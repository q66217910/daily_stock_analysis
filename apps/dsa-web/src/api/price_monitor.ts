import apiClient from './index';

// ============================================
// 类型定义
// ============================================

export type PriceMonitorStatus = {
  running: boolean;
  check_interval_seconds: number;
  watching_count: number;
  triggered_cache_count: number;
};

export type WatchingStock = {
  id: number;
  code: string;
  name?: string | null;
  sentiment_score: number;
  analysis_date: string;
  ideal_buy: number;
  secondary_buy?: number | null;
  stop_loss?: number | null;
  take_profit?: number | null;
  analysis_history_id?: number | null;
  is_active: boolean;
  triggered: boolean;
  triggered_at?: string | null;
  trigger_price?: number | null;
  note?: string | null;
  created_at: string;
  updated_at: string;
};

export type PriceAlert = {
  id: number;
  watching_stock_id: number;
  code: string;
  name?: string | null;
  alert_type: 'ideal_buy' | 'secondary_buy' | 'stop_loss' | 'take_profit';
  target_price: number;
  trigger_price: number;
  change_pct?: number | null;
  analysis_triggered: boolean;
  analysis_query_id?: string | null;
  notification_sent: boolean;
  notification_sent_at?: string | null;
  created_at: string;
};

export type AddWatchingStockRequest = {
  code: string;
  name?: string;
  sentiment_score: number;
  ideal_buy: number;
  secondary_buy?: number;
  stop_loss?: number;
  take_profit?: number;
  analysis_history_id?: number;
};

export type PriceAlertListResponse = {
  items: PriceAlert[];
  total: number;
  page: number;
  limit: number;
};

export type WatchingStockListResponse = {
  items: WatchingStock[];
  total: number;
  page: number;
  limit: number;
};

export type MonitorOperationResponse = {
  success: boolean;
  message: string;
};

// ============================================
// API 方法
// ============================================

export const priceMonitorApi = {
  /** 获取服务状态 */
  async getStatus(): Promise<PriceMonitorStatus> {
    const response = await apiClient.get('/api/v1/price-monitor/status');
    return response.data as PriceMonitorStatus;
  },

  /** 启动服务 */
  async start(): Promise<MonitorOperationResponse> {
    const response = await apiClient.post('/api/v1/price-monitor/start');
    return response.data as MonitorOperationResponse;
  },

  /** 停止服务 */
  async stop(): Promise<MonitorOperationResponse> {
    const response = await apiClient.post('/api/v1/price-monitor/stop');
    return response.data as MonitorOperationResponse;
  },

  /** 刷新盯盘列表 */
  async refreshList(): Promise<MonitorOperationResponse> {
    const response = await apiClient.post('/api/v1/price-monitor/refresh?min_score=85&days=2');
    return response.data as MonitorOperationResponse;
  },

  /** 获取盯盘列表 */
  async getWatchingList(min_score?: number): Promise<WatchingStock[]> {
    const params = min_score !== undefined ? { min_score } : {};
    const response = await apiClient.get('/api/v1/price-monitor/watching', { params });
    const data = response.data as WatchingStockListResponse;
    return data.items || [];
  },

  /** 添加盯盘股票 */
  async addWatchingStock(data: AddWatchingStockRequest): Promise<WatchingStock> {
    const response = await apiClient.post('/api/v1/price-monitor/watching', data);
    return response.data as WatchingStock;
  },

  /** 删除盯盘股票 */
  async deleteWatchingStock(id: number): Promise<MonitorOperationResponse> {
    const response = await apiClient.delete(`/api/v1/price-monitor/watching/${id}`);
    return response.data as MonitorOperationResponse;
  },

  /** 删除所有盯盘股票 */
  async deleteAllWatchingStocks(): Promise<MonitorOperationResponse> {
    const response = await apiClient.delete('/api/v1/price-monitor/watching');
    return response.data as MonitorOperationResponse;
  },

  /** 获取提醒历史 */
  async getAlerts(
    params: {
      page?: number;
      page_size?: number;
      code?: string;
      alert_type?: string;
    } = {}
  ): Promise<PriceAlertListResponse> {
    const queryParams: Record<string, any> = {};
    if (params.page) queryParams.page = params.page;
    if (params.page_size) queryParams.limit = params.page_size;
    if (params.code) queryParams.code = params.code;
    if (params.alert_type) queryParams.alert_type = params.alert_type;

    const response = await apiClient.get('/api/v1/price-monitor/alerts', { params: queryParams });
    return response.data as PriceAlertListResponse;
  },
};

// ============================================
// 工具函数
// ============================================

export function getAlertTypeLabel(type: string): string {
  const labels: Record<string, string> = {
    ideal_buy: '理想买入',
    secondary_buy: '次级买入',
    stop_loss: '止损',
    take_profit: '止盈',
  };
  return labels[type] || type;
}

export function getAlertTypeVariant(type: string): 'success' | 'warning' | 'danger' | 'info' | 'default' {
  const variants: Record<string, 'success' | 'warning' | 'danger' | 'info' | 'default'> = {
    ideal_buy: 'success',
    secondary_buy: 'info',
    stop_loss: 'danger',
    take_profit: 'warning',
  };
  return variants[type] || 'default';
}
