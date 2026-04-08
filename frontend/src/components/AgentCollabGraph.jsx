import React, { useEffect, useMemo, useState } from 'react';
import {
  Activity,
  ArrowRight,
  BrainCircuit,
  Cpu,
  Database,
  ShieldCheck,
  Zap,
} from 'lucide-react';

const avatarIconMap = {
  BrainCircuit,
  Cpu,
  Database,
  ShieldCheck,
  Zap,
};

const statusColorMap = {
  active: 'cyan',
  processing: 'purple',
  idle: 'blue',
  'self-correcting': 'yellow',
  warning: 'yellow',
};

const colorMap = {
  cyan: {
    bg: 'bg-cyan-500/10',
    border: 'border-cyan-500/30',
    text: 'text-cyan-400',
    dot: 'bg-cyan-400',
  },
  blue: {
    bg: 'bg-blue-500/10',
    border: 'border-blue-500/30',
    text: 'text-blue-400',
    dot: 'bg-blue-400',
  },
  purple: {
    bg: 'bg-purple-500/10',
    border: 'border-purple-500/30',
    text: 'text-purple-400',
    dot: 'bg-purple-400',
  },
  yellow: {
    bg: 'bg-yellow-500/10',
    border: 'border-yellow-500/30',
    text: 'text-yellow-400',
    dot: 'bg-yellow-400',
  },
  green: {
    bg: 'bg-green-500/10',
    border: 'border-green-500/30',
    text: 'text-green-400',
    dot: 'bg-green-400',
  },
};

function normalizeAgentName(name) {
  return name.toLowerCase().replace(/[^a-z0-9]+/g, ' ').trim();
}

function resolveNodeId(agentName, nodes) {
  const normalizedName = normalizeAgentName(agentName);
  const directMatch = nodes.find(
    (node) => normalizeAgentName(node.name) === normalizedName,
  );

  if (directMatch) {
    return directMatch.id;
  }

  const partialMatch = nodes.find((node) =>
    normalizeAgentName(node.name).includes(normalizedName) ||
    normalizedName.includes(normalizeAgentName(node.name)),
  );

  return partialMatch?.id ?? null;
}

function buildLiveFlow(data, nodes) {
  if (!data || nodes.length === 0) {
    return [];
  }

  const orchestratorId =
    nodes.find((node) => normalizeAgentName(node.name).includes('orchestrator'))?.id ??
    nodes[0]?.id ??
    null;

  const workflowMessages = (data.workflows ?? [])
    .flatMap((workflow) => {
      const agentSteps = workflow.steps.filter((step) => step.agent !== 'System');

      return agentSteps.map((step, index) => {
        const from = resolveNodeId(step.agent, nodes) ?? orchestratorId;
        const nextAgent = agentSteps[index + 1]?.agent;
        const to = resolveNodeId(nextAgent || workflow.assignedAgent || 'Nexus Orchestrator', nodes)
          ?? orchestratorId;
        const detailSuffix = step.detail ? `: ${step.detail}` : '';

        return {
          from,
          to,
          message: `${workflow.name} - ${step.name}${detailSuffix}`,
        };
      });
    })
    .filter((message) => message.from && message.to)
    .slice(-8);

  const auditMessages = (data.auditLogs ?? [])
    .slice(0, 8)
    .map((log) => {
      const from = resolveNodeId(log.agent, nodes) ?? orchestratorId;
      const to =
        from === orchestratorId
          ? resolveNodeId(
              data.workflows?.find((workflow) => workflow.assignedAgent)?.assignedAgent ||
                nodes.find((node) => node.id !== orchestratorId)?.name ||
                '',
              nodes,
            ) ?? orchestratorId
          : orchestratorId;

      return {
        from,
        to,
        message: log.message,
      };
    })
    .filter((message) => message.from && message.to);

  return [...workflowMessages, ...auditMessages];
}

export function AgentCollabGraph({ data }) {
  const agentNodes = useMemo(
    () =>
      (data?.agents ?? []).map((agent) => ({
        id: agent.id,
        name: agent.name,
        role: agent.role,
        currentTask: agent.currentTask,
        status: agent.status,
        icon: avatarIconMap[agent.avatar] || Cpu,
        color: statusColorMap[agent.status] || 'green',
      })),
    [data],
  );

  const collaborationFlow = useMemo(
    () => buildLiveFlow(data, agentNodes),
    [agentNodes, data],
  );
  const replayKey = useMemo(
    () => collaborationFlow.map((message) => `${message.from}-${message.to}-${message.message}`).join('|'),
    [collaborationFlow],
  );

  return (
    <div>
      <h1 className="text-3xl font-light mb-8 text-white">
        Agent <span className="font-bold text-cyan-400">Collaboration</span>
      </h1>

      <div className="grid grid-cols-2 md:grid-cols-5 gap-4 mb-8">
        {agentNodes.map((node) => {
          const colors = colorMap[node.color];
          const isActive = node.status !== 'idle';

          return (
            <div
              key={node.id}
              className={`glass-panel p-4 rounded-2xl text-center transition-all duration-500 ${
                isActive ? `${colors.border} border shadow-lg` : 'border-transparent'
              }`}
            >
              <div className="relative mx-auto mb-3 h-14 w-14 rounded-full bg-zinc-800 flex items-center justify-center">
                <node.icon
                  className={`h-7 w-7 ${colors.text} transition-all ${isActive ? 'scale-110' : ''}`}
                />
                {isActive && (
                  <div
                    className={`absolute -top-1 -right-1 h-4 w-4 rounded-full ${colors.dot} animate-pulse`}
                  ></div>
                )}
              </div>
              <h4 className="text-xs font-bold text-white truncate">{node.name}</h4>
              <p className="text-[10px] text-zinc-500 mt-0.5">{node.role}</p>
              <p className="text-[10px] text-zinc-600 mt-2 line-clamp-2 min-h-[2rem]">
                {node.currentTask}
              </p>
            </div>
          );
        })}
      </div>

      <div className="glass-panel p-6 rounded-2xl">
        <h2 className="text-lg font-bold text-white mb-4 flex items-center gap-2">
          <Activity className="h-5 w-5 text-cyan-400" /> Inter-Agent Communication
        </h2>
        <CollaborationReplay
          key={replayKey || 'empty'}
          agentNodes={agentNodes}
          collaborationFlow={collaborationFlow}
        />
      </div>
    </div>
  );
}

function CollaborationReplay({ agentNodes, collaborationFlow }) {
  const [activeMessages, setActiveMessages] = useState([]);
  const [currentIdx, setCurrentIdx] = useState(0);

  useEffect(() => {
    if (collaborationFlow.length === 0) {
      return undefined;
    }

    if (currentIdx >= collaborationFlow.length) {
      const resetTimer = setTimeout(() => {
        setActiveMessages([]);
        setCurrentIdx(0);
      }, 2500);
      return () => clearTimeout(resetTimer);
    }

    const timer = setTimeout(() => {
      setActiveMessages((currentMessages) => [
        ...currentMessages.slice(-7),
        collaborationFlow[currentIdx],
      ]);
      setCurrentIdx((current) => current + 1);
    }, currentIdx === 0 ? 900 : 1700);

    return () => clearTimeout(timer);
  }, [collaborationFlow, currentIdx]);

  return (
    <div className="space-y-3 max-h-[400px] overflow-y-auto">
      {activeMessages.map((message, index) => {
        const fromNode = agentNodes.find((node) => node.id === message.from);
        const toNode = agentNodes.find((node) => node.id === message.to);
        const colors = colorMap[fromNode?.color || 'cyan'];

        return (
          <div
            key={`${message.from}-${message.to}-${index}`}
            className={`flex items-start gap-3 p-3 rounded-xl bg-black/40 border border-zinc-800 animate-fade-in ${
              index === activeMessages.length - 1 ? 'ring-1 ring-cyan-500/20' : ''
            }`}
          >
            <div
              className={`h-8 w-8 rounded-full flex items-center justify-center flex-shrink-0 ${colors.bg}`}
            >
              {fromNode && <fromNode.icon className={`h-4 w-4 ${colors.text}`} />}
            </div>
            <div className="flex-1 min-w-0">
              <div className="flex items-center gap-2 mb-1">
                <span className={`text-xs font-bold ${colors.text}`}>{fromNode?.name}</span>
                <ArrowRight className="h-3 w-3 text-zinc-600" />
                <span className="text-xs font-bold text-zinc-400">{toNode?.name}</span>
              </div>
              <p className="text-sm text-zinc-300">{message.message}</p>
            </div>
          </div>
        );
      })}

      {collaborationFlow.length === 0 && (
        <div className="text-center py-8 text-zinc-600">
          <Activity className="h-8 w-8 mx-auto mb-2 opacity-30" />
          <p className="text-sm">No live collaboration events are available yet.</p>
        </div>
      )}

      {collaborationFlow.length > 0 && activeMessages.length === 0 && (
        <div className="text-center py-8 text-zinc-600">
          <Activity className="h-8 w-8 mx-auto mb-2 opacity-30" />
          <p className="text-sm">Initializing live collaboration replay...</p>
        </div>
      )}
    </div>
  );
}
