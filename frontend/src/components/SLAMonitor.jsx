import React, { useEffect, useState } from 'react';
import {
  AlertTriangle,
  ArrowUpRight,
  CheckCircle2,
  Shield,
  TrendingUp,
} from 'lucide-react';
import { fetchSlaOverview } from '../api';

const emptyOverview = {
  summary: {
    onTrack: 0,
    atRisk: 0,
    breached: 0,
    autoResolutions: 0,
  },
  workflows: [],
  bottlenecks: [],
};

export function SLAMonitor({ token }) {
  const [ticks, setTicks] = useState(0);
  const [overview, setOverview] = useState(emptyOverview);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  useEffect(() => {
    const timer = setInterval(() => setTicks((currentTicks) => currentTicks + 1), 1000);
    return () => clearInterval(timer);
  }, []);

  useEffect(() => {
    let cancelled = false;

    const loadOverview = async () => {
      if (!token) {
        setLoading(false);
        return;
      }

      setLoading(true);
      setError('');

      try {
        const response = await fetchSlaOverview(token);
        if (!cancelled) {
          setOverview(response);
        }
      } catch (err) {
        if (!cancelled) {
          setError(err.message || 'Unable to load SLA health data.');
        }
      } finally {
        if (!cancelled) {
          setLoading(false);
        }
      }
    };

    loadOverview();

    return () => {
      cancelled = true;
    };
  }, [token]);

  return (
    <div>
      <h1 className="text-3xl font-light mb-8 text-white">
        SLA Health <span className="font-bold text-cyan-400">Monitor</span>
      </h1>

      {error && (
        <div className="mb-6 rounded-2xl border border-red-500/20 bg-red-500/10 px-4 py-3 text-sm text-red-300">
          {error}
        </div>
      )}

      <div className="grid grid-cols-1 md:grid-cols-4 gap-4 mb-8">
        <div className="glass-panel p-4 rounded-2xl text-center">
          <p className="text-zinc-400 text-xs uppercase tracking-wider mb-1">On Track</p>
          <p className="text-3xl font-bold text-green-400">{overview.summary.onTrack}</p>
        </div>
        <div className="glass-panel p-4 rounded-2xl text-center">
          <p className="text-zinc-400 text-xs uppercase tracking-wider mb-1">At Risk</p>
          <p className="text-3xl font-bold text-yellow-400">{overview.summary.atRisk}</p>
        </div>
        <div className="glass-panel p-4 rounded-2xl text-center">
          <p className="text-zinc-400 text-xs uppercase tracking-wider mb-1">Breached</p>
          <p className="text-3xl font-bold text-red-400">{overview.summary.breached}</p>
        </div>
        <div className="glass-panel p-4 rounded-2xl text-center">
          <p className="text-zinc-400 text-xs uppercase tracking-wider mb-1">Auto-Resolutions</p>
          <p className="text-3xl font-bold text-cyan-400">{overview.summary.autoResolutions}</p>
        </div>
      </div>

      <div className="space-y-4 mb-8">
        {loading && (
          <div className="glass-panel p-5 rounded-2xl text-sm text-zinc-400">
            Loading SLA workflows...
          </div>
        )}

        {!loading &&
          overview.workflows.map((workflow) => {
            const percentElapsed = Math.min((workflow.elapsedHours / workflow.slaHours) * 100, 100);
            const remaining = Math.max(workflow.slaHours - workflow.elapsedHours, 0);
            const hoursRemaining = Math.floor(remaining);
            const minutesRemaining = Math.round((remaining - hoursRemaining) * 60);
            const displayMinutes = Math.max(minutesRemaining - (ticks % 60), 0);

            return (
              <div
                key={workflow.id}
                className={`glass-panel p-5 rounded-2xl border ${
                  workflow.status === 'breached'
                    ? 'border-red-500/30'
                    : workflow.status === 'at-risk'
                      ? 'border-yellow-500/30'
                      : 'border-transparent'
                }`}
              >
                <div className="flex justify-between items-start mb-3 gap-4">
                  <div>
                    <div className="flex items-center gap-2 mb-1">
                      <h3 className="text-white font-medium">{workflow.name}</h3>
                      <span
                        className={`px-2 py-0.5 rounded-full text-[10px] font-bold uppercase ${
                          workflow.status === 'on-track'
                            ? 'bg-green-400/10 text-green-400'
                            : workflow.status === 'at-risk'
                              ? 'bg-yellow-400/10 text-yellow-400'
                              : 'bg-red-400/10 text-red-400'
                        }`}
                      >
                        {workflow.status.replace('-', ' ')}
                      </span>
                    </div>
                    <p className="text-xs text-zinc-500">
                      {workflow.type} • Step: {workflow.currentStep} • Agent:{' '}
                      <span className="text-cyan-300 font-mono">{workflow.agent}</span>
                    </p>
                  </div>
                  <div className="text-right">
                    <div
                      className={`font-mono text-lg font-bold ${
                        workflow.status === 'breached'
                          ? 'text-red-400'
                          : workflow.status === 'at-risk'
                            ? 'text-yellow-400 animate-pulse'
                            : 'text-green-400'
                      }`}
                    >
                      {workflow.status === 'breached'
                        ? 'BREACHED'
                        : `${hoursRemaining}h ${displayMinutes}m`}
                    </div>
                    <p className="text-[10px] text-zinc-600">remaining</p>
                  </div>
                </div>

                <div className="w-full bg-zinc-800 rounded-full h-2 mb-2 overflow-hidden">
                  <div
                    className={`h-2 rounded-full transition-all duration-1000 ${
                      workflow.status === 'breached'
                        ? 'bg-red-500'
                        : workflow.status === 'at-risk'
                          ? 'bg-yellow-500'
                          : 'bg-green-500'
                    }`}
                    style={{ width: `${percentElapsed}%` }}
                  ></div>
                </div>

                <div className="flex justify-between items-center gap-4">
                  <p className="text-xs text-zinc-400 flex items-center gap-1">
                    <TrendingUp className="h-3 w-3" /> {workflow.prediction}
                  </p>
                  {workflow.autoAction && (
                    <p className="text-xs text-cyan-400 flex items-center gap-1 text-right">
                      <ArrowUpRight className="h-3 w-3" /> {workflow.autoAction}
                    </p>
                  )}
                </div>
              </div>
            );
          })}

        {!loading && overview.workflows.length === 0 && (
          <div className="glass-panel p-5 rounded-2xl text-sm text-zinc-400">
            No SLA-tracked workflows are available right now.
          </div>
        )}
      </div>

      <div className="glass-panel p-6 rounded-2xl">
        <h2 className="text-lg font-bold text-white mb-4 flex items-center gap-2">
          <AlertTriangle className="h-5 w-5 text-yellow-400" /> Bottleneck Predictions and
          Auto-Routing
        </h2>
        <div className="space-y-3">
          {overview.bottlenecks.map((bottleneck) => (
            <div
              key={`${bottleneck.area}-${bottleneck.risk}`}
              className="flex items-start gap-4 p-4 bg-black/40 rounded-xl border border-zinc-800"
            >
              <div
                className={`p-2 rounded-lg flex-shrink-0 ${
                  bottleneck.risk === 'high'
                    ? 'bg-red-500/10 text-red-400'
                    : bottleneck.risk === 'medium'
                      ? 'bg-yellow-500/10 text-yellow-400'
                      : 'bg-green-500/10 text-green-400'
                }`}
              >
                <Shield className="h-5 w-5" />
              </div>
              <div className="flex-1">
                <div className="flex items-center gap-2 mb-1">
                  <h4 className="text-sm font-medium text-white">{bottleneck.area}</h4>
                  <span
                    className={`px-2 py-0.5 rounded-full text-[10px] font-bold uppercase ${
                      bottleneck.risk === 'high'
                        ? 'bg-red-400/10 text-red-400'
                        : bottleneck.risk === 'medium'
                          ? 'bg-yellow-400/10 text-yellow-400'
                          : 'bg-green-400/10 text-green-400'
                    }`}
                  >
                    {bottleneck.risk} risk
                  </span>
                </div>
                <p className="text-xs text-zinc-500 mb-1">
                  Avg delay: {bottleneck.avgDelay} • Frequency: {bottleneck.frequency}
                </p>
                <p className="text-xs text-cyan-400 flex items-center gap-1">
                  <CheckCircle2 className="h-3 w-3" /> Agent suggestion: {bottleneck.suggestion}
                </p>
              </div>
            </div>
          ))}

          {!loading && overview.bottlenecks.length === 0 && (
            <div className="rounded-xl border border-zinc-800 bg-black/30 px-4 py-3 text-sm text-zinc-400">
              No active bottleneck predictions were returned by the backend.
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
