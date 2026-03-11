import type React from 'react';
import { useCallback, useEffect, useState } from 'react';
import { historyApi } from '../api/history';
import { getParsedApiError, type ParsedApiError } from '../api/error';
import type { HistoryItem, AnalysisReport } from '../types/analysis';
import { getSentimentColor, getSentimentLabel } from '../types/analysis';
import { formatDateTime } from '../utils/format';
import { getReportText, normalizeReportLanguage } from '../utils/reportLanguage';
import { Pagination, EmptyState, Button, Drawer, Badge, ApiErrorAlert, Input, Select, Checkbox } from '../components/common';
import { ReportSummary, ReportMarkdown } from '../components/report';
import { History, Calendar, Filter, RefreshCw } from 'lucide-react';

const DEFAULT_PAGE_SIZE = 6;

interface AnalysisHistoryTableProps {
  className?: string;
}

// 获取今天的日期字符串 YYYY-MM-DD
const getTodayString = (): string => {
  const today = new Date();
  const year = today.getFullYear();
  const month = String(today.getMonth() + 1).padStart(2, '0');
  const day = String(today.getDate()).padStart(2, '0');
  return `${year}-${month}-${day}`;
};

/**
 * 分析历史表格组件
 * 展示股票名称、股票代码、sentiment_score、操作建议、趋势、理想买入点、二次买入点、止损价格、止盈价格
 */
export const AnalysisHistoryTable: React.FC<AnalysisHistoryTableProps> = ({ className = '' }) => {
  const [items, setItems] = useState<HistoryItem[]>([]);
  const [total, setTotal] = useState(0);
  const [currentPage, setCurrentPage] = useState(1);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<ParsedApiError | null>(null);

  // 筛选条件
  const [analysisDate, setAnalysisDate] = useState<string>(getTodayString());
  const [dailyDedup, setDailyDedup] = useState(true);
  const [sortBy, setSortBy] = useState<'created_at' | 'sentiment_score'>('sentiment_score');
  const [pageSize, setPageSize] = useState<number>(DEFAULT_PAGE_SIZE);

  // 报告详情抽屉
  const [selectedReport, setSelectedReport] = useState<AnalysisReport | null>(null);
  const [reportDrawerOpen, setReportDrawerOpen] = useState(false);
  const [isLoadingReport, setIsLoadingReport] = useState(false);

  // Markdown 完整报告抽屉
  const [markdownDrawerOpen, setMarkdownDrawerOpen] = useState(false);

  const totalPages = Math.ceil(total / pageSize);

  // 加载历史列表
  const loadHistory = useCallback(async (page: number) => {
    setIsLoading(true);
    setError(null);
    try {
      const response = await historyApi.getList({
        page,
        limit: pageSize,
        analysisDate: analysisDate || undefined,
        dailyDedup,
        sortBy,
      });
      setItems(response.items);
      setTotal(response.total);
      setCurrentPage(response.page);
    } catch (err) {
      setError(getParsedApiError(err));
    } finally {
      setIsLoading(false);
    }
  }, [analysisDate, dailyDedup, sortBy, pageSize]);

  useEffect(() => {
    void loadHistory(1);
  }, [loadHistory]);

  // 重置筛选
  const handleResetFilters = useCallback(() => {
    setAnalysisDate(getTodayString());
    setDailyDedup(true);
    setSortBy('sentiment_score');
    setPageSize(DEFAULT_PAGE_SIZE);
  }, []);

  // 查看完整报告
  const handleViewReport = useCallback(async (item: HistoryItem) => {
    if (!item.id) return;

    setIsLoadingReport(true);
    try {
      const report = await historyApi.getDetail(item.id);
      setSelectedReport(report);
      setReportDrawerOpen(true);
    } catch (err) {
      console.error('加载报告详情失败:', err);
    } finally {
      setIsLoadingReport(false);
    }
  }, []);

  // 打开 Markdown 完整报告
  const handleOpenMarkdown = useCallback(() => {
    setMarkdownDrawerOpen(true);
  }, []);

  // 关闭 Markdown 完整报告
  const handleCloseMarkdown = useCallback(() => {
    setMarkdownDrawerOpen(false);
  }, []);

  // 导出当天所有股票分析报告
  const handleExportBatch = useCallback(async () => {
    try {
      await historyApi.exportBatchMarkdown(analysisDate);
    } catch (err) {
      console.error('Failed to export batch report:', err);
      setError(getParsedApiError(err));
    }
  }, [analysisDate]);

  // 格式化价格显示
  const formatPrice = (price?: string) => {
    if (!price || price === 'N/A' || price === 'None') return '-';
    return price;
  };

  // 获取情绪标签
  const getSentimentDisplay = (score?: number) => {
    if (score === undefined) return { label: '-', color: '#9ca3af' };
    return {
      label: getSentimentLabel(score, 'zh'),
      color: getSentimentColor(score),
    };
  };

  return (
      <div className={`flex flex-col h-full ${className}`}>
        {/* 标题区 */}
        <div className="flex items-center justify-between mb-4 flex-shrink-0">
          <div className="flex items-center gap-2">
            <History className="h-5 w-5 text-primary" />
            <h1 className="text-xl font-semibold text-foreground">分析历史</h1>
            <Badge variant="info" size="sm">
              共 {total} 条
            </Badge>
          </div>
          <Button
            variant="primary"
            size="sm"
            onClick={handleExportBatch}
            className="flex items-center gap-2"
          >
            <svg className="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4" />
            </svg>
            导出报告
          </Button>
        </div>

        {/* 筛选区 */}
        <div className="glass-card rounded-2xl p-4 mb-4 flex-shrink-0">
          <div className="flex items-center gap-2 mb-3">
            <Filter className="h-4 w-4 text-secondary-text" />
            <span className="text-sm font-medium text-foreground">筛选条件</span>
          </div>
          <div className="flex flex-wrap gap-4 items-end">
            <div className="w-40">
              <Input
                  label="分析日期"
                  type="date"
                  value={analysisDate}
                  onChange={(e) => setAnalysisDate(e.target.value)}
                  placeholder="YYYY-MM-DD"
              />
            </div>
            <div className="w-40">
              <Select
                  label="排序方式"
                  value={sortBy}
                  onChange={(value) => setSortBy(value as 'created_at' | 'sentiment_score')}
                  options={[
                    { value: 'sentiment_score', label: '按得分排序' },
                    { value: 'created_at', label: '按时间排序' },
                  ]}
              />
            </div>
            <div className="w-32">
              <Select
                  label="每页数量"
                  value={String(pageSize)}
                  onChange={(value) => {
                    setPageSize(Number(value));
                    setCurrentPage(1);
                  }}
                  options={[
                    { value: '6', label: '6条' },
                    { value: '12', label: '12条' },
                    { value: '24', label: '24条' },
                    { value: '50', label: '50条' },
                  ]}
              />
            </div>
            <div className="flex items-center gap-2 pb-1">
              <Checkbox
                  id="daily-dedup"
                  checked={dailyDedup}
                  onChange={(e) => setDailyDedup(e.target.checked)}
                  label="按天去重"
              />
            </div>
            <Button
                variant="ghost"
                size="sm"
                onClick={handleResetFilters}
                className="flex items-center gap-1"
            >
              <RefreshCw className="h-4 w-4" />
              重置
            </Button>
          </div>
          {dailyDedup && (
              <p className="text-xs text-muted-text mt-2 flex items-center gap-1">
                <Calendar className="h-3 w-3" />
                同一天同一股票只保留最新的一条记录
              </p>
          )}
        </div>

        {/* 错误提示 */}
        {error && (
            <div className="mb-4 flex-shrink-0">
              <ApiErrorAlert error={error} onDismiss={() => setError(null)} />
            </div>
        )}

        {/* 表格区 */}
        <div className="flex-1 overflow-hidden glass-card rounded-2xl">
          {isLoading && items.length === 0 ? (
              <div className="flex h-full items-center justify-center py-20">
                <div className="flex flex-col items-center gap-3">
                  <div className="h-8 w-8 animate-spin rounded-full border-2 border-cyan/20 border-t-cyan" />
                  <span className="text-sm text-secondary-text">加载中...</span>
                </div>
              </div>
          ) : items.length === 0 ? (
              <div className="py-20">
                <EmptyState
                    title="暂无分析记录"
                    description="完成首次股票分析后，这里会展示分析历史记录。"
                    icon={
                      <History className="h-6 w-6" />
                    }
                />
              </div>
          ) : (
              <div className="h-full overflow-y-auto">
                <table className="w-full table-fixed">
                  <thead className="sticky top-0 z-10 bg-surface/80 backdrop-blur-sm border-b border-border/50">
                  <tr>
                    <th className="w-[11%] px-3 py-3 text-left text-xs font-medium text-secondary-text uppercase tracking-wider">
                      股票
                    </th>
                    <th className="w-[9%] px-3 py-3 text-left text-xs font-medium text-secondary-text uppercase tracking-wider">
                      情绪评分
                    </th>
                    <th className="w-[9%] px-3 py-3 text-left text-xs font-medium text-secondary-text uppercase tracking-wider">
                      操作建议
                    </th>
                    <th className="w-[8%] px-3 py-3 text-left text-xs font-medium text-secondary-text uppercase tracking-wider">
                      趋势
                    </th>
                    <th className="w-[9%] px-3 py-3 text-left text-xs font-medium text-secondary-text uppercase tracking-wider">
                      时效性
                    </th>
                    <th className="w-[8%] px-3 py-3 text-left text-xs font-medium text-secondary-text uppercase tracking-wider">
                      理想买入
                    </th>
                    <th className="w-[8%] px-3 py-3 text-left text-xs font-medium text-secondary-text uppercase tracking-wider">
                      二次买入
                    </th>
                    <th className="w-[7%] px-3 py-3 text-left text-xs font-medium text-secondary-text uppercase tracking-wider">
                      止损价
                    </th>
                    <th className="w-[7%] px-3 py-3 text-left text-xs font-medium text-secondary-text uppercase tracking-wider">
                      止盈价
                    </th>
                    <th className="w-[12%] px-3 py-3 text-left text-xs font-medium text-secondary-text uppercase tracking-wider">
                      分析时间
                    </th>
                    <th className="w-[8%] px-3 py-3 text-left text-xs font-medium text-secondary-text uppercase tracking-wider">
                      操作
                    </th>
                  </tr>
                  </thead>
                  <tbody className="divide-y divide-border/30">
                  {items.map((item) => {
                    const sentiment = getSentimentDisplay(item.sentimentScore);
                    return (
                        <tr
                            key={item.id}
                            className="hover:bg-hover/50 transition-colors group"
                        >
                          {/* 股票信息 */}
                          <td className="px-3 py-3">
                            <div className="flex flex-col">
                          <span className="text-sm font-medium text-foreground break-words">
                            {item.stockName || item.stockCode}
                          </span>
                              <span className="text-xs text-muted-text font-mono break-all">
                            {item.stockCode}
                          </span>
                            </div>
                          </td>

                          {/* 情绪评分 */}
                          <td className="px-3 py-3">
                            {item.sentimentScore !== undefined ? (
                                <div className="flex items-center gap-2">
                                  <div
                                      className="w-2 h-6 rounded-full flex-shrink-0"
                                      style={{
                                        backgroundColor: sentiment.color,
                                        boxShadow: `0 0 8px ${sentiment.color}40`,
                                      }}
                                  />
                                  <div className="flex flex-col min-w-0">
                              <span
                                  className="text-sm font-semibold"
                                  style={{ color: sentiment.color }}
                              >
                                {item.sentimentScore}
                              </span>
                                    <span className="text-[10px] text-muted-text">
                                {sentiment.label}
                              </span>
                                  </div>
                                </div>
                            ) : (
                                <span className="text-muted-text">-</span>
                            )}
                          </td>

                          {/* 操作建议 */}
                          <td className="px-3 py-3">
                        <span className="text-sm text-foreground break-words">
                          {item.operationAdvice || '-'}
                        </span>
                          </td>

                          {/* 趋势 */}
                          <td className="px-3 py-3">
                        <span className="text-sm text-foreground break-words">
                          {item.trendPrediction || '-'}
                        </span>
                          </td>

                          {/* 时效性 */}
                          <td className="px-3 py-3">
                        <span className="text-sm text-foreground break-words">
                          {item.timeSensitivity || '-'}
                        </span>
                          </td>

                          {/* 理想买入 */}
                          <td className="px-3 py-3">
                        <span className="text-sm font-mono text-emerald-400 break-all">
                          {formatPrice(item.idealBuy)}
                        </span>
                          </td>

                          {/* 二次买入 */}
                          <td className="px-3 py-3">
                        <span className="text-sm font-mono text-cyan-400 break-all">
                          {formatPrice(item.secondaryBuy)}
                        </span>
                          </td>

                          {/* 止损价 */}
                          <td className="px-3 py-3">
                        <span className="text-sm font-mono text-red-400 break-all">
                          {formatPrice(item.stopLoss)}
                        </span>
                          </td>

                          {/* 止盈价 */}
                          <td className="px-3 py-3">
                        <span className="text-sm font-mono text-amber-400 break-all">
                          {formatPrice(item.takeProfit)}
                        </span>
                          </td>

                          {/* 分析时间 */}
                          <td className="px-3 py-3">
                        <span className="text-xs text-muted-text break-words">
                          {formatDateTime(item.createdAt)}
                        </span>
                          </td>

                          {/* 操作按钮 */}
                          <td className="px-3 py-3">
                            <Button
                                variant="ghost"
                                size="xsm"
                                onClick={() => void handleViewReport(item)}
                                isLoading={isLoadingReport && selectedReport?.meta.id === item.id}
                                className="opacity-0 group-hover:opacity-100 transition-opacity"
                            >
                              查看报告
                            </Button>
                          </td>
                        </tr>
                    );
                  })}
                  </tbody>
                </table>
              </div>
          )}
        </div>

        {/* 分页 */}
        {totalPages > 1 && (
            <div className="mt-4 flex-shrink-0">
              <Pagination
                  currentPage={currentPage}
                  totalPages={totalPages}
                  onPageChange={(page) => void loadHistory(page)}
              />
            </div>
        )}

        {/* 报告详情抽屉 */}
        <Drawer
            isOpen={reportDrawerOpen}
            onClose={() => setReportDrawerOpen(false)}
            title={
              selectedReport
                  ? `${selectedReport.meta.stockName || selectedReport.meta.stockCode} (${selectedReport.meta.stockCode})`
                  : '报告详情'
            }
            width="max-w-3xl"
        >
          {isLoadingReport ? (
              <div className="flex h-full items-center justify-center py-20">
                <div className="flex flex-col items-center gap-3">
                  <div className="h-8 w-8 animate-spin rounded-full border-2 border-cyan/20 border-t-cyan" />
                  <span className="text-sm text-secondary-text">加载报告中...</span>
                </div>
              </div>
          ) : selectedReport ? (
              <div className="h-full overflow-y-auto">
                <div className="flex flex-wrap items-center justify-end gap-2 mb-4">
                  <Button
                      variant="home-action-ai"
                      size="sm"
                      disabled={selectedReport.meta.id === undefined}
                      onClick={handleOpenMarkdown}
                  >
                    <svg className="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
                    </svg>
                    {getReportText(normalizeReportLanguage(selectedReport.meta.reportLanguage)).fullReport}
                  </Button>
                </div>
                <ReportSummary data={selectedReport} isHistory />
              </div>
          ) : null}
        </Drawer>

        {/* Markdown 完整报告抽屉 */}
        {markdownDrawerOpen && selectedReport?.meta.id ? (
            <ReportMarkdown
                recordId={selectedReport.meta.id}
                stockName={selectedReport.meta.stockName || ''}
                stockCode={selectedReport.meta.stockCode}
                reportLanguage={normalizeReportLanguage(selectedReport.meta.reportLanguage)}
                onClose={handleCloseMarkdown}
            />
        ) : null}
      </div>
  );
};

/**
 * 分析历史页面
 */
const AnalysisHistoryPage: React.FC = () => {
  useEffect(() => {
    document.title = '分析历史 - DSA';
  }, []);

  return (
      <div className="h-[calc(100vh-5rem)] sm:h-[calc(100vh-5.5rem)] lg:h-[calc(100vh-2rem)]">
        <AnalysisHistoryTable />
      </div>
  );
};

export default AnalysisHistoryPage;
