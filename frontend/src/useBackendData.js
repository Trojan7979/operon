import { useEffect, useState } from 'react';
import { advanceWorkflow, fetchDashboardOverview } from './api';

const emptyData = {
  systemMetrics: {
    activeWorkflows: 0,
    tasksAutomated: 0,
    humanEscalations: 0,
    selfCorrections: 0,
    uptime: '0%',
    autonomyRate: '0%',
  },
  agents: [],
  workflows: [],
  auditLogs: [],
  connectedTools: [],
};

export function useBackendData(token) {
  const [data, setData] = useState(emptyData);
  const [loading, setLoading] = useState(Boolean(token));
  const [error, setError] = useState('');

  useEffect(() => {
    if (!token) {
      setData(emptyData);
      setLoading(false);
      setError('');
      return;
    }

    let cancelled = false;

    const load = async ({ silent = false } = {}) => {
      if (!silent) {
        setLoading(true);
      }
      try {
        const overview = await fetchDashboardOverview(token);
        if (!cancelled) {
          setData(overview);
          setError('');
        }
      } catch (err) {
        if (!cancelled) {
          setError(err.message || 'Unable to load live system data.');
        }
      } finally {
        if (!cancelled) {
          setLoading(false);
        }
      }
    };

    load();
    const interval = window.setInterval(() => load({ silent: true }), 15000);

    return () => {
      cancelled = true;
      window.clearInterval(interval);
    };
  }, [token]);

  const refresh = async () => {
    if (!token) return;
    setLoading(true);
    try {
      const overview = await fetchDashboardOverview(token);
      setData(overview);
      setError('');
    } catch (err) {
      setError(err.message || 'Unable to refresh live system data.');
    } finally {
      setLoading(false);
    }
  };

  const advanceLiveWorkflow = async (workflowId) => {
    const result = await advanceWorkflow(token, workflowId);
    await refresh();
    return result;
  };

  return {
    data,
    loading,
    error,
    refresh,
    advanceWorkflow: advanceLiveWorkflow,
  };
}
