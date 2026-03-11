import type React from 'react';
import { useCallback, useEffect, useState } from 'react';
import { Eye, EyeOff, Play, Square, RefreshCw, Trash2, Plus, Bell, CheckCircle2, Clock } from 'lucide-react';
import { priceMonitorApi, type WatchingStock, type PriceAlert, getAlertTypeLabel, getAlertTypeVariant } from '../api/price_monitor';
import { getParsedApiError, type ParsedApiError } from '../api/error';
import { ApiErrorAlert, Card, EmptyState, Badge, StatusDot } from '../components/common';

const DEFAULT_PAGE_SIZE = 20;

const PriceMonitorPage: React.FC = () => {
  // Set page title
  useEffect(() => {
    document.title = '价格盯盘 - DSA';
  }, []);

  // 服务状态
  const [status, setStatus] = useState<{
    running: boolean;
    check_interval_seconds: number;
    watching_count: number;
    triggered_cache_count: number;
  } | null>(null);
  const [error, setError] = useState<ParsedApiError | null>(null);

  // 盯盘列表
  const [watchingList, setWatchingList] = useState<WatchingStock[]>([]);
  const [watchingLoading, setWatchingLoading] = useState(false);

  // 提醒历史
  const [alerts, setAlerts] = useState<PriceAlert[]>([]);
  const [alertsTotal, setAlertsTotal] = useState(0);
  const [alertsPage, setAlertsPage] = useState(1);
  const [alertsLoading, setAlertsLoading] = useState(false);
  const [alertFilter, setAlertFilter] = useState({ code: '', alert_type: '' });

  // 操作状态
  const [actionLoading, setActionLoading] = useState<string | null>(null);
  const [showAddDialog, setShowAddDialog] = useState(false);
  const [deleteConfirm, setDeleteConfirm] = useState<{ id: number; code: string } | null>(null);
  const [deleteAllConfirm, setDeleteAllConfirm] = useState(false);
  const [addForm, setAddForm] = useState({
    code: '',
    name: '',
    sentiment_score: 85,
    ideal_buy: '',
    secondary_buy: '',
    stop_loss: '',
    take_profit: '',
  });

  // 加载服务状态
  const loadStatus = useCallback(async () => {
    try {
      const data = await priceMonitorApi.getStatus();
      setStatus(data);
      setError(null);
    } catch (err) {
      setError(getParsedApiError(err));
    }
  }, []);

  // 加载盯盘列表
  const loadWatchingList = useCallback(async () => {
    setWatchingLoading(true);
    try {
      const data = await priceMonitorApi.getWatchingList();
      setWatchingList(Array.isArray(data) ? data : []);
      setError(null);
    } catch (err) {
      setError(getParsedApiError(err));
      setWatchingList([]);
    } finally {
      setWatchingLoading(false);
    }
  }, []);

  // 加载提醒历史
  const loadAlerts = useCallback(async (page = 1) => {
    setAlertsLoading(true);
    try {
      const data = await priceMonitorApi.getAlerts({
        page,
        page_size: DEFAULT_PAGE_SIZE,
        code: alertFilter.code || undefined,
        alert_type: alertFilter.alert_type || undefined,
      });
      setAlerts(Array.isArray(data.items) ? data.items : []);
      setAlertsTotal(data.total || 0);
      setAlertsPage(page);
      setError(null);
    } catch (err) {
      setError(getParsedApiError(err));
    } finally {
      setAlertsLoading(false);
    }
  }, [alertFilter]);

  // 初始加载
  useEffect(() => {
    void loadStatus();
    void loadWatchingList();
    void loadAlerts();
  }, [loadStatus, loadWatchingList, loadAlerts]);

  // 启动服务
  const handleStart = async () => {
    setActionLoading('start');
    try {
      await priceMonitorApi.start();
      await loadStatus();
    } catch (err) {
      setError(getParsedApiError(err));
    } finally {
      setActionLoading(null);
    }
  };

  // 停止服务
  const handleStop = async () => {
    setActionLoading('stop');
    try {
      await priceMonitorApi.stop();
      await loadStatus();
    } catch (err) {
      setError(getParsedApiError(err));
    } finally {
      setActionLoading(null);
    }
  };

  // 刷新列表
  const handleRefreshList = async () => {
    setActionLoading('refresh');
    try {
      await priceMonitorApi.refreshList();
      await Promise.all([loadStatus(), loadWatchingList()]);
    } catch (err) {
      setError(getParsedApiError(err));
    } finally {
      setActionLoading(null);
    }
  };

  // 删除盯盘股票
  const handleDelete = async () => {
    if (!deleteConfirm) return;
    setActionLoading('delete');
    try {
      await priceMonitorApi.deleteWatchingStock(deleteConfirm.id);
      await Promise.all([loadStatus(), loadWatchingList()]);
      setDeleteConfirm(null);
    } catch (err) {
      setError(getParsedApiError(err));
    } finally {
      setActionLoading(null);
    }
  };

  // 删除所有盯盘股票
  const handleDeleteAll = async () => {
    setActionLoading('deleteAll');
    try {
      await priceMonitorApi.deleteAllWatchingStocks();
      await Promise.all([loadStatus(), loadWatchingList()]);
      setDeleteAllConfirm(false);
    } catch (err) {
      setError(getParsedApiError(err));
    } finally {
      setActionLoading(null);
    }
  };

  // 添加盯盘股票
  const handleAddSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setActionLoading('add');
    try {
      await priceMonitorApi.addWatchingStock({
        code: addForm.code.trim(),
        name: addForm.name.trim() || undefined,
        sentiment_score: addForm.sentiment_score,
        ideal_buy: Number(addForm.ideal_buy),
        secondary_buy: addForm.secondary_buy ? Number(addForm.secondary_buy) : undefined,
        stop_loss: addForm.stop_loss ? Number(addForm.stop_loss) : undefined,
        take_profit: addForm.take_profit ? Number(addForm.take_profit) : undefined,
      });
      setShowAddDialog(false);
      setAddForm({
        code: '',
        name: '',
        sentiment_score: 85,
        ideal_buy: '',
        secondary_buy: '',
        stop_loss: '',
        take_profit: '',
      });
      await Promise.all([loadStatus(), loadWatchingList()]);
    } catch (err) {
      setError(getParsedApiError(err));
    } finally {
      setActionLoading(null);
    }
  };

  const totalAlertPages = Math.max(1, Math.ceil(alertsTotal / DEFAULT_PAGE_SIZE));

  return (
    <div className="price-monitor-page min-h-screen space-y-4 p-4 md:p-6">
      <section className="space-y-3">
        <div className="space-y-2">
          <h1 className="text-xl md:text-2xl font-semibold text-foreground">价格盯盘</h1>
          <p className="text-xs md:text-sm text-secondary">
            监控高分股票，到达理想价格时自动触发 AI 分析
          </p>
        </div>

        {/* 服务控制 */}
        <Card padding="md">
          <div className="flex flex-wrap items-center gap-3">
            <div className="flex items-center gap-2">
              <StatusDot tone={status?.running ? 'success' : 'neutral'} />
              <span className="text-sm text-foreground">
                服务状态: {status?.running ? '运行中' : '已停止'}
              </span>
            </div>
            {status ? (
              <span className="text-xs text-secondary">
                检查间隔: {status.check_interval_seconds}秒 | 盯盘数: {status.watching_count}
              </span>
            ) : null}
            <div className="flex-1" />
            <button
              type="button"
              className="btn-secondary text-sm flex items-center gap-2"
              onClick={() => void loadStatus()}
            >
              <RefreshCw className="h-4 w-4" />
              刷新状态
            </button>
            {status?.running ? (
              <button
                type="button"
                className="btn-secondary text-sm flex items-center gap-2 text-danger"
                onClick={() => void handleStop()}
                disabled={actionLoading === 'stop'}
              >
                <Square className="h-4 w-4" />
                {actionLoading === 'stop' ? '停止中...' : '停止服务'}
              </button>
            ) : (
              <button
                type="button"
                className="btn-primary text-sm flex items-center gap-2"
                onClick={() => void handleStart()}
                disabled={actionLoading === 'start'}
              >
                <Play className="h-4 w-4" />
                {actionLoading === 'start' ? '启动中...' : '启动服务'}
              </button>
            )}
          </div>
        </Card>
      </section>

      {error ? <ApiErrorAlert error={error} onDismiss={() => setError(null)} /> : null}

      {/* 主内容区 */}
      <section className="grid grid-cols-1 xl:grid-cols-3 gap-3">
        {/* 盯盘列表 */}
        <Card className="xl:col-span-2" padding="md">
          <div className="flex items-center justify-between mb-3">
            <h2 className="text-sm font-semibold text-foreground flex items-center gap-2">
              <Eye className="h-4 w-4" />
              盯盘列表
            </h2>
            <div className="flex gap-2">
              {watchingList.length > 0 ? (
                <button
                  type="button"
                  className="btn-secondary text-xs px-3 py-1 flex items-center gap-1 text-danger"
                  onClick={() => setDeleteAllConfirm(true)}
                  disabled={actionLoading === 'deleteAll'}
                >
                  <Trash2 className="h-3 w-3" />
                  清空全部
                </button>
              ) : null}
              <button
                type="button"
                className="btn-secondary text-xs px-3 py-1 flex items-center gap-1"
                onClick={() => void handleRefreshList()}
                disabled={actionLoading === 'refresh' || watchingLoading}
              >
                <RefreshCw className={`h-3 w-3 ${actionLoading === 'refresh' ? 'animate-spin' : ''}`} />
                从分析历史刷新
              </button>
              <button
                type="button"
                className="btn-primary text-xs px-3 py-1 flex items-center gap-1"
                onClick={() => setShowAddDialog(true)}
              >
                <Plus className="h-3 w-3" />
                手动添加
              </button>
            </div>
          </div>

          {watchingLoading ? (
            <div className="flex items-center justify-center py-8">
              <div className="h-6 w-6 animate-spin rounded-full border-2 border-cyan/20 border-t-cyan" />
            </div>
          ) : watchingList.length === 0 ? (
            <EmptyState
              title="暂无盯盘股票"
              description="点击“从分析历史刷新”自动添加高分股票，或手动添加个股到盯盘列表。"
              className="border-none bg-transparent px-4 py-8 shadow-none"
            />
          ) : (
            <div className="space-y-2 max-h-[500px] overflow-auto">
              {watchingList.map((stock) => (
                <div
                  key={stock.id}
                  className="flex items-start justify-between gap-3 rounded-lg border border-white/10 bg-white/[0.02] p-3"
                >
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-2">
                      <span className="font-mono text-sm text-foreground">{stock.code}</span>
                      <span className="text-sm text-secondary">{stock.name || '-'}</span>
                      <Badge variant={stock.sentiment_score >= 90 ? 'success' : stock.sentiment_score >= 85 ? 'info' : 'default'}>
                        {stock.sentiment_score}分
                      </Badge>
                      {stock.triggered ? <Badge variant="warning">已触发</Badge> : null}
                      {!stock.is_active ? (
                        <Badge variant="default">
                          <EyeOff className="h-3 w-3 mr-1" />
                          停用
                        </Badge>
                      ) : null}
                    </div>
                    <div className="mt-2 grid grid-cols-2 md:grid-cols-4 gap-2 text-xs text-secondary">
                      <div>
                        理想买入: <span className="text-foreground">{stock.ideal_buy.toFixed(2)}</span>
                      </div>
                      {stock.secondary_buy ? (
                        <div>
                          次级买入: <span className="text-foreground">{stock.secondary_buy.toFixed(2)}</span>
                        </div>
                      ) : null}
                      {stock.stop_loss ? (
                        <div>
                          止损: <span className="text-danger">{stock.stop_loss.toFixed(2)}</span>
                        </div>
                      ) : null}
                      {stock.take_profit ? (
                        <div>
                          止盈: <span className="text-success">{stock.take_profit.toFixed(2)}</span>
                        </div>
                      ) : null}
                    </div>
                    <div className="mt-1 text-xs text-secondary">
                      分析日期: {stock.analysis_date}
                      {stock.triggered_at ? ` | 触发时间: ${stock.triggered_at}` : ''}
                      {stock.trigger_price ? ` | 触发价: ${stock.trigger_price.toFixed(2)}` : ''}
                    </div>
                  </div>
                  <button
                    type="button"
                    className="btn-secondary !px-2 !py-1 text-xs text-danger"
                    onClick={() => setDeleteConfirm({ id: stock.id, code: stock.code })}
                    disabled={actionLoading === 'delete'}
                  >
                    <Trash2 className="h-3 w-3" />
                  </button>
                </div>
              ))}
            </div>
          )}
        </Card>

        {/* 提醒历史 */}
        <Card padding="md">
          <div className="flex items-center justify-between mb-3">
            <h2 className="text-sm font-semibold text-foreground flex items-center gap-2">
              <Bell className="h-4 w-4" />
              提醒历史
            </h2>
            <button
              type="button"
              className="btn-secondary text-xs px-2 py-1"
              onClick={() => void loadAlerts(1)}
              disabled={alertsLoading}
            >
              <RefreshCw className={`h-3 w-3 ${alertsLoading ? 'animate-spin' : ''}`} />
            </button>
          </div>

          {/* 筛选 */}
          <div className="space-y-2 mb-3">
            <input
              className="input-surface input-focus-glow h-8 w-full rounded-lg border bg-transparent px-3 text-xs transition-all focus:outline-none"
              placeholder="按代码筛选..."
              value={alertFilter.code}
              onChange={(e) => setAlertFilter((prev) => ({ ...prev, code: e.target.value }))}
            />
            <select
              className="input-surface input-focus-glow h-8 w-full rounded-lg border bg-transparent px-3 text-xs transition-all focus:outline-none"
              value={alertFilter.alert_type}
              onChange={(e) => setAlertFilter((prev) => ({ ...prev, alert_type: e.target.value }))}
            >
              <option value="">全部类型</option>
              <option value="ideal_buy">理想买入</option>
              <option value="secondary_buy">次级买入</option>
              <option value="stop_loss">止损</option>
              <option value="take_profit">止盈</option>
            </select>
          </div>

          {alertsLoading ? (
            <div className="flex items-center justify-center py-8">
              <div className="h-6 w-6 animate-spin rounded-full border-2 border-cyan/20 border-t-cyan" />
            </div>
          ) : alerts.length === 0 ? (
            <EmptyState
              title="暂无提醒记录"
              description="价格触发后会在这里显示提醒记录。"
              className="border-none bg-transparent px-3 py-6 shadow-none"
            />
          ) : (
            <div className="space-y-2 max-h-[400px] overflow-auto">
              {alerts.map((alert) => (
                <div
                  key={alert.id}
                  className="rounded-lg border border-white/10 bg-white/[0.02] p-2"
                >
                  <div className="flex items-center justify-between gap-2">
                    <div className="flex items-center gap-2 min-w-0">
                      <span className="font-mono text-xs text-foreground">{alert.code}</span>
                      <Badge variant={getAlertTypeVariant(alert.alert_type)}>
                        {getAlertTypeLabel(alert.alert_type)}
                      </Badge>
                    </div>
                    <div className="flex items-center gap-1 shrink-0">
                      {alert.analysis_triggered ? (
                        <CheckCircle2 className="h-3 w-3 text-success" />
                      ) : null}
                      {alert.notification_sent ? (
                        <Bell className="h-3 w-3 text-info" />
                      ) : null}
                    </div>
                  </div>
                  <div className="mt-1 text-xs text-secondary">
                    目标: {alert.target_price.toFixed(2)} | 触发: {alert.trigger_price.toFixed(2)}
                  </div>
                  <div className="mt-1 text-xs text-secondary flex items-center gap-1">
                    <Clock className="h-3 w-3" />
                    {alert.created_at}
                  </div>
                </div>
              ))}
            </div>
          )}

          {/* 分页 */}
          {alertsTotal > 0 ? (
            <div className="mt-3 flex items-center justify-between text-xs text-secondary">
              <span>第 {alertsPage} / {totalAlertPages} 页</span>
              <div className="flex gap-2">
                <button
                  type="button"
                  className="btn-secondary !px-2 !py-1 text-xs"
                  disabled={alertsPage <= 1 || alertsLoading}
                  onClick={() => void loadAlerts(alertsPage - 1)}
                >
                  上一页
                </button>
                <button
                  type="button"
                  className="btn-secondary !px-2 !py-1 text-xs"
                  disabled={alertsPage >= totalAlertPages || alertsLoading}
                  onClick={() => void loadAlerts(alertsPage + 1)}
                >
                  下一页
                </button>
              </div>
            </div>
          ) : null}
        </Card>
      </section>

      {/* 添加对话框 - 使用简单的 div 替代 ConfirmDialog */}
      {showAddDialog ? (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm transition-all">
          <div
            className="mx-4 w-full max-w-md rounded-xl border border-border/70 bg-elevated p-6 shadow-2xl"
            onClick={(e) => e.stopPropagation()}
          >
            <h3 className="mb-4 text-lg font-medium text-foreground">手动添加盯盘股票</h3>
            <form className="space-y-3" onSubmit={handleAddSubmit}>
              <div>
                <label className="text-xs text-secondary mb-1 block">股票代码 *</label>
                <input
                  className="input-surface input-focus-glow h-9 w-full rounded-lg border bg-transparent px-3 text-sm transition-all focus:outline-none"
                  placeholder="例如 600519"
                  value={addForm.code}
                  onChange={(e) => setAddForm((prev) => ({ ...prev, code: e.target.value }))}
                  required
                />
              </div>
              <div>
                <label className="text-xs text-secondary mb-1 block">名称</label>
                <input
                  className="input-surface input-focus-glow h-9 w-full rounded-lg border bg-transparent px-3 text-sm transition-all focus:outline-none"
                  placeholder="股票名称（可选）"
                  value={addForm.name}
                  onChange={(e) => setAddForm((prev) => ({ ...prev, name: e.target.value }))}
                />
              </div>
              <div className="grid grid-cols-2 gap-2">
                <div>
                  <label className="text-xs text-secondary mb-1 block">评分 *</label>
                  <input
                    type="number"
                    min="0"
                    max="100"
                    className="input-surface input-focus-glow h-9 w-full rounded-lg border bg-transparent px-3 text-sm transition-all focus:outline-none"
                    value={addForm.sentiment_score}
                    onChange={(e) => setAddForm((prev) => ({ ...prev, sentiment_score: Number(e.target.value) }))}
                    required
                  />
                </div>
                <div>
                  <label className="text-xs text-secondary mb-1 block">理想买入价 *</label>
                  <input
                    type="number"
                    min="0"
                    step="0.01"
                    className="input-surface input-focus-glow h-9 w-full rounded-lg border bg-transparent px-3 text-sm transition-all focus:outline-none"
                    placeholder="0.00"
                    value={addForm.ideal_buy}
                    onChange={(e) => setAddForm((prev) => ({ ...prev, ideal_buy: e.target.value }))}
                    required
                  />
                </div>
              </div>
              <div className="grid grid-cols-3 gap-2">
                <div>
                  <label className="text-xs text-secondary mb-1 block">次级买入</label>
                  <input
                    type="number"
                    min="0"
                    step="0.01"
                    className="input-surface input-focus-glow h-9 w-full rounded-lg border bg-transparent px-3 text-sm transition-all focus:outline-none"
                    placeholder="可选"
                    value={addForm.secondary_buy}
                    onChange={(e) => setAddForm((prev) => ({ ...prev, secondary_buy: e.target.value }))}
                  />
                </div>
                <div>
                  <label className="text-xs text-secondary mb-1 block">止损价</label>
                  <input
                    type="number"
                    min="0"
                    step="0.01"
                    className="input-surface input-focus-glow h-9 w-full rounded-lg border bg-transparent px-3 text-sm transition-all focus:outline-none"
                    placeholder="可选"
                    value={addForm.stop_loss}
                    onChange={(e) => setAddForm((prev) => ({ ...prev, stop_loss: e.target.value }))}
                  />
                </div>
                <div>
                  <label className="text-xs text-secondary mb-1 block">止盈价</label>
                  <input
                    type="number"
                    min="0"
                    step="0.01"
                    className="input-surface input-focus-glow h-9 w-full rounded-lg border bg-transparent px-3 text-sm transition-all focus:outline-none"
                    placeholder="可选"
                    value={addForm.take_profit}
                    onChange={(e) => setAddForm((prev) => ({ ...prev, take_profit: e.target.value }))}
                  />
                </div>
              </div>
              <div className="flex gap-2 pt-2">
                <button
                  type="button"
                  className="btn-secondary flex-1 text-sm"
                  onClick={() => setShowAddDialog(false)}
                >
                  取消
                </button>
                <button
                  type="submit"
                  className="btn-primary flex-1 text-sm"
                  disabled={actionLoading === 'add'}
                >
                  {actionLoading === 'add' ? '添加中...' : '添加'}
                </button>
              </div>
            </form>
          </div>
        </div>
      ) : null}

      {/* 删除确认对话框 */}
      {deleteConfirm ? (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm transition-all">
          <div
            className="mx-4 w-full max-w-sm rounded-xl border border-border/70 bg-elevated p-6 shadow-2xl"
            onClick={(e) => e.stopPropagation()}
          >
            <h3 className="mb-2 text-lg font-medium text-foreground">删除盯盘股票</h3>
            <p className="text-sm text-secondary-text mb-6 leading-relaxed">
              确认删除 {deleteConfirm.code} 的盯盘设置吗？
            </p>
            <div className="flex justify-end gap-3">
              <button
                type="button"
                onClick={() => setDeleteConfirm(null)}
                className="rounded-lg border border-border/70 px-4 py-2 text-sm font-medium text-secondary-text transition-colors hover:bg-hover hover:text-foreground"
              >
                取消
              </button>
              <button
                type="button"
                onClick={() => void handleDelete()}
                className="rounded-lg px-4 py-2 text-sm font-medium text-foreground transition-colors bg-red-500/80 hover:bg-red-500 shadow-lg shadow-red-500/20"
                disabled={actionLoading === 'delete'}
              >
                {actionLoading === 'delete' ? '删除中...' : '确认删除'}
              </button>
            </div>
          </div>
        </div>
      ) : null}

      {/* 删除所有确认对话框 */}
      {deleteAllConfirm ? (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm transition-all">
          <div
            className="mx-4 w-full max-w-sm rounded-xl border border-border/70 bg-elevated p-6 shadow-2xl"
            onClick={(e) => e.stopPropagation()}
          >
            <h3 className="mb-2 text-lg font-medium text-foreground">清空全部盯盘股票</h3>
            <p className="text-sm text-secondary-text mb-6 leading-relaxed">
              确认要删除所有 {watchingList.length} 只盯盘股票吗？此操作不可撤销。
            </p>
            <div className="flex justify-end gap-3">
              <button
                type="button"
                onClick={() => setDeleteAllConfirm(false)}
                className="rounded-lg border border-border/70 px-4 py-2 text-sm font-medium text-secondary-text transition-colors hover:bg-hover hover:text-foreground"
              >
                取消
              </button>
              <button
                type="button"
                onClick={() => void handleDeleteAll()}
                className="rounded-lg px-4 py-2 text-sm font-medium text-foreground transition-colors bg-red-500/80 hover:bg-red-500 shadow-lg shadow-red-500/20"
                disabled={actionLoading === 'deleteAll'}
              >
                {actionLoading === 'deleteAll' ? '删除中...' : '确认清空'}
              </button>
            </div>
          </div>
        </div>
      ) : null}
    </div>
  );
};

export default PriceMonitorPage;
