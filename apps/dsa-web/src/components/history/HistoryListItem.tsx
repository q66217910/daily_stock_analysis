import type React from 'react';
import { useState } from 'react';
import { Badge, Button } from '../common';
import type { HistoryItem } from '../../types/analysis';
import { getSentimentColor } from '../../types/analysis';
import { formatDateTime } from '../../utils/format';
import { truncateStockName, isStockNameTruncated } from '../../utils/stockName';
import { priceMonitorApi } from '../../api/price_monitor';
import { Eye } from 'lucide-react';

interface HistoryListItemProps {
  item: HistoryItem;
  isViewing: boolean; // Indicates if this report is currently being viewed in the right panel
  isChecked: boolean; // Indicates if the checkbox is checked for bulk operations
  isDeleting: boolean;
  onToggleChecked: (recordId: number) => void;
  onClick: (recordId: number) => void;
  onAddToWatchSuccess?: () => void;
}

const getOperationBadgeLabel = (advice?: string) => {
  const normalized = advice?.trim();
  if (!normalized) {
    return '情绪';
  }
  if (normalized.includes('减仓')) {
    return '减仓';
  }
  if (normalized.includes('卖')) {
    return '卖出';
  }
  if (normalized.includes('观望') || normalized.includes('等待')) {
    return '观望';
  }
  if (normalized.includes('买') || normalized.includes('布局')) {
    return '买入';
  }
  return normalized.split(/[，。；、\s]/)[0] || '建议';
};

export const HistoryListItem: React.FC<HistoryListItemProps> = ({
  item,
  isViewing,
  isChecked,
  isDeleting,
  onToggleChecked,
  onClick,
  onAddToWatchSuccess,
}) => {
  const sentimentColor = item.sentimentScore !== undefined ? getSentimentColor(item.sentimentScore) : null;
  const stockName = item.stockName || item.stockCode;
  const isTruncated = isStockNameTruncated(stockName);
  const [isAddingToWatch, setIsAddingToWatch] = useState(false);
  const [addToWatchSuccess, setAddToWatchSuccess] = useState(false);

  // 解析价格字符串（处理 "123.45" 或 "¥123.45" 或 "123.45元" 等格式
  const parsePrice = (priceStr?: string): number | undefined => {
    if (!priceStr) return undefined;
    const match = priceStr.match(/[\d.]+/);
    if (!match) return undefined;
    const num = parseFloat(match[0]);
    return isNaN(num) ? undefined : num;
  };

  const handleAddToWatch = async (e: React.MouseEvent) => {
    e.stopPropagation();
    if (isAddingToWatch) return;

    const idealBuy = parsePrice(item.idealBuy);
    if (!idealBuy || item.sentimentScore === undefined) {
      return;
    }

    setIsAddingToWatch(true);
    try {
      await priceMonitorApi.addWatchingStock({
        code: item.stockCode,
        name: item.stockName,
        sentiment_score: item.sentimentScore,
        ideal_buy: idealBuy,
        secondary_buy: parsePrice(item.secondaryBuy),
        stop_loss: parsePrice(item.stopLoss),
        take_profit: parsePrice(item.takeProfit),
        analysis_history_id: item.id,
      });
      setAddToWatchSuccess(true);
      setTimeout(() => setAddToWatchSuccess(false), 2000);
      onAddToWatchSuccess?.();
    } catch (error) {
      console.error('Failed to add to watch list:', error);
    } finally {
      setIsAddingToWatch(false);
    }
  };

  // 检查是否可以加入盯盘（需要有理想买入价和评分）
  const canAddToWatch = item.sentimentScore !== undefined && parsePrice(item.idealBuy) !== undefined;

  return (
    <div className="flex items-start gap-2 group">
      <div className="pt-5">
        <input
          type="checkbox"
          checked={isChecked}
          onChange={() => onToggleChecked(item.id)}
          disabled={isDeleting}
          className="h-3.5 w-3.5 cursor-pointer rounded border-subtle-hover bg-transparent accent-primary focus:ring-primary/30 disabled:opacity-50"
        />
      </div>
      <button
        type="button"
        onClick={() => onClick(item.id)}
        className={`home-history-item flex-1 text-left p-2.5 group/item ${
          isViewing ? 'home-history-item-selected' : ''
        }`}
      >
        <div className={`flex items-center gap-2.5 relative z-10${isTruncated ? ' group-hover/item:z-20' : ''}`}>
          {sentimentColor && (
            <div
              className="w-1 h-8 rounded-full flex-shrink-0"
              style={{
                backgroundColor: sentimentColor,
                boxShadow: `0 0 10px ${sentimentColor}40`,
              }}
            />
          )}
          <div className="flex-1 min-w-0">
            <div className="flex items-start justify-between gap-2">
              <div className="min-w-0 flex-1">
                <span className="truncate text-sm font-semibold text-foreground tracking-tight">
                  <span className="group-hover/item:hidden">
                    {truncateStockName(stockName)}
                  </span>
                  <span className="hidden group-hover/item:inline">
                    {stockName}
                  </span>
                </span>
              </div>
              {sentimentColor && (
                <Badge
                  variant="default"
                  size="sm"
                  className={`home-history-sentiment-badge shrink-0 shadow-none text-[11px] font-semibold leading-none transition-opacity duration-200${isTruncated ? ' group-hover/item:opacity-80' : ''}`}
                  style={{
                    color: sentimentColor,
                    borderColor: `${sentimentColor}30`,
                    backgroundColor: `${sentimentColor}10`,
                  }}
                >
                  {getOperationBadgeLabel(item.operationAdvice)} {item.sentimentScore}
                </Badge>
              )}
            </div>
            <div className="flex items-center gap-2 mt-1">
              <span className="text-[11px] text-secondary-text font-mono">
                {item.stockCode}
              </span>
              <span className="w-1 h-1 rounded-full bg-subtle-hover" />
              <span className="text-[11px] text-muted-text">
                {formatDateTime(item.createdAt)}
              </span>
            </div>
          </div>
        </div>
      </button>
      {/* 加入盯盘按钮 */}
      <div className="pt-4 pr-1 opacity-0 group-hover:opacity-100 transition-opacity duration-200">
        {canAddToWatch ? (
          <Button
            variant="ghost"
            size="xsm"
            onClick={handleAddToWatch}
            isLoading={isAddingToWatch}
            disabled={isDeleting}
            className="!px-2 !py-1 text-xs"
            title="加入盯盘"
          >
            {addToWatchSuccess ? (
              <svg className="h-3.5 w-3.5 text-success" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
              </svg>
            ) : (
              <Eye className="h-3.5 w-3.5" />
            )}
          </Button>
        ) : null}
      </div>
    </div>
  );
};
