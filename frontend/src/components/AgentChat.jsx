import React, { useEffect, useRef, useState } from 'react';
import {
  Send, User, Cpu, BrainCircuit, Database,
  Zap, ShieldCheck, Loader, Sparkles, Network, ArrowRightLeft
} from 'lucide-react';
import { getApiBase, sendAgentMessage, subscribeApiTrace } from '../api';

const agents = [
  { id: 'orchestrator', name: 'Nexus Orchestrator', icon: Cpu, color: 'cyan', desc: 'Manages workflows and routing' },
  { id: 'intel', name: 'MeetIntel Core', icon: BrainCircuit, color: 'purple', desc: 'Analyzes meetings and documents' },
  { id: 'retrieval', name: 'Data Fetcher v4', icon: Database, color: 'blue', desc: 'Retrieves data and context' },
  { id: 'executor', name: 'Action Exec Alpha', icon: Zap, color: 'yellow', desc: 'Executes tasks and actions' },
  { id: 'verifier', name: 'Shield Verifier', icon: ShieldCheck, color: 'green', desc: 'Validates and audits' },
];

const colorClasses = {
  cyan: { bg: 'bg-cyan-500/10', text: 'text-cyan-400', border: 'border-cyan-500/30', ring: 'ring-cyan-500/20' },
  purple: { bg: 'bg-purple-500/10', text: 'text-purple-400', border: 'border-purple-500/30', ring: 'ring-purple-500/20' },
  blue: { bg: 'bg-blue-500/10', text: 'text-blue-400', border: 'border-blue-500/30', ring: 'ring-blue-500/20' },
  yellow: { bg: 'bg-yellow-500/10', text: 'text-yellow-400', border: 'border-yellow-500/30', ring: 'ring-yellow-500/20' },
  green: { bg: 'bg-green-500/10', text: 'text-green-400', border: 'border-green-500/30', ring: 'ring-green-500/20' },
};

const starterMessages = {
  orchestrator: "Hello! I'm the **Nexus Orchestrator**. I coordinate workflows, approvals, tool routing, and guided onboarding. What should we work on?",
  intel: "MeetIntel Core is online. Share a meeting, transcript, or summary request and I'll process it.",
  retrieval: "Data Fetcher v4 is ready. Ask me to find vendors, employees, tasks, or operational context.",
  executor: "Action Exec Alpha is online. I can help push actions through the workflow system.",
  verifier: "Shield Verifier is online. Ask me to validate risk, compliance, or audit-related concerns.",
};

function RouteActionCard({ action, onContinue }) {
  const [showTrace, setShowTrace] = useState(false);
  const captured = Object.entries(action.prefill ?? {})
    .filter(([, value]) => value)
    .filter(([key]) => !['phone', 'location'].includes(key));

  return (
    <div className="mt-3 rounded-xl border border-cyan-500/20 bg-cyan-500/10 px-3 py-3">
      <p className="text-[10px] font-semibold uppercase tracking-wider text-cyan-300">
        Specialist Handoff
      </p>
      <p className="mt-1 text-xs text-zinc-300">
        Nexus Orchestrator routed this goal to the Onboarding Agent workspace.
      </p>
      {captured.length > 0 && (
        <div className="mt-2 flex flex-wrap gap-2">
          {captured.map(([key, value]) => (
            <span
              key={key}
              className="rounded-full border border-cyan-500/20 bg-black/30 px-2 py-1 text-[10px] text-cyan-200"
            >
              {key}: {value}
            </span>
          ))}
        </div>
      )}
      <div className="mt-3 flex flex-wrap gap-2">
        <button
          onClick={() => onContinue?.(action)}
          className="rounded-lg bg-cyan-500 px-3 py-2 text-xs font-semibold text-zinc-950 transition-colors hover:bg-cyan-400"
        >
          {action.ctaLabel ?? 'Continue'}
        </button>
        {action.trace?.length > 0 && (
          <button
            onClick={() => setShowTrace((value) => !value)}
            className="rounded-lg border border-zinc-700 px-3 py-2 text-xs text-zinc-300 transition-colors hover:border-cyan-500/40 hover:text-white"
          >
            {showTrace ? 'Hide Execution Trace' : 'Show Execution Trace'}
          </button>
        )}
      </div>
      {showTrace && action.trace?.length > 0 && (
        <div className="mt-3 space-y-2 rounded-xl border border-zinc-800 bg-black/30 px-3 py-3">
          {action.trace.map((step, index) => (
            <p key={`${step}-${index}`} className="text-xs text-zinc-400">
              {index + 1}. {step}
            </p>
          ))}
        </div>
      )}
    </div>
  );
}

export function AgentChat({ token, onRouteIntent }) {
  const [selectedAgent, setSelectedAgent] = useState(agents[0]);
  const [messages, setMessages] = useState([
    { sender: 'agent', text: starterMessages.orchestrator, agentId: 'orchestrator' }
  ]);
  const [input, setInput] = useState('');
  const [isTyping, setIsTyping] = useState(false);
  const [error, setError] = useState('');
  const [conversationId, setConversationId] = useState(null);
  const [apiCalls, setApiCalls] = useState([]);
  const messagesEndRef = useRef(null);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, isTyping]);

  useEffect(() => {
    return subscribeApiTrace((entries) => {
      setApiCalls(entries);
    });
  }, []);

  const switchAgent = (agent) => {
    setSelectedAgent(agent);
    setError('');
    setConversationId(null);
    setMessages([
      {
        sender: 'agent',
        text: starterMessages[agent.id] ?? `Switched to **${agent.name}**. ${agent.desc}.`,
        agentId: agent.id,
      },
    ]);
  };

  const sendMessage = async () => {
    if (!input.trim()) return;
    const userMsg = input.trim();
    setMessages(prev => [...prev, { sender: 'user', text: userMsg }]);
    setInput('');
    setError('');
    setIsTyping(true);

    try {
      const response = await sendAgentMessage(token, selectedAgent.id, userMsg, conversationId);
      setConversationId(response.conversationId ?? null);
      setMessages(prev => [
        ...prev,
        {
          sender: 'agent',
          text: response.message,
          agentId: selectedAgent.id,
          invokedTools: response.invokedTools ?? [],
          collaboration: response.collaboration ?? [],
          workflowId: response.workflowId ?? null,
          conversationId: response.conversationId ?? null,
          routeAction: response.routeAction ?? null,
        }
      ]);
    } catch (err) {
      setError(err.message || 'Unable to reach the agent right now.');
    } finally {
      setIsTyping(false);
    }
  };

  const c = colorClasses[selectedAgent.color];
  const AgentIcon = selectedAgent.icon;
  const chatApiCalls = apiCalls.filter(call => call.path.startsWith('/chat'));

  const renderAgentLabel = (agentId) => {
    if (agentId === 'workspace:onboarding') {
      return 'Onboarding Agent Workspace';
    }
    const knownAgent = agents.find((agent) => agent.id === agentId || `ag-${agent.id}` === agentId);
    return knownAgent?.name || agentId || 'Unknown agent';
  };

  const renderText = (text) => {
    return text.split('\n').map((line, i) => {
      const processed = line.replace(/\*\*(.*?)\*\*/g, '<strong class="text-white">$1</strong>');
      if (line.startsWith('•')) {
        return <li key={i} className="ml-4 list-disc" dangerouslySetInnerHTML={{ __html: processed }} />;
      }
      return <p key={i} className={line === '' ? 'h-2' : ''} dangerouslySetInnerHTML={{ __html: processed }} />;
    });
  };

  return (
    <div className="h-[calc(100vh-5rem)] flex flex-col">
      <div className="flex items-center justify-between mb-6">
        <h1 className="text-3xl font-light text-white">Agent <span className="font-bold text-cyan-400">Chat</span></h1>
      </div>

      <div className="flex-1 flex gap-6 min-h-0">
        <div className="w-64 flex-shrink-0 space-y-2">
          <p className="text-xs text-zinc-500 uppercase tracking-wider font-semibold mb-3 px-1">Select Agent</p>
          {agents.map(agent => {
            const ac = colorClasses[agent.color];
            const isActive = selectedAgent.id === agent.id;
            return (
              <button
                key={agent.id}
                onClick={() => switchAgent(agent)}
                className={`w-full p-3 rounded-xl flex items-center gap-3 transition-all text-left ${
                  isActive ? `${ac.bg} ${ac.border} border ${ac.ring} ring-2` : 'glass-panel hover:border-zinc-600'
                }`}
              >
                <div className={`h-9 w-9 rounded-lg flex items-center justify-center ${ac.bg}`}>
                  <agent.icon className={`h-5 w-5 ${ac.text}`} />
                </div>
                <div>
                  <h4 className={`text-sm font-medium ${isActive ? ac.text : 'text-zinc-300'}`}>{agent.name}</h4>
                  <p className="text-[10px] text-zinc-500">{agent.desc}</p>
                </div>
              </button>
            );
          })}

          <div className="mt-6 pt-4 border-t border-zinc-800">
            <p className="text-xs text-zinc-500 uppercase tracking-wider font-semibold mb-3 px-1">Quick Prompts</p>
            {[
              'Check system status',
              'Start a new workflow',
              'Onboard a new employee',
              'Find vendor info',
              'Run compliance check',
              'Summarize meetings'
            ].map((prompt, i) => (
              <button
                key={i}
                onClick={() => setInput(prompt)}
                className="w-full text-left px-3 py-2 text-xs text-zinc-400 hover:text-cyan-400 hover:bg-zinc-800/50 rounded-lg transition-colors"
              >
                <Sparkles className="h-3 w-3 inline mr-2 opacity-50" />{prompt}
              </button>
            ))}
          </div>
        </div>

        <div className="flex-1 flex gap-6 min-h-0">
        <div className="flex-1 glass-panel rounded-2xl flex flex-col overflow-hidden">
          <div className={`p-4 border-b border-zinc-800 flex items-center gap-3 ${c.bg}`}>
            <div className={`h-8 w-8 rounded-lg flex items-center justify-center ${c.bg} border ${c.border}`}>
              <AgentIcon className={`h-4 w-4 ${c.text}`} />
            </div>
            <div>
              <h3 className="text-sm font-bold text-white">{selectedAgent.name}</h3>
              <p className="text-[10px] text-green-400 flex items-center gap-1">
                <span className="h-1.5 w-1.5 rounded-full bg-green-400"></span> Online
              </p>
            </div>
            <div className="ml-auto text-right">
              <p className="text-[10px] uppercase tracking-wider text-zinc-500">Conversation</p>
              <p className="text-xs font-mono text-cyan-300">{conversationId ?? 'Not started'}</p>
            </div>
          </div>

          <div className="flex-1 overflow-y-auto p-6 space-y-4">
            {messages.map((msg, idx) => (
              <div key={idx} className={`flex ${msg.sender === 'user' ? 'justify-end' : 'justify-start'} animate-fade-in`}>
                {msg.sender === 'agent' && (
                  <div className={`h-7 w-7 rounded-lg flex items-center justify-center mr-2 mt-1 flex-shrink-0 ${c.bg}`}>
                    <AgentIcon className={`h-3.5 w-3.5 ${c.text}`} />
                  </div>
                )}
                <div className={`max-w-[75%] px-4 py-3 rounded-2xl text-sm leading-relaxed ${
                  msg.sender === 'user'
                    ? 'bg-cyan-600/20 text-cyan-100 rounded-br-none border border-cyan-500/20'
                    : 'bg-zinc-800/80 text-zinc-300 rounded-bl-none border border-zinc-700'
                }`}>
                  {renderText(msg.text)}
                  {msg.sender === 'agent' && msg.collaboration?.length > 0 && (
                    <div className="mt-3 space-y-2">
                      <p className="text-[10px] uppercase tracking-wider text-zinc-500 font-semibold">
                        Agent Collaboration
                      </p>
                      {msg.collaboration.map((entry, idx2) => (
                        <div
                          key={`${entry.handoffId ?? idx2}`}
                          className="rounded-xl border border-purple-500/10 bg-black/30 px-3 py-2"
                        >
                          <div className="flex items-center gap-2 text-xs text-purple-300 font-semibold">
                            <ArrowRightLeft className="h-3 w-3" />
                            <span>
                              {renderAgentLabel(entry.fromAgentId)} {'->'} {renderAgentLabel(entry.toAgentId)}
                            </span>
                          </div>
                          <p className="mt-1 text-xs text-zinc-400">{entry.reason}</p>
                          <p className="mt-1 text-[10px] uppercase tracking-wider text-zinc-500">
                            {entry.status} {msg.workflowId ? `• workflow ${msg.workflowId}` : ''}
                          </p>
                        </div>
                      ))}
                    </div>
                  )}
                  {msg.sender === 'agent' && msg.invokedTools?.length > 0 && (
                    <div className="mt-3 space-y-2">
                      <p className="text-[10px] uppercase tracking-wider text-zinc-500 font-semibold">
                        Tool Activity
                      </p>
                      {msg.invokedTools.map((tool, toolIdx) => (
                        <div
                          key={`${tool.toolName}-${toolIdx}`}
                          className="rounded-xl border border-cyan-500/10 bg-black/30 px-3 py-2"
                        >
                          <div className="flex items-center justify-between gap-3 mb-1">
                            <span className="text-xs font-semibold text-cyan-300">{tool.toolName}</span>
                            <span className="text-[10px] uppercase tracking-wider text-zinc-500">
                              {tool.status}
                            </span>
                          </div>
                          <p className="text-xs text-zinc-400">{tool.summary}</p>
                        </div>
                      ))}
                    </div>
                  )}
                  {msg.sender === 'agent' && msg.routeAction && (
                    <RouteActionCard action={msg.routeAction} onContinue={onRouteIntent} />
                  )}
                </div>
                {msg.sender === 'user' && (
                  <div className="h-7 w-7 rounded-lg flex items-center justify-center ml-2 mt-1 flex-shrink-0 bg-zinc-800">
                    <User className="h-3.5 w-3.5 text-zinc-400" />
                  </div>
                )}
              </div>
            ))}
            {isTyping && (
              <div className="flex justify-start animate-fade-in">
                <div className={`h-7 w-7 rounded-lg flex items-center justify-center mr-2 mt-1 flex-shrink-0 ${c.bg}`}>
                  <AgentIcon className={`h-3.5 w-3.5 ${c.text}`} />
                </div>
                <div className="bg-zinc-800/80 px-4 py-3 rounded-2xl rounded-bl-none border border-zinc-700 text-sm text-zinc-400 flex items-center gap-2">
                  <Loader className="h-3 w-3 animate-spin" /> Thinking...
                </div>
              </div>
            )}
            {error && (
              <div className="rounded-xl border border-red-500/20 bg-red-500/10 px-4 py-3 text-sm text-red-300">
                {error}
              </div>
            )}
            <div ref={messagesEndRef} />
          </div>

          <div className="p-4 border-t border-zinc-800">
            <div className="flex gap-2">
              <input
                type="text"
                value={input}
                onChange={e => setInput(e.target.value)}
                onKeyDown={e => e.key === 'Enter' && sendMessage()}
                placeholder={`Ask ${selectedAgent.name} anything...`}
                className="flex-1 px-4 py-3 bg-zinc-900 border border-zinc-800 rounded-xl text-sm text-white placeholder-zinc-500 focus:outline-none focus:border-cyan-500/50 transition-colors"
              />
              <button
                onClick={sendMessage}
                disabled={!input.trim() || isTyping}
                className="px-5 py-3 bg-gradient-to-r from-cyan-500 to-purple-600 rounded-xl text-sm font-semibold text-white hover:shadow-lg hover:shadow-cyan-500/20 transition-all disabled:opacity-30"
              >
                <Send className="h-4 w-4" />
              </button>
            </div>
          </div>
        </div>
        <div className="w-80 flex-shrink-0 glass-panel rounded-2xl overflow-hidden">
          <div className="p-4 border-b border-zinc-800 flex items-center gap-2">
            <Network className="h-4 w-4 text-cyan-400" />
            <div>
              <h3 className="text-sm font-bold text-white">API Activity</h3>
              <p className="text-[10px] text-zinc-500">Frontend to backend trace</p>
            </div>
          </div>
          <div className="p-4 border-b border-zinc-800 bg-black/20">
            <p className="text-[10px] uppercase tracking-wider text-zinc-500 mb-1">Base URL</p>
            <p className="text-xs font-mono text-cyan-300 break-all">{getApiBase()}</p>
          </div>
          <div className="p-4 space-y-3 max-h-[calc(100vh-16rem)] overflow-y-auto">
            {chatApiCalls.length === 0 && (
              <div className="rounded-xl border border-zinc-800 bg-black/30 px-3 py-3 text-xs text-zinc-500">
                Send a message to show the exact chat API calls from the frontend.
              </div>
            )}
            {chatApiCalls.map((call) => (
              <div key={call.id} className="rounded-xl border border-zinc-800 bg-black/30 px-3 py-3">
                <div className="flex items-center justify-between gap-3">
                  <span className="text-[10px] font-semibold uppercase tracking-wider text-cyan-300">
                    {call.method}
                  </span>
                  <span className={`text-[10px] font-mono ${call.ok ? 'text-green-400' : 'text-red-400'}`}>
                    {call.status}
                  </span>
                </div>
                <p className="mt-1 text-xs font-mono text-zinc-300">{call.path}</p>
                <p className="mt-1 text-[10px] text-zinc-500">{call.durationMs}ms</p>
                {call.error && (
                  <p className="mt-2 text-[10px] text-red-300">{call.error}</p>
                )}
              </div>
            ))}
          </div>
        </div>
        </div>
      </div>
    </div>
  );
}
