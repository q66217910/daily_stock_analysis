import apiClient from './index';
import { toCamelCase } from './utils';
import type {
  HistoryListResponse,
  HistoryItem,
  AnalysisReport,
  NewsIntelResponse,
  NewsIntelItem,
} from '../types/analysis';

// ============ API 接口 ============

export interface GetHistoryListParams {
  page?: number;
  limit?: number;
  startDate?: string;
  endDate?: string;
  analysisDate?: string;
  dailyDedup?: boolean;
  sortBy?: 'created_at' | 'sentiment_score';
}

export const historyApi = {
  /**
   * 获取历史分析列表
   * @param params 筛选和分页参数
   */
  getList: async (params: GetHistoryListParams = {}): Promise<HistoryListResponse> => {
    const { page = 1, limit = 20, startDate, endDate, analysisDate, dailyDedup, sortBy } = params;

    const queryParams: Record<string, string | number | boolean> = { page, limit };
    if (dailyDedup !== undefined) queryParams.daily_dedup = dailyDedup;
    if (sortBy) queryParams.sort_by = sortBy;
    if (analysisDate) {
      queryParams.analysis_date = analysisDate;
    } else {
      if (startDate) queryParams.start_date = startDate;
      if (endDate) queryParams.end_date = endDate;
    }

    const response = await apiClient.get<Record<string, unknown>>('/api/v1/history', {
      params: queryParams,
    });

    const data = toCamelCase<{ total: number; page: number; limit: number; items: HistoryItem[] }>(response.data);
    return {
      total: data.total,
      page: data.page,
      limit: data.limit,
      items: data.items.map(item => toCamelCase<HistoryItem>(item)),
    };
  },

  /**
   * 获取历史报告详情
   * @param recordId 分析历史记录主键 ID（使用 ID 而非 query_id，因为 query_id 在批量分析时可能重复）
   */
  getDetail: async (recordId: number): Promise<AnalysisReport> => {
    const response = await apiClient.get<Record<string, unknown>>(`/api/v1/history/${recordId}`);
    return toCamelCase<AnalysisReport>(response.data);
  },

  /**
   * 获取历史报告关联新闻
   * @param recordId 分析历史记录主键 ID
   * @param limit 返回数量限制
   */
  getNews: async (recordId: number, limit = 20): Promise<NewsIntelResponse> => {
    const response = await apiClient.get<Record<string, unknown>>(`/api/v1/history/${recordId}/news`, {
      params: { limit },
    });

    const data = toCamelCase<NewsIntelResponse>(response.data);
    return {
      total: data.total,
      items: (data.items || []).map(item => toCamelCase<NewsIntelItem>(item)),
    };
  },

  /**
   * 获取历史报告的 Markdown 格式内容
   * @param recordId 分析历史记录主键 ID
   * @returns Markdown 格式的完整报告内容
   */
  getMarkdown: async (recordId: number): Promise<string> => {
    const response = await apiClient.get<{ content: string }>(`/api/v1/history/${recordId}/markdown`);
    return response.data.content;
  },

  /**
   * 批量删除历史记录
   * @param recordIds 分析历史记录主键 ID 列表
   */
  deleteRecords: async (recordIds: number[]): Promise<{ deleted: number }> => {
    const response = await apiClient.delete<Record<string, unknown>>('/api/v1/history', {
      data: { record_ids: recordIds },
    });

    return toCamelCase<{ deleted: number }>(response.data);
  },

  /**
   * Export batch Markdown report for a specific date
   * @param analysisDate Analysis date in YYYY-MM-DD format (optional, defaults to today)
   * @returns Promise that resolves when download starts
   */
  exportBatchMarkdown: async (analysisDate?: string): Promise<void> => {
    const params: Record<string, string | number | boolean> = {};
    if (analysisDate) {
      params.analysis_date = analysisDate;
    }

    // Use direct browser download to handle file attachment
    const queryString = Object.keys(params)
      .map(key => `${encodeURIComponent(key)}=${encodeURIComponent(params[key])}`)
      .join('&');
    const url = `/api/v1/history/batch/markdown${queryString ? '?' + queryString : ''}`;

    // Create a temporary anchor element to trigger download
    const link = document.createElement('a');
    link.href = url;
    link.setAttribute('download', analysisDate
      ? `stock_analysis_report_${analysisDate}.md`
      : `stock_analysis_report_${new Date().toISOString().split('T')[0]}.md`
    );
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
  },
};
