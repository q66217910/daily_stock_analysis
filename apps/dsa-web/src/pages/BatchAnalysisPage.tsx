import type React from 'react';
import { useCallback, useState, useEffect, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import { Button, Card, ApiErrorAlert } from '../components/common';
import { getParsedApiError } from '../api/error';
import { analysisApi } from '../api/analysis';
import { historyApi } from '../api/history';
import { validateStockCode, looksLikeStockCode } from '../utils/validation';
import { useTaskStream } from '../hooks/useTaskStream';
import type { TaskInfo } from '../types/analysis';

// 策略定义
const STRATEGIES = [
  { id: 'bull_trend', label: '多头趋势', description: 'MA5 > MA10 > MA20 排列 + 低乖离率' },
  { id: 'ma_golden_cross', label: '均线金叉', description: 'MA5 上穿 MA10/MA20' },
  { id: 'volume_breakout', label: '放量突破', description: '价格突破近期高点 + 成交量放大' },
  { id: 'shrink_pullback', label: '缩量回踩', description: '回踩均线 + 量能萎缩，低吸点' },
  { id: 'bottom_volume', label: '底部放量', description: '地量见地价，底部反转信号' },
  { id: 'dragon_head', label: '龙头策略', description: '强势龙头，趋势延续追涨' },
  { id: 'one_yang_three_yin', label: '一阳夹三阴', description: '主力洗盘后强势反包形态' },
  { id: 'box_oscillation', label: '箱体震荡', description: '区间高抛低吸' },
  { id: 'chan_theory', label: '缠论', description: '缠中说禅理论：笔/线段/中枢' },
  { id: 'wave_theory', label: '波浪理论', description: '艾略特波浪计数' },
  { id: 'emotion_cycle', label: '情绪周期', description: '市场情绪高低点轮动' },
  { id: 'boll_pullback', label: '布林带回踩', description: '缩量回踩布林中轨顺势买点' },
];

// 任务状态类型
interface TaskState {
  taskId: string;
  stockCode: string;
  stockName?: string;
  status: 'pending' | 'processing' | 'completed' | 'failed';
  progress: number;
  message?: string;
  recordId?: number;
  error?: string;
}

// 格式化日期为 YYYY-MM-DD
const formatDate = (date: Date): string => {
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, '0');
  const day = String(date.getDate()).padStart(2, '0');
  return `${year}-${month}-${day}`;
};

// 下载 Markdown 内容到本地
const downloadMarkdown = (content: string, filename: string): void => {
  const blob = new Blob([content], { type: 'text/markdown;charset=utf-8' });
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.setAttribute('download', filename);
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
  URL.revokeObjectURL(url);
};

const BatchAnalysisPage: React.FC = () => {
  const navigate = useNavigate();
  const [stockInput, setStockInput] = useState('');
  const [selectedStrategies, setSelectedStrategies] = useState<string[]>([]);
  const [isAnalyzing, setIsAnalyzing] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const [inputError, setInputError] = useState<string | undefined>();
  const [tasks, setTasks] = useState<Map<string, TaskState>>(new Map());
  const [showTaskList, setShowTaskList] = useState(false);
  const [allTasksCompleted, setAllTasksCompleted] = useState(false);
  const pendingTaskIdsRef = useRef<Set<string>>(new Set());
  const analysisDateRef = useRef<string>(formatDate(new Date()));

  // SSE 任务流连接
  useTaskStream({
    enabled: showTaskList,
    onTaskCreated: (task: TaskInfo) => {
      if (pendingTaskIdsRef.current.has(task.taskId)) {
        setTasks((prev) =>
          new Map(prev).set(task.taskId, {
            taskId: task.taskId,
            stockCode: task.stockCode,
            stockName: task.stockName,
            status: task.status as TaskState['status'],
            progress: task.progress,
            message: task.message,
          })
        );
      }
    },
    onTaskStarted: (task: TaskInfo) => {
      if (pendingTaskIdsRef.current.has(task.taskId)) {
        setTasks((prev) => {
          const existing = prev.get(task.taskId);
          if (existing) {
            const updated: TaskState = {
              taskId: existing.taskId,
              stockCode: existing.stockCode,
              stockName: existing.stockName,
              status: task.status as TaskState['status'],
              progress: task.progress,
              message: task.message,
              recordId: existing.recordId,
              error: existing.error,
            };
            return new Map(prev).set(task.taskId, updated);
          }
          return prev;
        });
      }
    },
    onTaskProgress: (task: TaskInfo) => {
      if (pendingTaskIdsRef.current.has(task.taskId)) {
        setTasks((prev) => {
          const existing = prev.get(task.taskId);
          if (existing) {
            const updated: TaskState = {
              taskId: existing.taskId,
              stockCode: existing.stockCode,
              stockName: existing.stockName,
              status: task.status as TaskState['status'],
              progress: task.progress,
              message: task.message,
              recordId: existing.recordId,
              error: existing.error,
            };
            return new Map(prev).set(task.taskId, updated);
          }
          return prev;
        });
      }
    },
    onTaskCompleted: async (task: TaskInfo) => {
      if (pendingTaskIdsRef.current.has(task.taskId)) {
        // 获取记录 ID
        let recordId: number | undefined;
        try {
          const historyList = await historyApi.getList({
            analysisDate: analysisDateRef.current,
            limit: 100,
          });
          const matchingRecord = historyList.items.find(
            (item) => item.stockCode === task.stockCode
          );
          recordId = matchingRecord?.id;
        } catch (err) {
          console.error('Failed to fetch record ID:', err);
        }

        setTasks((prev) => {
          const existing = prev.get(task.taskId);
          if (existing) {
            const updated: TaskState = {
              taskId: existing.taskId,
              stockCode: existing.stockCode,
              stockName: existing.stockName,
              status: 'completed',
              progress: 100,
              message: task.message,
              recordId,
              error: undefined,
            };
            return new Map(prev).set(task.taskId, updated);
          }
          return prev;
        });
      }
    },
    onTaskFailed: (task: TaskInfo) => {
      if (pendingTaskIdsRef.current.has(task.taskId)) {
        setTasks((prev) => {
          const existing = prev.get(task.taskId);
          if (existing) {
            const updated: TaskState = {
              taskId: existing.taskId,
              stockCode: existing.stockCode,
              stockName: existing.stockName,
              status: 'failed',
              progress: 0,
              message: task.message,
              recordId: existing.recordId,
              error: task.error,
            };
            return new Map(prev).set(task.taskId, updated);
          }
          return prev;
        });
      }
    },
  });

  // 检查所有任务是否完成
  useEffect(() => {
    if (tasks.size === 0 || !showTaskList) return;

    const taskArray = Array.from(tasks.values());
    const allDone = taskArray.every(
      (t) => t.status === 'completed' || t.status === 'failed'
    );

    if (allDone && pendingTaskIdsRef.current.size > 0) {
      setAllTasksCompleted(true);
    }
  }, [tasks, showTaskList]);

  // 解析股票代码输入
  const parseStockCodes = useCallback((input: string): string[] => {
    return input
      .split(/[,\n\s;]+/)
      .map((code) => code.trim())
      .filter((code) => code.length > 0);
  }, []);

  // 验证股票代码
  const validateStockCodes = useCallback(
    (codes: string[]): { valid: string[]; invalid: string[] } => {
      const valid: string[] = [];
      const invalid: string[] = [];

      for (const code of codes) {
        if (looksLikeStockCode(code)) {
          const { valid: isValid, normalized } = validateStockCode(code);
          if (isValid && normalized) {
            valid.push(normalized);
          } else {
            invalid.push(code);
          }
        } else {
          invalid.push(code);
        }
      }

      return { valid, invalid };
    },
    []
  );

  // 切换策略选择
  const toggleStrategy = useCallback((strategyId: string) => {
    setSelectedStrategies((prev) => {
      if (prev.includes(strategyId)) {
        return prev.filter((id) => id !== strategyId);
      } else {
        return [...prev, strategyId];
      }
    });
  }, []);

  // 全选/取消全选策略
  const toggleAllStrategies = useCallback(() => {
    if (selectedStrategies.length === STRATEGIES.length) {
      setSelectedStrategies([]);
    } else {
      setSelectedStrategies(STRATEGIES.map((s) => s.id));
    }
  }, [selectedStrategies.length]);

  // 提交批量分析
  const handleSubmit = useCallback(async () => {
    const stockCodes = parseStockCodes(stockInput);

    if (stockCodes.length === 0) {
      setInputError('请输入至少一个股票代码');
      return;
    }

    const { valid, invalid } = validateStockCodes(stockCodes);

    if (invalid.length > 0) {
      setInputError(`以下股票代码无效：${invalid.join(', ')}`);
      return;
    }

    if (selectedStrategies.length === 0) {
      setInputError('请至少选择一个策略');
      return;
    }

    setInputError(undefined);
    setError(null);
    setIsAnalyzing(true);
    setShowTaskList(false);
    setAllTasksCompleted(false);
    setTasks(new Map());
    analysisDateRef.current = formatDate(new Date());

    try {
      const response = await analysisApi.analyzeAsync({
        stockCodes: valid,
        reportType: 'detailed',
        asyncMode: true,
        agentSkills: selectedStrategies,
      });

      // 初始化任务状态
      const newTasks = new Map<string, TaskState>();
      const newPendingIds = new Set<string>();

      if ('accepted' in response) {
        response.accepted.forEach((item) => {
          newTasks.set(item.taskId, {
            taskId: item.taskId,
            stockCode: item.stockCode,
            status: 'pending',
            progress: 0,
            message: '等待分析...',
          });
          newPendingIds.add(item.taskId);
        });
        response.duplicates.forEach((item) => {
          newTasks.set(item.existingTaskId, {
            taskId: item.existingTaskId,
            stockCode: item.stockCode,
            status: 'pending',
            progress: 0,
            message: '已有任务在运行中...',
          });
          newPendingIds.add(item.existingTaskId);
        });
      } else if ('taskId' in response) {
        // 单个任务响应
        newTasks.set(response.taskId, {
          taskId: response.taskId,
          stockCode: valid[0] || '',
          status: 'pending',
          progress: 0,
          message: '等待分析...',
        });
        newPendingIds.add(response.taskId);
      }

      setTasks(newTasks);
      pendingTaskIdsRef.current = newPendingIds;
      setShowTaskList(true);

      // 成功后清空输入
      setStockInput('');
    } catch (err) {
      setError(err);
    } finally {
      setIsAnalyzing(false);
    }
  }, [stockInput, selectedStrategies, parseStockCodes, validateStockCodes]);

  // 重置任务列表
  const handleResetTasks = useCallback(() => {
    setShowTaskList(false);
    setTasks(new Map());
    setAllTasksCompleted(false);
    pendingTaskIdsRef.current.clear();
  }, []);

  // 下载单个报告
  const handleDownloadReport = useCallback(async (task: TaskState) => {
    if (!task.recordId) return;

    try {
      const markdown = await historyApi.getMarkdown(task.recordId);
      const filename = `${task.stockCode}_${task.stockName || 'analysis'}_${analysisDateRef.current}.md`;
      downloadMarkdown(markdown, filename);
    } catch (err) {
      console.error('Failed to download report:', err);
    }
  }, []);

  // 批量下载所有报告
  const handleDownloadAllReports = useCallback(async () => {
    const completedTasks = Array.from(tasks.values()).filter(
      (t) => t.status === 'completed' && t.recordId
    );

    if (completedTasks.length === 0) return;

    // 收集所有报告内容
    const allReports: string[] = [];
    for (const task of completedTasks) {
      if (task.recordId) {
        try {
          const markdown = await historyApi.getMarkdown(task.recordId);
          allReports.push(markdown);
        } catch (err) {
          console.error(`Failed to fetch report for ${task.stockCode}:`, err);
        }
      }
    }

    // 合并并下载
    const combinedContent = allReports.join('\n\n' + '='.repeat(80) + '\n\n');
    const filename = `batch_analysis_report_${analysisDateRef.current}.md`;
    downloadMarkdown(combinedContent, filename);
  }, [tasks]);

  // 跳转到历史页面
  const handleGoToHistory = useCallback(() => {
    navigate('/history');
  }, [navigate]);

  // 获取状态对应的颜色
  const getStatusColor = (status: TaskState['status']): string => {
    switch (status) {
      case 'pending':
        return '#6b7280'; // gray-500
      case 'processing':
        return '#3b82f6'; // blue-500
      case 'completed':
        return '#22c55e'; // green-500
      case 'failed':
        return '#ef4444'; // red-500
      default:
        return '#6b7280';
    }
  };

  // 获取状态显示文本
  const getStatusText = (status: TaskState['status']): string => {
    switch (status) {
      case 'pending':
        return '等待中';
      case 'processing':
        return '分析中';
      case 'completed':
        return '已完成';
      case 'failed':
        return '失败';
      default:
        return '未知';
    }
  };

  const taskArray = Array.from(tasks.values());
  const completedCount = taskArray.filter((t) => t.status === 'completed').length;
  const failedCount = taskArray.filter((t) => t.status === 'failed').length;
  const totalCount = taskArray.length;

  return (
    <div className="flex min-h-[calc(100vh-8rem)] flex-col gap-6 pb-24">
      <div className="space-y-2">
        <h1 className="text-xl font-semibold text-foreground">批量策略分析</h1>
        <p className="text-sm text-secondary-text">
          批量输入股票代码，选择多个策略，一次性获取多维度的 AI 分析报告
        </p>
      </div>

      {error ? (
        <ApiErrorAlert error={getParsedApiError(error)} onDismiss={() => setError(null)} />
      ) : null}

      {/* 任务进度列表 */}
      {showTaskList && tasks.size > 0 && (
        <Card className="p-4">
          <div className="space-y-4">
            <div className="flex items-center justify-between">
              <h3 className="font-medium text-foreground">分析进度</h3>
              <div className="flex items-center gap-2 text-sm text-secondary-text">
                <span>总计: {totalCount}</span>
                <span className="text-green-500">完成: {completedCount}</span>
                {failedCount > 0 && <span className="text-red-500">失败: {failedCount}</span>}
              </div>
            </div>

            {/* 任务列表 */}
            <div className="space-y-3">
              {taskArray.map((task) => (
                <div
                  key={task.taskId}
                  className="rounded-xl border border-border/70 bg-surface/40 p-4"
                >
                  <div className="flex items-start justify-between">
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2 mb-1">
                        <span className="font-medium text-foreground">
                          {task.stockName || task.stockCode}
                        </span>
                        <span className="text-xs text-secondary-text font-mono">
                          {task.stockCode}
                        </span>
                        <span
                          className="text-xs px-2 py-0.5 rounded-full"
                          style={{
                            backgroundColor: `${getStatusColor(task.status)}20`,
                            color: getStatusColor(task.status),
                          }}
                        >
                          {getStatusText(task.status)}
                        </span>
                      </div>

                      {/* 进度条 */}
                      <div className="mt-2 mb-2">
                        <div className="h-2 w-full rounded-full bg-border/50 overflow-hidden">
                          <div
                            className="h-full rounded-full transition-all duration-300"
                            style={{
                              width: `${task.progress}%`,
                              backgroundColor: getStatusColor(task.status),
                            }}
                          />
                        </div>
                      </div>

                      {/* 消息 */}
                      {task.message && (
                        <p className="text-xs text-secondary-text">{task.message}</p>
                      )}
                      {task.error && (
                        <p className="text-xs text-red-500 mt-1">错误: {task.error}</p>
                      )}
                    </div>

                    {/* 下载按钮 */}
                    {task.status === 'completed' && task.recordId && (
                      <Button
                        variant="ghost"
                        size="sm"
                        onClick={() => handleDownloadReport(task)}
                      >
                        下载报告
                      </Button>
                    )}
                  </div>
                </div>
              ))}
            </div>

            {/* 完成后的操作按钮 */}
            {allTasksCompleted && (
              <div className="flex flex-wrap gap-2 pt-2 border-t border-border/50">
                <Button variant="primary" size="sm" onClick={handleDownloadAllReports}>
                  批量下载所有报告
                </Button>
                <Button variant="outline" size="sm" onClick={handleGoToHistory}>
                  查看分析历史
                </Button>
                <Button variant="outline" size="sm" onClick={handleResetTasks}>
                  继续分析新股票
                </Button>
              </div>
            )}

            {/* 进行中的操作按钮 */}
            {!allTasksCompleted && (
              <div className="flex gap-2 pt-2 border-t border-border/50">
                <Button variant="outline" size="sm" onClick={handleGoToHistory}>
                  查看分析历史
                </Button>
              </div>
            )}
          </div>
        </Card>
      )}

      {!showTaskList && (
        <div className="grid gap-6 lg:grid-cols-2">
          {/* 股票代码输入区域 */}
          <Card className="p-4">
            <div className="space-y-4">
              <div>
                <h3 className="mb-2 font-medium text-foreground">股票代码</h3>
                <p className="mb-3 text-xs text-secondary-text">
                  输入多个股票代码，支持逗号、换行、空格或分号分隔
                </p>
                <textarea
                  value={stockInput}
                  onChange={(e) => {
                    setStockInput(e.target.value);
                    setInputError(undefined);
                  }}
                  placeholder="例如：600519, 000001, AAPL&#10;或每行一个代码"
                  className="input-surface input-focus-glow h-36 w-full resize-none rounded-xl border bg-transparent px-4 py-3 text-sm transition-all focus:outline-none disabled:cursor-not-allowed disabled:opacity-60"
                  disabled={isAnalyzing}
                />
                {inputError ? (
                  <p className="mt-2 text-xs text-danger">{inputError}</p>
                ) : null}
                <p className="mt-2 text-xs text-secondary-text">
                  已输入 {parseStockCodes(stockInput).length} 只股票
                </p>
              </div>
            </div>
          </Card>

          {/* 策略选择区域 */}
          <Card className="p-4">
            <div className="space-y-4">
              <div className="flex items-center justify-between">
                <h3 className="font-medium text-foreground">策略选择</h3>
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={toggleAllStrategies}
                  disabled={isAnalyzing}
                >
                  {selectedStrategies.length === STRATEGIES.length ? '取消全选' : '全选'}
                </Button>
              </div>
              <div className="space-y-3 max-h-96 overflow-y-auto">
                {STRATEGIES.map((strategy) => (
                  <div
                    key={strategy.id}
                    className="rounded-xl border border-border/70 bg-surface/40 p-3 transition-all hover:bg-surface/60"
                  >
                    <div className="flex items-start gap-3">
                      <input
                        type="checkbox"
                        id={`strategy-${strategy.id}`}
                        checked={selectedStrategies.includes(strategy.id)}
                        onChange={() => toggleStrategy(strategy.id)}
                        disabled={isAnalyzing}
                        className="mt-0.5 h-4 w-4 cursor-pointer rounded border border-border/70 bg-base text-cyan transition-all focus:ring-2 focus:ring-cyan/20 focus:outline-none disabled:cursor-not-allowed disabled:opacity-50"
                      />
                      <div className="flex-1 min-w-0">
                        <label
                          htmlFor={`strategy-${strategy.id}`}
                          className="cursor-pointer block font-medium text-foreground"
                        >
                          {strategy.label}
                        </label>
                        <p className="text-xs text-secondary-text mt-0.5">
                          {strategy.description}
                        </p>
                      </div>
                    </div>
                  </div>
                ))}
              </div>
              <p className="text-xs text-secondary-text">
                已选择 {selectedStrategies.length} 个策略
              </p>
            </div>
          </Card>
        </div>
      )}

      {/* 提交按钮 */}
      {!showTaskList && (
        <div className="sticky bottom-0 z-10 flex justify-end border-t border-border/60 bg-background/85 py-4 backdrop-blur-xl">
          <Button
            onClick={handleSubmit}
            isLoading={isAnalyzing}
            loadingText="提交中..."
            disabled={!stockInput.trim() || selectedStrategies.length === 0}
            size="lg"
            glow
          >
            开始批量分析
          </Button>
        </div>
      )}
    </div>
  );
};

export default BatchAnalysisPage;
