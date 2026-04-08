import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { DecisionPanel } from './DecisionPanel';
import {
  AlertCircle,
  AlertTriangle,
  Check,
  ChevronRight,
  Clock,
  Loader,
  Pause,
  Play,
  RefreshCw,
  ShieldAlert,
} from 'lucide-react';

const DEFAULT_STEP_DURATION = 1800;

function getActionableStep(workflow) {
  if (!workflow) {
    return null;
  }

  return (
    workflow.steps.find((step) => step.status === 'in-progress') ||
    workflow.steps.find((step) => step.status === 'pending') ||
    null
  );
}

function getStepKey(workflowId, stepId) {
  return `${workflowId}:${stepId}`;
}

export function WorkflowSimulator({
  workflows = [],
  onAdvanceWorkflow,
  onRefreshWorkflows,
}) {
  const [selectedWorkflowId, setSelectedWorkflowId] = useState(null);
  const [isRunning, setIsRunning] = useState(false);
  const [selectedStep, setSelectedStep] = useState(null);
  const [chaosMode, setChaosMode] = useState(false);
  const [failureActive, setFailureActive] = useState(false);
  const [recoverySteps, setRecoverySteps] = useState([]);
  const [recoveryIdx, setRecoveryIdx] = useState(-1);
  const [recoveredStepKeys, setRecoveredStepKeys] = useState([]);
  const [lastExecution, setLastExecution] = useState(null);
  const [advancing, setAdvancing] = useState(false);
  const [actionError, setActionError] = useState('');
  const timerRef = useRef(null);

  const selectedWorkflow = useMemo(
    () => workflows.find((workflow) => workflow.id === selectedWorkflowId) ?? null,
    [selectedWorkflowId, workflows],
  );
  const actionableStep = useMemo(
    () => getActionableStep(selectedWorkflow),
    [selectedWorkflow],
  );
  const currentStepIdx = selectedWorkflow
    ? selectedWorkflow.steps.findIndex((step) => step.id === actionableStep?.id)
    : -1;

  const completedSteps = useMemo(() => {
    if (!selectedWorkflow) {
      return [];
    }

    return selectedWorkflow.steps
      .filter((step) => ['completed', 'self-corrected'].includes(step.status))
      .map((step) => ({
        ...step,
        recovered:
          step.status === 'self-corrected' ||
          recoveredStepKeys.includes(getStepKey(selectedWorkflow.id, step.id)),
      }));
  }, [recoveredStepKeys, selectedWorkflow]);

  const progress = selectedWorkflow?.progress ?? 0;
  const isComplete = selectedWorkflow?.status === 'completed' || progress === 100;
  const awaitingHumanIntervention =
    Boolean(selectedWorkflow) &&
    !isComplete &&
    !actionableStep &&
    selectedWorkflow.status !== 'in-progress';

  const clearLocalPlayback = () => {
    setIsRunning(false);
    setFailureActive(false);
    setRecoverySteps([]);
    setRecoveryIdx(-1);
    setSelectedStep(null);
    setLastExecution(null);
    setActionError('');
    if (timerRef.current) {
      clearTimeout(timerRef.current);
    }
  };

  const selectWorkflow = (workflowId) => {
    clearLocalPlayback();
    setSelectedWorkflowId(workflowId);
  };

  const closeWorkflow = () => {
    clearLocalPlayback();
    setSelectedWorkflowId(null);
  };

  const syncWorkflow = async () => {
    if (!onRefreshWorkflows) {
      return;
    }

    clearLocalPlayback();
    await onRefreshWorkflows();
  };

  const advanceCurrentWorkflow = useCallback(async () => {
    if (!selectedWorkflow || !onAdvanceWorkflow) {
      return;
    }

    setAdvancing(true);
    setActionError('');

    try {
      const result = await onAdvanceWorkflow(selectedWorkflow.id);
      setLastExecution(result);
    } catch (err) {
      setIsRunning(false);
      setActionError(err.message || 'Unable to advance this workflow right now.');
    } finally {
      setAdvancing(false);
    }
  }, [onAdvanceWorkflow, selectedWorkflow]);

  useEffect(() => {
    if (!selectedWorkflow || !isRunning || !actionableStep || advancing || failureActive) {
      return undefined;
    }

    const stepKey = getStepKey(selectedWorkflow.id, actionableStep.id);
    const stepDuration = actionableStep.duration ?? DEFAULT_STEP_DURATION;

    if (
      chaosMode &&
      actionableStep.canFail &&
      !recoveredStepKeys.includes(stepKey)
    ) {
      timerRef.current = setTimeout(() => {
        setFailureActive(true);
        setRecoverySteps(actionableStep.failureScenario?.recovery ?? []);
        setRecoveryIdx(0);
      }, Math.max(Math.floor(stepDuration / 2), 700));

      return () => clearTimeout(timerRef.current);
    }

    timerRef.current = setTimeout(() => {
      advanceCurrentWorkflow();
    }, stepDuration);

    return () => clearTimeout(timerRef.current);
  }, [
    actionableStep,
    advancing,
    chaosMode,
    failureActive,
    isRunning,
    advanceCurrentWorkflow,
    recoveredStepKeys,
    selectedWorkflow,
  ]);

  useEffect(() => {
    if (!failureActive || recoveryIdx < 0 || recoveryIdx >= recoverySteps.length) {
      return undefined;
    }

    timerRef.current = setTimeout(() => {
      if (recoveryIdx >= recoverySteps.length - 1) {
        if (selectedWorkflow && actionableStep) {
          const stepKey = getStepKey(selectedWorkflow.id, actionableStep.id);
          setRecoveredStepKeys((currentKeys) =>
            currentKeys.includes(stepKey) ? currentKeys : [...currentKeys, stepKey],
          );
        }
        setFailureActive(false);
        setRecoverySteps([]);
        setRecoveryIdx(-1);
        advanceCurrentWorkflow();
      } else {
        setRecoveryIdx((currentIdx) => currentIdx + 1);
      }
    }, 1400);

    return () => clearTimeout(timerRef.current);
  }, [actionableStep, advanceCurrentWorkflow, failureActive, recoveryIdx, recoverySteps, selectedWorkflow]);

  useEffect(() => {
    if (isComplete || awaitingHumanIntervention) {
      setIsRunning(false);
    }
  }, [awaitingHumanIntervention, isComplete]);

  return (
    <div>
      <div className="flex items-center justify-between mb-8">
        <h1 className="text-3xl font-light text-white">
          Workflow <span className="font-bold text-cyan-400">Simulator</span>
        </h1>
        <button
          onClick={() => setChaosMode((current) => !current)}
          className={`flex items-center gap-2 px-4 py-2 rounded-xl text-sm font-semibold transition-all border ${
            chaosMode
              ? 'bg-red-500/10 text-red-400 border-red-500/30 shadow-[0_0_15px_rgba(239,68,68,0.15)]'
              : 'bg-zinc-800/50 text-zinc-400 border-zinc-700 hover:border-red-500/30 hover:text-red-400'
          }`}
        >
          <ShieldAlert className="h-4 w-4" />
          {chaosMode ? 'Chaos Mode ON' : 'Chaos Mode'}
        </button>
      </div>

      {!selectedWorkflow && (
        <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
          {workflows.map((workflow) => (
            <button
              key={workflow.id}
              onClick={() => selectWorkflow(workflow.id)}
              className="glass-panel p-6 rounded-2xl text-left hover:border-cyan-500/30 transition-all group"
            >
              <div className="flex items-center gap-3 mb-4">
                <div className="p-3 bg-cyan-500/10 rounded-xl text-cyan-400 group-hover:bg-cyan-500/20 transition-colors">
                  <Play className="h-5 w-5" />
                </div>
                <div>
                  <p className="text-[10px] uppercase tracking-[0.2em] text-cyan-400 font-bold mb-1">
                    {workflow.type}
                  </p>
                  <h3 className="text-lg font-bold text-white">{workflow.name}</h3>
                </div>
              </div>
              <p className="text-sm text-zinc-400 mb-4">
                {workflow.prediction || 'Live workflow state from the backend orchestration engine.'}
              </p>
              <div className="flex items-center justify-between gap-3 text-xs text-zinc-500">
                <div className="flex items-center gap-2">
                  <Clock className="h-3 w-3" />
                  <span>{workflow.steps.length} backend steps</span>
                </div>
                <span className="text-zinc-300">{workflow.progress}% complete</span>
              </div>
            </button>
          ))}
        </div>
      )}

      {selectedWorkflow && (
        <div>
          <div className="glass-panel p-6 rounded-2xl mb-6">
            <div className="flex justify-between items-center mb-4 gap-4">
              <div>
                <p className="text-cyan-400 text-xs uppercase tracking-widest font-bold mb-1">
                  {selectedWorkflow.type}
                </p>
                <p className="text-white text-lg font-semibold">{selectedWorkflow.name}</p>
                <p className="text-zinc-400 text-sm mt-1">
                  {selectedWorkflow.prediction || 'Live status streamed from the backend workflow engine.'}
                </p>
              </div>
              <div className="flex gap-2">
                {isRunning ? (
                  <button
                    onClick={() => setIsRunning(false)}
                    className="p-2 bg-zinc-800 rounded-lg text-yellow-400 hover:bg-zinc-700"
                  >
                    <Pause className="h-4 w-4" />
                  </button>
                ) : (
                  <button
                    onClick={() => setIsRunning(true)}
                    disabled={!actionableStep || isComplete || advancing}
                    className="p-2 bg-zinc-800 rounded-lg text-green-400 hover:bg-zinc-700 disabled:opacity-40"
                  >
                    <Play className="h-4 w-4" />
                  </button>
                )}
                <button
                  onClick={advanceCurrentWorkflow}
                  disabled={!actionableStep || isComplete || advancing || failureActive}
                  className="px-3 py-2 bg-zinc-800 rounded-lg text-zinc-200 hover:bg-zinc-700 text-xs disabled:opacity-40"
                >
                  Advance
                </button>
                <button
                  onClick={syncWorkflow}
                  className="p-2 bg-zinc-800 rounded-lg text-zinc-400 hover:bg-zinc-700"
                >
                  <RefreshCw className="h-4 w-4" />
                </button>
                <button
                  onClick={closeWorkflow}
                  className="px-3 py-2 bg-zinc-800 rounded-lg text-zinc-400 hover:bg-zinc-700 text-xs"
                >
                  Back
                </button>
              </div>
            </div>

            <div className="w-full bg-zinc-800 rounded-full h-3 overflow-hidden">
              <div
                className={`h-3 rounded-full transition-all duration-700 ${
                  isComplete
                    ? 'bg-gradient-to-r from-green-500 to-emerald-400'
                    : 'bg-gradient-to-r from-cyan-500 to-purple-500'
                }`}
                style={{ width: `${progress}%` }}
              ></div>
            </div>
            <div className="flex justify-between mt-2 text-xs text-zinc-500">
              <span>
                {completedSteps.length} / {selectedWorkflow.steps.length} steps completed
              </span>
              <span className={isComplete ? 'text-green-400 font-bold' : ''}>
                {isComplete ? 'WORKFLOW COMPLETE' : `${progress}%`}
              </span>
            </div>
          </div>

          {actionError && (
            <div className="mb-6 rounded-2xl border border-red-500/20 bg-red-500/10 px-4 py-3 text-sm text-red-300">
              {actionError}
            </div>
          )}

          {lastExecution && (
            <div className="mb-6 grid grid-cols-1 lg:grid-cols-2 gap-4">
              <div className="glass-panel p-4 rounded-2xl">
                <p className="text-xs text-zinc-500 uppercase tracking-wider mb-2">
                  Last Invoked Tools
                </p>
                <div className="space-y-2">
                  {lastExecution.invokedTools?.length ? (
                    lastExecution.invokedTools.map((tool, index) => (
                      <div
                        key={`${tool.toolName}-${index}`}
                        className="rounded-xl border border-zinc-800 bg-black/30 px-3 py-2 text-sm text-zinc-300"
                      >
                        {tool.toolName} • {tool.action}
                      </div>
                    ))
                  ) : (
                    <p className="text-sm text-zinc-500">No external tool invocation was reported.</p>
                  )}
                </div>
              </div>
              <div className="glass-panel p-4 rounded-2xl">
                <p className="text-xs text-zinc-500 uppercase tracking-wider mb-2">
                  Latest Audit Logs
                </p>
                <div className="space-y-2">
                  {lastExecution.newLogs?.length ? (
                    lastExecution.newLogs.map((log) => (
                      <div
                        key={log.id}
                        className="rounded-xl border border-zinc-800 bg-black/30 px-3 py-2"
                      >
                        <p className="text-[10px] uppercase tracking-wider text-cyan-400 mb-1">
                          {log.agent}
                        </p>
                        <p className="text-sm text-zinc-300">{log.message}</p>
                      </div>
                    ))
                  ) : (
                    <p className="text-sm text-zinc-500">No new audit entries came back for that step.</p>
                  )}
                </div>
              </div>
            </div>
          )}

          {awaitingHumanIntervention && (
            <div className="mb-6 rounded-2xl border border-yellow-500/20 bg-yellow-500/10 px-4 py-3 text-sm text-yellow-200">
              This workflow is currently waiting on human intervention or an external unblock. The
              backend does not have an executable step to advance right now.
            </div>
          )}

          <div className="relative pl-8 space-y-4">
            <div className="timeline-stem"></div>
            {selectedWorkflow.steps.map((step, index) => {
              const stepKey = getStepKey(selectedWorkflow.id, step.id);
              const isRecovered = recoveredStepKeys.includes(stepKey) || step.status === 'self-corrected';
              const isCompleted = ['completed', 'self-corrected'].includes(step.status);
              const isCurrent = index === currentStepIdx;
              const isRecovering = isCurrent && failureActive;
              const isEscalated = step.status === 'escalated';

              return (
                <div
                  key={step.id}
                  className={`relative z-10 flex gap-4 transition-all duration-300 ${
                    index > currentStepIdx && !isCompleted && !isEscalated ? 'opacity-30' : 'opacity-100'
                  }`}
                >
                  <div
                    className={`mt-1 h-8 w-8 rounded-full flex items-center justify-center border-2 bg-black flex-shrink-0 ${
                      isRecovering
                        ? 'border-red-500 text-red-500 animate-pulse'
                        : isRecovered
                          ? 'border-yellow-500 text-yellow-500'
                          : isCompleted
                            ? 'border-cyan-500 text-cyan-500'
                            : isEscalated
                              ? 'border-red-400 text-red-400'
                              : isCurrent
                                ? 'border-cyan-400 text-cyan-400'
                                : 'border-zinc-700 text-zinc-700'
                    }`}
                  >
                    {isRecovering ? (
                      <AlertTriangle className="h-4 w-4" />
                    ) : isRecovered ? (
                      <RefreshCw className="h-4 w-4" />
                    ) : isCompleted ? (
                      <Check className="h-4 w-4" />
                    ) : isEscalated ? (
                      <AlertCircle className="h-4 w-4" />
                    ) : isCurrent && (isRunning || advancing) ? (
                      <Loader className="h-4 w-4 animate-spin" />
                    ) : (
                      <span className="h-2 w-2 rounded-full bg-zinc-700"></span>
                    )}
                  </div>

                  <div
                    className={`flex-1 p-4 rounded-xl border cursor-pointer transition-all ${
                      isRecovering
                        ? 'bg-red-950/30 border-red-500/30'
                        : isCurrent
                          ? 'bg-cyan-950/20 border-cyan-500/30'
                          : isEscalated
                            ? 'bg-red-950/10 border-red-500/20'
                            : isCompleted
                              ? 'bg-zinc-900/50 border-zinc-800 hover:border-zinc-600'
                              : 'bg-zinc-900/20 border-zinc-800/50'
                    }`}
                    onClick={() => (isCompleted || isEscalated ? setSelectedStep(step) : null)}
                  >
                    <div className="flex justify-between items-start mb-1 gap-4">
                      <h4 className="text-sm font-medium text-white">{step.name}</h4>
                      <span className="text-xs font-mono text-cyan-300">{step.agent}</span>
                    </div>

                    {step.detail && <p className="text-xs text-zinc-400 mt-2">{step.detail}</p>}

                    {isCurrent && !isRecovering && (
                      <p className="text-xs text-cyan-400 mt-2 flex items-center gap-1">
                        <Loader className="h-3 w-3 animate-spin" /> Processing live backend step...
                      </p>
                    )}

                    {(isCompleted || isEscalated) && !isRecovering && (
                      <p className="text-xs text-zinc-500 mt-2 flex items-center gap-1">
                        <ChevronRight className="h-3 w-3" /> Click for decision reasoning
                      </p>
                    )}

                    {isRecovering && (
                      <div className="mt-3 space-y-2">
                        <div className="bg-red-500/10 border border-red-500/20 p-3 rounded-lg">
                          <p className="text-red-400 text-xs font-bold flex items-center gap-1 mb-1">
                            <AlertTriangle className="h-3 w-3" /> FAILURE DETECTED
                          </p>
                          <p className="text-red-200 text-xs">
                            {step.failureScenario?.detection || 'A recoverable failure was injected for this step.'}
                          </p>
                        </div>

                        <div className="bg-yellow-500/5 border border-yellow-500/20 p-3 rounded-lg">
                          <p className="text-yellow-400 text-xs font-bold mb-2 flex items-center gap-1">
                            <RefreshCw className="h-3 w-3" /> SELF-CORRECTION IN PROGRESS
                          </p>
                          {recoverySteps.map((recoveryStep, recoveryStepIndex) => (
                            <div
                              key={`${recoveryStep.agent}-${recoveryStepIndex}`}
                              className={`flex items-start gap-2 text-xs py-1 transition-all duration-500 ${
                                recoveryStepIndex <= recoveryIdx ? 'opacity-100' : 'opacity-20'
                              }`}
                            >
                              <span
                                className={`mt-0.5 h-4 w-4 rounded-full flex items-center justify-center border flex-shrink-0 ${
                                  recoveryStepIndex < recoveryIdx
                                    ? 'border-green-500 text-green-500'
                                    : recoveryStepIndex === recoveryIdx
                                      ? 'border-yellow-400 text-yellow-400'
                                      : 'border-zinc-700 text-zinc-700'
                                }`}
                              >
                                {recoveryStepIndex < recoveryIdx ? (
                                  <Check className="h-2.5 w-2.5" />
                                ) : recoveryStepIndex === recoveryIdx ? (
                                  <Loader className="h-2.5 w-2.5 animate-spin" />
                                ) : (
                                  <span className="h-1 w-1 rounded-full bg-zinc-700"></span>
                                )}
                              </span>
                              <div>
                                <span className="text-zinc-300">{recoveryStep.action}</span>
                                <span className="text-cyan-500 font-mono ml-2">
                                  - {recoveryStep.agent}
                                </span>
                              </div>
                            </div>
                          ))}
                        </div>
                      </div>
                    )}
                  </div>
                </div>
              );
            })}
          </div>

          {isComplete && (
            <div className="mt-8 glass-panel p-6 rounded-2xl border-green-500/20 bg-green-950/10 text-center animate-fade-in">
              <div className="text-green-400 text-4xl mb-2">✓</div>
              <h3 className="text-xl font-bold text-white mb-1">
                Workflow Completed Through the Backend Engine
              </h3>
              <p className="text-zinc-400 text-sm">
                {completedSteps.length} steps executed |{' '}
                {completedSteps.filter((step) => step.recovered).length} self-corrections surfaced |
                0 local mock transitions used
              </p>
            </div>
          )}
        </div>
      )}

      {selectedStep && <DecisionPanel step={selectedStep} onClose={() => setSelectedStep(null)} />}
    </div>
  );
}
