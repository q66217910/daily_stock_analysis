import type React from 'react';
import { useCallback, useEffect, useRef, useState } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { historyApi } from '../api/history';
import { getParsedApiError, type ParsedApiError } from '../api/error';
import { Button, Input, Card, Badge, ApiErrorAlert, EmptyState } from '../components/common';
import { FileText, Search, Download, AlertCircle } from 'lucide-react';

const getTodayString = (): string => {
  const today = new Date();
  const year = today.getFullYear();
  const month = String(today.getMonth() + 1).padStart(2, '0');
  const day = String(today.getDate()).padStart(2, '0');
  return `${year}-${month}-${day}`;
};

const ReportExtractPage: React.FC = () => {
  useEffect(() => {
    document.title = '提取报告 - DSA';
  }, []);

  // 输入
  const [stockCodesInput, setStockCodesInput] = useState('');
  const [analysisDate, setAnalysisDate] = useState(getTodayString());

  // 结果
  const [markdownContent, setMarkdownContent] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [hasSearched, setHasSearched] = useState(false);
  const [error, setError] = useState<ParsedApiError | null>(null);
  const [missingCodes, setMissingCodes] = useState<string[]>([]);

  const resultRef = useRef<HTMLDivElement>(null);

  // 解析股票代码
  const parseStockCodes = useCallback((): string[] => {
    return stockCodesInput
      .split(/[,;\n，；\s]+/)
      .map(code => code.trim())
      .filter(code => code.length > 0);
  }, [stockCodesInput]);

  // 提取报告
  const handleExtract = useCallback(async () => {
    const codes = parseStockCodes();
    if (codes.length === 0) return;

    setIsLoading(true);
    setError(null);
    setHasSearched(true);
    setMissingCodes([]);
    setMarkdownContent(null);

    try {
      // 先通过表格接口获取数据，判断哪些股票有报告
      const listResponse = await historyApi.extractReports(codes, analysisDate);

      // 找出未匹配的股票代码
      const matchedCodes = new Set(listResponse.items.map(item => item.stockCode.toUpperCase()));
      const unmatched = codes.filter(code => !matchedCodes.has(code.toUpperCase()));
      setMissingCodes(unmatched);

      // 通过 POST 获取 markdown 文本内容（不使用 blob 下载）
      const response = await historyApi.getExtractMarkdownText(codes, analysisDate);
      setMarkdownContent(response);
    } catch (err) {
      setError(getParsedApiError(err));
      setMarkdownContent(null);
    } finally {
      setIsLoading(false);
    }
  }, [parseStockCodes, analysisDate]);

  // 下载 Markdown 文件
  const handleDownload = useCallback(async () => {
    const codes = parseStockCodes();
    if (codes.length === 0) return;

    try {
      await historyApi.exportExtractMarkdown(codes, analysisDate);
    } catch (err) {
      setError(getParsedApiError(err));
    }
  }, [parseStockCodes, analysisDate]);

  // 提取成功后滚动到结果区域
  useEffect(() => {
    if (markdownContent && resultRef.current) {
      resultRef.current.scrollIntoView({ behavior: 'smooth', block: 'start' });
    }
  }, [markdownContent]);

  return (
    <div className="flex h-[calc(100vh-5rem)] flex-col sm:h-[calc(100vh-5.5rem)] lg:h-[calc(100vh-2rem)]">
      {/* 标题区 */}
      <div className="mb-4 flex items-center justify-between flex-shrink-0">
        <div className="flex items-center gap-2">
          <FileText className="h-5 w-5 text-primary" />
          <h1 className="text-xl font-semibold text-foreground">提取报告</h1>
        </div>
      </div>

      {/* 输入区 */}
      <Card className="mb-4 flex-shrink-0">
        <div className="p-4">
          <div className="flex flex-wrap gap-4 items-start">
            <div className="flex-1 min-w-[300px]">
              <label className="mb-2 block text-sm font-medium text-foreground">
                股票代码列表
              </label>
              <textarea
                value={stockCodesInput}
                onChange={(e) => setStockCodesInput(e.target.value)}
                placeholder={'输入股票代码，用逗号、空格或换行分隔\n例如: 600519, 000001, 300750'}
                className="input-surface input-focus-glow h-28 w-full rounded-xl border bg-transparent px-4 py-3 text-sm transition-all focus:outline-none resize-y"
                disabled={isLoading}
              />
              <p className="mt-1.5 text-xs text-secondary-text">
                支持 A 股（如 600519）、港股（如 00700）、美股（如 AAPL）
              </p>
            </div>
            <div className="w-44">
              <Input
                label="分析日期"
                type="date"
                value={analysisDate}
                onChange={(e) => setAnalysisDate(e.target.value)}
                placeholder="YYYY-MM-DD"
                disabled={isLoading}
              />
            </div>
            <div className="flex items-end gap-2 pt-1">
              <Button
                variant="primary"
                size="md"
                onClick={() => void handleExtract()}
                isLoading={isLoading}
                loadingText="提取中..."
                disabled={!stockCodesInput.trim() || !analysisDate}
                className="flex items-center gap-2"
              >
                <Search className="h-4 w-4" />
                提取报告
              </Button>
            </div>
          </div>
        </div>
      </Card>

      {/* 错误提示 */}
      {error && (
        <div className="mb-4 flex-shrink-0">
          <ApiErrorAlert error={error} onDismiss={() => setError(null)} />
        </div>
      )}

      {/* 未匹配提示 */}
      {missingCodes.length > 0 && (
        <div className="mb-4 flex-shrink-0">
          <div className="rounded-2xl border border-warning/30 bg-warning/5 p-4">
            <div className="flex items-start gap-3">
              <AlertCircle className="mt-0.5 h-4 w-4 shrink-0 text-warning" />
              <div className="text-sm text-foreground">
                <span className="font-medium">以下股票在 {analysisDate} 未找到分析记录：</span>
                <span className="ml-1 text-muted-text">{missingCodes.join(', ')}</span>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* 结果区 */}
      <div className="flex-1 overflow-hidden" ref={resultRef}>
        {isLoading ? (
          <div className="flex h-full items-center justify-center py-20">
            <div className="flex flex-col items-center gap-3">
              <div className="h-8 w-8 animate-spin rounded-full border-2 border-cyan/20 border-t-cyan" />
              <span className="text-sm text-secondary-text">生成报告中...</span>
            </div>
          </div>
        ) : !hasSearched ? (
          <div className="py-20">
            <EmptyState
              title="输入股票代码开始提取"
              description={'在上方输入股票代码列表并选择日期，点击「提取报告」按钮获取 Markdown 格式的分析报告。'}
              icon={<FileText className="h-6 w-6" />}
            />
          </div>
        ) : markdownContent !== null && hasSearched ? (
          <Card className="h-full flex flex-col">
            {/* 操作栏 */}
            <div className="flex items-center justify-between px-4 py-3 border-b border-border/50 flex-shrink-0">
              <div className="flex items-center gap-2">
                <Badge variant="info" size="sm">
                  Markdown 报告
                </Badge>
                {analysisDate && (
                  <span className="text-xs text-secondary-text">{analysisDate}</span>
                )}
              </div>
              <Button
                variant="outline"
                size="sm"
                onClick={() => void handleDownload()}
                className="flex items-center gap-2"
              >
                <Download className="h-4 w-4" />
                下载 .md 文件
              </Button>
            </div>

            {/* Markdown 内容 */}
            <div className="flex-1 overflow-y-auto p-4">
              <div className="prose prose-sm dark:prose-invert max-w-none">
                <ReactMarkdown remarkPlugins={[remarkGfm]}>
                  {markdownContent}
                </ReactMarkdown>
              </div>
            </div>
          </Card>
        ) : (
          <div className="py-20">
            <EmptyState
              title="未找到匹配的报告"
              description={`在 ${analysisDate} 未找到指定股票的分析记录。请检查股票代码或日期是否正确。`}
              icon={<Search className="h-6 w-6" />}
            />
          </div>
        )}
      </div>
    </div>
  );
};

export default ReportExtractPage;
