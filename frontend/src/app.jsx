import React, { useState, useEffect } from 'react';
import { 
  ShieldAlert, 
  CheckCircle2, 
  AlertTriangle, 
  XCircle, 
  Search, 
  RefreshCw, 
  Eye, 
  X, 
  Activity, 
  Filter, 
  Layers, 
  ArrowUpDown, 
  FileText,
  DollarSign
} from 'lucide-react';

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000';

function App() {
  const [metrics, setMetrics] = useState(null);
  const [exceptionsBreakdown, setExceptionsBreakdown] = useState({});
  const [humanReviewQueue, setHumanReviewQueue] = useState([]);
  const [loading, setLoading] = useState(true);
  const [reconciling, setReconciling] = useState(false);
  const [error, setError] = useState(null);
  const [healthStatus, setHealthStatus] = useState('checking');

  // Filter & Search states
  const [searchTerm, setSearchTerm] = useState('');
  const [causeFilter, setCauseFilter] = useState('ALL');
  const [sortBy, setSortBy] = useState('expected_loss_desc');

  // Audit modal state
  const [selectedAuditId, setSelectedAuditId] = useState(null);
  const [auditData, setAuditData] = useState(null);
  const [auditLoading, setAuditLoading] = useState(false);
  const [auditError, setAuditError] = useState(null);

  // Currency Formatter
  const formatINR = (val) => {
    if (val === undefined || val === null) return '₹0.00';
    return new Intl.NumberFormat('en-IN', {
      style: 'currency',
      currency: 'INR',
      maximumFractionDigits: 2
    }).format(val);
  };

  // Check backend health
  const checkHealth = async () => {
    try {
      const res = await fetch(`${API_BASE_URL}/api/health`);
      if (res.ok) {
        setHealthStatus('online');
      } else {
        setHealthStatus('offline');
      }
    } catch {
      setHealthStatus('offline');
    }
  };

  // Fetch metrics & human review queue
  const loadData = async (isReconcileCall = false) => {
    if (isReconcileCall) setReconciling(true);
    else setLoading(true);
    setError(null);

    try {
      const url = `${API_BASE_URL}/api/reconcile`;
      const res = await fetch(url);
      if (!res.ok) {
        throw new Error(`Failed to load data (HTTP ${res.status})`);
      }
      const data = await res.json();
      setMetrics(data.metrics || null);
      setExceptionsBreakdown(data.exceptions_breakdown || {});
      setHumanReviewQueue(data.human_review_queue || []);
      setHealthStatus('online');
    } catch (err) {
      console.error(err);
      setError(err.message || 'Error connecting to backend server');
      setHealthStatus('offline');
    } finally {
      setLoading(false);
      setReconciling(false);
    }
  };

  useEffect(() => {
    checkHealth();
    loadData(false);
  }, []);

  // Fetch Audit details for modal
  const handleOpenAudit = async (gwId) => {
    setSelectedAuditId(gwId);
    setAuditLoading(true);
    setAuditError(null);
    setAuditData(null);

    try {
      const res = await fetch(`${API_BASE_URL}/api/audit/${encodeURIComponent(gwId)}`);
      if (!res.ok) {
        const errJson = await res.json().catch(() => ({}));
        throw new Error(errJson.detail || `Transaction audit not found (HTTP ${res.status})`);
      }
      const data = await res.json();
      setAuditData(data);
    } catch (err) {
      setAuditError(err.message);
    } finally {
      setAuditLoading(false);
    }
  };

  // Filtering & Sorting
  const filteredQueue = humanReviewQueue.filter((item) => {
    const matchesSearch = 
      item.gateway_id.toLowerCase().includes(searchTerm.toLowerCase()) ||
      (item.ledger_id && item.ledger_id.toLowerCase().includes(searchTerm.toLowerCase())) ||
      (item.bank_id && item.bank_id.toLowerCase().includes(searchTerm.toLowerCase()));

    const matchesCause = 
      causeFilter === 'ALL' || 
      (item.root_causes && item.root_causes.includes(causeFilter));

    return matchesSearch && matchesCause;
  }).sort((a, b) => {
    if (sortBy === 'expected_loss_desc') return b.expected_loss - a.expected_loss;
    if (sortBy === 'expected_loss_asc') return a.expected_loss - b.expected_loss;
    if (sortBy === 'confidence_asc') return a.confidence - b.confidence;
    if (sortBy === 'confidence_desc') return b.confidence - a.confidence;
    if (sortBy === 'exposure_desc') return b.exposure - a.exposure;
    return 0;
  });

  return (
    <div className="min-h-screen bg-slate-950 text-slate-100 p-4 md:p-8 font-sans">
      {/* Header Bar */}
      <header className="max-w-7xl mx-auto flex flex-col md:flex-row items-start md:items-center justify-between pb-6 mb-8 border-b border-slate-800 gap-4">
        <div>
          <div className="flex items-center gap-3">
            <div className="p-2.5 bg-indigo-600/20 border border-indigo-500/30 rounded-xl text-indigo-400">
              <Layers className="w-6 h-6" />
            </div>
            <div>
              <h1 className="text-2xl font-bold text-white tracking-tight flex items-center gap-2">
                KuberSetu <span className="text-xs px-2 py-0.5 rounded-full bg-indigo-500/10 text-indigo-400 border border-indigo-500/20 font-medium">SettleSense AI</span>
              </h1>
              <p className="text-xs text-slate-400 mt-0.5">Automated 3-Way Reconciliation & Risk Decision Engine</p>
            </div>
          </div>
        </div>

        <div className="flex items-center gap-3">
          {/* Health status badge */}
          <div className={`flex items-center gap-2 px-3 py-1.5 rounded-lg text-xs font-medium border ${
            healthStatus === 'online'
              ? 'bg-emerald-950/60 border-emerald-800/60 text-emerald-400'
              : 'bg-rose-950/60 border-rose-800/60 text-rose-400'
          }`}>
            <span className={`w-2 h-2 rounded-full ${healthStatus === 'online' ? 'bg-emerald-400 animate-pulse' : 'bg-rose-500'}`} />
            {healthStatus === 'online' ? 'Backend Live' : 'Backend Offline'}
          </div>

          <button
            onClick={() => loadData(true)}
            disabled={reconciling || loading}
            className="flex items-center gap-2 px-4 py-2 bg-indigo-600 hover:bg-indigo-500 disabled:opacity-50 text-white font-medium text-sm rounded-lg transition-colors shadow-lg shadow-indigo-600/20"
          >
            <RefreshCw className={`w-4 h-4 ${reconciling ? 'animate-spin' : ''}`} />
            {reconciling ? 'Running Engine...' : 'Run Reconciliation'}
          </button>
        </div>
      </header>

      {/* Main Container */}
      <main className="max-w-7xl mx-auto space-y-8">
        {/* Error Alert */}
        {error && (
          <div className="p-4 bg-rose-950/50 border border-rose-800/80 rounded-xl text-rose-300 flex items-start gap-3">
            <XCircle className="w-5 h-5 text-rose-400 shrink-0 mt-0.5" />
            <div>
              <h3 className="font-semibold text-sm">Connection Error</h3>
              <p className="text-xs text-rose-400/90 mt-0.5">{error}. Check backend server logs or API endpoint configuration.</p>
            </div>
          </div>
        )}

        {/* Section 1: Summary Cards Row */}
        <div>
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-sm font-semibold uppercase tracking-wider text-slate-400 flex items-center gap-2">
              <Activity className="w-4 h-4 text-indigo-400" /> Executive Metrics Summary
            </h2>
            {metrics && (
              <span className="text-xs text-slate-500">
                Automation Rate: <strong className="text-emerald-400">{(metrics.automation_rate * 100).toFixed(1)}%</strong>
              </span>
            )}
          </div>

          {loading ? (
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-5 gap-4">
              {[...Array(5)].map((_, i) => (
                <div key={i} className="h-28 bg-slate-900/60 border border-slate-800 rounded-xl animate-pulse" />
              ))}
            </div>
          ) : metrics ? (
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-5 gap-4">
              {/* Card 1: Total Processed */}
              <div className="p-5 bg-slate-900/80 border border-slate-800 rounded-xl hover:border-slate-700 transition-colors">
                <div className="flex justify-between items-start">
                  <span className="text-xs font-medium text-slate-400 uppercase tracking-wide">Total Processed</span>
                  <div className="p-1.5 bg-slate-800 text-slate-300 rounded-md">
                    <FileText className="w-4 h-4" />
                  </div>
                </div>
                <div className="mt-3">
                  <div className="text-2xl font-bold text-white">{metrics.total_processed}</div>
                  <p className="text-xs text-slate-500 mt-1">3-Way Gateway Dataset</p>
                </div>
              </div>

              {/* Card 2: Auto-Resolved */}
              <div className="p-5 bg-slate-900/80 border border-slate-800 rounded-xl hover:border-emerald-800/40 transition-colors relative overflow-hidden">
                <div className="absolute top-0 right-0 w-24 h-24 bg-emerald-500/5 rounded-full blur-xl pointer-events-none" />
                <div className="flex justify-between items-start">
                  <span className="text-xs font-medium text-slate-400 uppercase tracking-wide">Auto-Resolved</span>
                  <div className="p-1.5 bg-emerald-950 text-emerald-400 border border-emerald-800/50 rounded-md">
                    <CheckCircle2 className="w-4 h-4" />
                  </div>
                </div>
                <div className="mt-3">
                  <div className="text-2xl font-bold text-emerald-400">{metrics.auto_resolved_count}</div>
                  <p className="text-xs text-slate-400 mt-1 font-mono">{formatINR(metrics.auto_resolved_value)}</p>
                </div>
              </div>

              {/* Card 3: Human Review */}
              <div className="p-5 bg-slate-900/80 border border-slate-800 rounded-xl hover:border-amber-800/40 transition-colors relative overflow-hidden">
                <div className="absolute top-0 right-0 w-24 h-24 bg-amber-500/5 rounded-full blur-xl pointer-events-none" />
                <div className="flex justify-between items-start">
                  <span className="text-xs font-medium text-slate-400 uppercase tracking-wide">Human Review</span>
                  <div className="p-1.5 bg-amber-950 text-amber-400 border border-amber-800/50 rounded-md">
                    <AlertTriangle className="w-4 h-4" />
                  </div>
                </div>
                <div className="mt-3">
                  <div className="text-2xl font-bold text-amber-400">{metrics.human_review_count}</div>
                  <p className="text-xs text-slate-400 mt-1 font-mono">{formatINR(metrics.human_review_value)}</p>
                </div>
              </div>

              {/* Card 4: Unresolved Orphans */}
              <div className="p-5 bg-slate-900/80 border border-slate-800 rounded-xl hover:border-rose-800/40 transition-colors relative overflow-hidden">
                <div className="absolute top-0 right-0 w-24 h-24 bg-rose-500/5 rounded-full blur-xl pointer-events-none" />
                <div className="flex justify-between items-start">
                  <span className="text-xs font-medium text-slate-400 uppercase tracking-wide">Orphans</span>
                  <div className="p-1.5 bg-rose-950 text-rose-400 border border-rose-800/50 rounded-md">
                    <ShieldAlert className="w-4 h-4" />
                  </div>
                </div>
                <div className="mt-3">
                  <div className="text-2xl font-bold text-rose-400">{metrics.orphan_count}</div>
                  <p className="text-xs text-slate-400 mt-1 font-mono">{formatINR(metrics.orphan_value)}</p>
                </div>
              </div>

              {/* Card 5: Automation Rate */}
              <div className="p-5 bg-slate-900/80 border border-slate-800 rounded-xl hover:border-indigo-800/40 transition-colors">
                <div className="flex justify-between items-start">
                  <span className="text-xs font-medium text-slate-400 uppercase tracking-wide">Automation Rate</span>
                  <div className="p-1.5 bg-indigo-950 text-indigo-400 border border-indigo-800/50 rounded-md">
                    <DollarSign className="w-4 h-4" />
                  </div>
                </div>
                <div className="mt-3">
                  <div className="text-2xl font-bold text-indigo-300">
                    {(metrics.automation_rate * 100).toFixed(1)}%
                  </div>
                  <div className="w-full bg-slate-800 h-1.5 rounded-full mt-2 overflow-hidden">
                    <div 
                      className="bg-indigo-500 h-full rounded-full transition-all duration-500" 
                      style={{ width: `${metrics.automation_rate * 100}%` }}
                    />
                  </div>
                </div>
              </div>
            </div>
          ) : null}
        </div>

        {/* Section 2: Filterable Human-Review Queue Table */}
        <div className="bg-slate-900/80 border border-slate-800 rounded-2xl p-5 md:p-6 shadow-xl">
          <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 pb-5 border-b border-slate-800">
            <div>
              <h2 className="text-lg font-bold text-white flex items-center gap-2">
                <ShieldAlert className="w-5 h-5 text-amber-400" /> Human Review Queue
              </h2>
              <p className="text-xs text-slate-400 mt-0.5">Transactions exceeding risk tolerance requiring compliance investigation</p>
            </div>

            {/* Filter controls */}
            <div className="flex flex-wrap items-center gap-3">
              {/* Search */}
              <div className="relative">
                <Search className="w-4 h-4 text-slate-400 absolute left-3 top-1/2 -translate-y-1/2" />
                <input
                  type="text"
                  placeholder="Search Gateway ID..."
                  value={searchTerm}
                  onChange={(e) => setSearchTerm(e.target.value)}
                  className="pl-9 pr-4 py-2 bg-slate-950 border border-slate-800 rounded-xl text-xs text-slate-200 placeholder-slate-500 focus:outline-none focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500 w-48 sm:w-56"
                />
              </div>

              {/* Cause filter */}
              <div className="flex items-center gap-1.5 bg-slate-950 border border-slate-800 px-3 py-1.5 rounded-xl">
                <Filter className="w-3.5 h-3.5 text-slate-400" />
                <select
                  value={causeFilter}
                  onChange={(e) => setCauseFilter(e.target.value)}
                  className="bg-transparent text-xs text-slate-300 focus:outline-none cursor-pointer"
                >
                  <option value="ALL" className="bg-slate-900 text-slate-200">All Causes</option>
                  <option value="REFERENCE_VARIANCE" className="bg-slate-900 text-slate-200">Reference Variance</option>
                  <option value="FEE_VARIANCE" className="bg-slate-900 text-slate-200">Fee Variance</option>
                  <option value="TIMING_DRIFT" className="bg-slate-900 text-slate-200">Timing Drift</option>
                </select>
              </div>

              {/* Sort by */}
              <div className="flex items-center gap-1.5 bg-slate-950 border border-slate-800 px-3 py-1.5 rounded-xl">
                <ArrowUpDown className="w-3.5 h-3.5 text-slate-400" />
                <select
                  value={sortBy}
                  onChange={(e) => setSortBy(e.target.value)}
                  className="bg-transparent text-xs text-slate-300 focus:outline-none cursor-pointer"
                >
                  <option value="expected_loss_desc" className="bg-slate-900 text-slate-200">Loss (High to Low)</option>
                  <option value="expected_loss_asc" className="bg-slate-900 text-slate-200">Loss (Low to High)</option>
                  <option value="confidence_asc" className="bg-slate-900 text-slate-200">Confidence (Low to High)</option>
                  <option value="confidence_desc" className="bg-slate-900 text-slate-200">Confidence (High to Low)</option>
                  <option value="exposure_desc" className="bg-slate-900 text-slate-200">Exposure (High to Low)</option>
                </select>
              </div>
            </div>
          </div>

          {/* Table Container */}
          <div className="overflow-x-auto mt-4">
            {loading ? (
              <div className="py-16 text-center text-slate-500 text-sm">
                <RefreshCw className="w-6 h-6 animate-spin mx-auto mb-2 text-indigo-400" />
                Loading reconciliation queue...
              </div>
            ) : filteredQueue.length === 0 ? (
              <div className="py-16 text-center text-slate-500 text-sm">
                <CheckCircle2 className="w-8 h-8 text-emerald-500/50 mx-auto mb-2" />
                No transactions found matching the selected filter criteria.
              </div>
            ) : (
              <table className="w-full text-left text-xs border-collapse">
                <thead>
                  <tr className="border-b border-slate-800 text-slate-400 font-semibold uppercase tracking-wider">
                    <th className="py-3 px-4">Gateway ID</th>
                    <th className="py-3 px-4">Root Causes</th>
                    <th className="py-3 px-4">Confidence</th>
                    <th className="py-3 px-4 text-right">Exposure</th>
                    <th className="py-3 px-4 text-right">Expected Loss</th>
                    <th className="py-3 px-4 text-center">Action</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-800/60">
                  {filteredQueue.map((item) => (
                    <tr 
                      key={item.gateway_id}
                      className="hover:bg-slate-800/40 transition-colors group cursor-pointer"
                      onClick={() => handleOpenAudit(item.gateway_id)}
                    >
                      {/* Gateway ID */}
                      <td className="py-3.5 px-4 font-mono font-medium text-indigo-300">
                        {item.gateway_id}
                      </td>

                      {/* Root Causes Badges */}
                      <td className="py-3.5 px-4">
                        <div className="flex flex-wrap gap-1.5">
                          {item.root_causes && item.root_causes.map((cause, idx) => (
                            <span
                              key={idx}
                              className={`px-2 py-0.5 rounded text-[10px] font-semibold border ${
                                cause === 'REFERENCE_VARIANCE'
                                  ? 'bg-amber-950/80 text-amber-300 border-amber-800/60'
                                  : cause === 'FEE_VARIANCE'
                                  ? 'bg-purple-950/80 text-purple-300 border-purple-800/60'
                                  : cause === 'TIMING_DRIFT'
                                  ? 'bg-blue-950/80 text-blue-300 border-blue-800/60'
                                  : 'bg-slate-800 text-slate-300 border-slate-700'
                              }`}
                            >
                              {cause}
                            </span>
                          ))}
                        </div>
                      </td>

                      {/* Confidence Score Bar */}
                      <td className="py-3.5 px-4">
                        <div className="flex items-center gap-2">
                          <div className="w-16 bg-slate-800 h-2 rounded-full overflow-hidden">
                            <div
                              className={`h-full rounded-full ${
                                item.confidence >= 0.9
                                  ? 'bg-emerald-400'
                                  : item.confidence >= 0.75
                                  ? 'bg-amber-400'
                                  : 'bg-rose-400'
                              }`}
                              style={{ width: `${item.confidence * 100}%` }}
                            />
                          </div>
                          <span className="font-mono text-slate-300 text-[11px]">
                            {(item.confidence * 100).toFixed(0)}%
                          </span>
                        </div>
                      </td>

                      {/* Exposure */}
                      <td className="py-3.5 px-4 text-right font-mono text-slate-300">
                        {formatINR(item.exposure)}
                      </td>

                      {/* Expected Loss */}
                      <td className="py-3.5 px-4 text-right font-mono font-semibold text-rose-400">
                        {formatINR(item.expected_loss)}
                      </td>

                      {/* Action Button */}
                      <td className="py-3.5 px-4 text-center">
                        <button
                          onClick={(e) => {
                            e.stopPropagation();
                            handleOpenAudit(item.gateway_id);
                          }}
                          className="px-3 py-1 bg-slate-800 hover:bg-indigo-600 hover:text-white text-slate-300 font-medium text-[11px] rounded-lg transition-colors inline-flex items-center gap-1.5"
                        >
                          <Eye className="w-3.5 h-3.5" /> Audit
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>
        </div>
      </main>

      {/* Section 3: Click-Through Decision Trail Detail Modal */}
      {selectedAuditId && (
        <div 
          className="fixed inset-0 z-50 bg-slate-950/80 backdrop-blur-sm flex items-center justify-center p-4"
          onClick={() => setSelectedAuditId(null)}
        >
          <div 
            className="bg-slate-900 border border-slate-800 rounded-2xl w-full max-w-xl shadow-2xl overflow-hidden animate-in fade-in zoom-in-95 duration-200"
            onClick={(e) => e.stopPropagation()}
          >
            {/* Modal Header */}
            <div className="flex items-center justify-between px-6 py-4 border-b border-slate-800 bg-slate-950/50">
              <div className="flex items-center gap-3">
                <div className="p-2 bg-indigo-500/10 border border-indigo-500/20 rounded-lg text-indigo-400">
                  <FileText className="w-5 h-5" />
                </div>
                <div>
                  <h3 className="text-base font-bold text-white flex items-center gap-2">
                    Audit Decision Trail
                  </h3>
                  <p className="text-xs font-mono text-indigo-400 mt-0.5">{selectedAuditId}</p>
                </div>
              </div>

              <button
                onClick={() => setSelectedAuditId(null)}
                className="p-1.5 text-slate-400 hover:text-white bg-slate-800/60 hover:bg-slate-800 rounded-lg transition-colors"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            {/* Modal Body */}
            <div className="p-6 space-y-6 max-h-[80vh] overflow-y-auto">
              {auditLoading ? (
                <div className="py-12 text-center text-slate-400 text-sm">
                  <RefreshCw className="w-6 h-6 animate-spin mx-auto mb-2 text-indigo-400" />
                  Fetching audit decision trail from API...
                </div>
              ) : auditError ? (
                <div className="p-4 bg-rose-950/50 border border-rose-800 rounded-xl text-rose-300 text-xs">
                  <p className="font-semibold">Error Loading Audit</p>
                  <p className="mt-1">{auditError}</p>
                </div>
              ) : auditData ? (
                <>
                  {/* Status & Pass Banner */}
                  <div className="grid grid-cols-2 gap-3 p-4 bg-slate-950/60 border border-slate-800 rounded-xl">
                    <div>
                      <span className="text-[10px] uppercase font-semibold tracking-wider text-slate-500">Matching Pass</span>
                      <div className="text-xs font-semibold text-indigo-300 mt-1 flex items-center gap-1.5">
                        <Layers className="w-3.5 h-3.5" /> {auditData.matched_pass || 'N/A'}
                      </div>
                    </div>
                    <div>
                      <span className="text-[10px] uppercase font-semibold tracking-wider text-slate-500">Status</span>
                      <div className="mt-1">
                        <span className={`px-2 py-0.5 rounded text-xs font-bold ${
                          auditData.status === 'AUTO_RESOLVED'
                            ? 'bg-emerald-950 text-emerald-400 border border-emerald-800'
                            : auditData.status === 'HUMAN_REVIEW'
                            ? 'bg-amber-950 text-amber-400 border border-amber-800'
                            : 'bg-rose-950 text-rose-400 border border-rose-800'
                        }`}>
                          {auditData.status}
                        </span>
                      </div>
                    </div>
                  </div>

                  {/* Decision Grid */}
                  <div className="grid grid-cols-2 sm:grid-cols-3 gap-4">
                    <div className="p-3 bg-slate-950/40 border border-slate-800/80 rounded-xl">
                      <span className="text-[10px] text-slate-400 uppercase font-semibold">Confidence</span>
                      <p className="text-lg font-bold text-white mt-0.5">
                        {auditData.confidence !== undefined ? `${(auditData.confidence * 100).toFixed(0)}%` : 'N/A'}
                      </p>
                    </div>

                    <div className="p-3 bg-slate-950/40 border border-slate-800/80 rounded-xl">
                      <span className="text-[10px] text-slate-400 uppercase font-semibold">Expected Loss</span>
                      <p className="text-lg font-bold text-rose-400 mt-0.5 font-mono">
                        {formatINR(auditData.expected_loss)}
                      </p>
                    </div>

                    <div className="p-3 bg-slate-950/40 border border-slate-800/80 rounded-xl col-span-2 sm:col-span-1">
                      <span className="text-[10px] text-slate-400 uppercase font-semibold">Exposure</span>
                      <p className="text-lg font-bold text-slate-200 mt-0.5 font-mono">
                        {formatINR(auditData.exposure)}
                      </p>
                    </div>
                  </div>

                  {/* Rule & Root Causes */}
                  <div className="space-y-3">
                    <div>
                      <h4 className="text-xs font-semibold text-slate-400 uppercase tracking-wider mb-1.5">Rule Fired</h4>
                      <div className="p-3 bg-slate-950 border border-slate-800 rounded-xl font-mono text-xs text-indigo-300">
                        {auditData.rule_fired || 'N/A'}
                      </div>
                    </div>

                    <div>
                      <h4 className="text-xs font-semibold text-slate-400 uppercase tracking-wider mb-1.5">Root Causes</h4>
                      <div className="flex flex-wrap gap-2">
                        {auditData.root_causes && auditData.root_causes.map((c, i) => (
                          <span key={i} className="px-2.5 py-1 bg-amber-950/60 border border-amber-800/60 text-amber-300 rounded-lg text-xs font-semibold">
                            {c}
                          </span>
                        ))}
                      </div>
                    </div>
                  </div>

                  {/* 3-Way Source IDs */}
                  <div className="p-4 bg-slate-950/80 border border-slate-800 rounded-xl space-y-2">
                    <h4 className="text-xs font-semibold text-slate-400 uppercase tracking-wider mb-2">Cross-System Identity Mapping</h4>
                    <div className="flex justify-between items-center text-xs py-1 border-b border-slate-800/60">
                      <span className="text-slate-400">Gateway ID:</span>
                      <span className="font-mono text-indigo-300">{auditData.gateway_id}</span>
                    </div>
                    <div className="flex justify-between items-center text-xs py-1 border-b border-slate-800/60">
                      <span className="text-slate-400">Ledger ID Match:</span>
                      <span className="font-mono text-slate-300">{auditData.ledger_id || 'None'}</span>
                    </div>
                    <div className="flex justify-between items-center text-xs py-1">
                      <span className="text-slate-400">Bank Settlement Ref:</span>
                      <span className="font-mono text-slate-300">{auditData.bank_id || 'None'}</span>
                    </div>
                  </div>
                </>
              ) : null}
            </div>

            {/* Modal Footer */}
            <div className="px-6 py-3 border-t border-slate-800 bg-slate-950/50 flex justify-end">
              <button
                onClick={() => setSelectedAuditId(null)}
                className="px-4 py-2 bg-slate-800 hover:bg-slate-700 text-slate-200 text-xs font-medium rounded-xl transition-colors"
              >
                Close Audit View
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

export default App;
