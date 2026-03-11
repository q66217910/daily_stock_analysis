import type React from 'react';
import { useCallback, useState } from 'react';
import { Button, Card, InlineAlert, ApiErrorAlert } from '../components/common';
import { getParsedApiError } from '../api/error';
import { analysisApi } from '../api/analysis';
import { validateStockCode, looksLikeStockCode } from '../utils/validation';

// 策略定义
const STRATEGIES = [
  { id: 'day-trade', label: '一日持股策略', description: '适合短线交易，关注日内波动和次日走势' },
  { id: 'swing', label: '波段策略', description: '捕捉中期趋势，持仓周期数天至数周' },
  { id: 'value', label: '价值投资', description: '基于基本面分析，寻找被低估的股票' },
  { id: 'growth', label: '成长策略', description: '关注高成长潜力的公司，追求长期收益' },
  { id: 'technical', label: '技术分析', description: '基于技术指标和图表形态进行分析' },
];

const BatchAnalysisPage: React.FC = () => {
  const [stockInput, setStockInput] = useState('');
  const [selectedStrategies, setSelectedStrategies] = useState<string[]>([]);
  const [isAnalyzing, setIsAnalyzing] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const [inputError, setInputError] = useState<string | undefined>();
  const [result, setResult] = useState<{ accepted: string[]; duplicates: string[]; failed: string[] } | null>(null);

  // 解析股票代码输入
  const parseStockCodes = useCallback((input: string): string[] => {
    return input
      .split(/[,\n\s;]+/)
      .map(code => code.trim())
      .filter(code => code.length > 0);
  }, []);

  // 验证股票代码
  const validateStockCodes = useCallback((codes: string[]): { valid: string[]; invalid: string[] } => {
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
  }, []);

  // 切换策略选择
  const toggleStrategy = useCallback((strategyId: string) => {
    setSelectedStrategies(prev => {
      if (prev.includes(strategyId)) {
        return prev.filter(id => id !== strategyId);
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
      setSelectedStrategies(STRATEGIES.map(s => s.id));
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
    setResult(null);
    setIsAnalyzing(true);

    try {
      const response = await analysisApi.analyzeAsync({
        stockCodes: valid,
        reportType: 'detailed',
        asyncMode: true,
        agentSkills: selectedStrategies,
      });

      // 处理响应结果
      if ('accepted' in response) {
        setResult({
          accepted: response.accepted.map(item => item.stockCode),
          duplicates: response.duplicates.map(item => item.stockCode),
          failed: [],
        });
      } else {
        // TaskAccepted 响应，没有 stockCode 信息
        setResult({
          accepted: valid.length > 0 ? [valid[0]] : [],
          duplicates: [],
          failed: valid.length > 1 ? valid.slice(1) : [],
        });
      }

      // 成功后清空输入
      setStockInput('');
    } catch (err) {
      setError(err);
    } finally {
      setIsAnalyzing(false);
    }
  }, [stockInput, selectedStrategies, parseStockCodes, validateStockCodes]);

  return (
    <div className="flex min-h-[calc(100vh-8rem)] flex-col gap-6">
      <div className="space-y-2">
        <h1 className="text-xl font-semibold text-foreground">批量策略分析</h1>
        <p className="text-sm text-secondary-text">
          批量输入股票代码，选择多个策略，一次性获取多维度的 AI 分析报告
        </p>
      </div>

      {error ? (
        <ApiErrorAlert error={getParsedApiError(error)} onDismiss={() => setError(null)} />
      ) : null}

      {result ? (
        <Card className="p-4">
          <div className="space-y-3">
            <h3 className="font-medium text-foreground">提交结果</h3>
            {result.accepted.length > 0 ? (
              <InlineAlert
                variant="success"
                title="提交成功"
                message={`已成功提交 ${result.accepted.length} 只股票进行分析：${result.accepted.join(', ')}`}
              />
            ) : null}
            {result.duplicates.length > 0 ? (
              <InlineAlert
                variant="warning"
                title="任务已存在"
                message={`以下股票正在分析中：${result.duplicates.join(', ')}`}
              />
            ) : null}
            {result.failed.length > 0 ? (
              <InlineAlert
                variant="warning"
                title="部分未提交"
                message={`以下股票未提交：${result.failed.join(', ')}`}
              />
            ) : null}
            <div className="pt-2">
              <Button variant="outline" size="sm" onClick={() => setResult(null)}>
                继续添加
              </Button>
            </div>
          </div>
        </Card>
      ) : null}

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
            <div className="space-y-3">
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

      {/* 提交按钮 */}
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
    </div>
  );
};

export default BatchAnalysisPage;
