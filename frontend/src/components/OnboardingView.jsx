import React, { useCallback, useEffect, useState } from 'react';
import {
  UserPlus, Search, Mail, Phone, Building, Briefcase, Calendar, MapPin,
  Bot, Loader, CheckCircle2, Clock, Camera
} from 'lucide-react';
import { createEmployee, fetchEmployees } from '../api';

const onboardingAgentSteps = [
  { question: "Welcome! I'm the Onboarding Agent. Let's get started. What is the new employee's full name?", field: 'name', type: 'text' },
  { question: 'Great! What role will they be joining as?', field: 'role', type: 'text' },
  { question: 'Which department?', field: 'department', type: 'select', options: ['Engineering', 'Product', 'Design', 'Marketing', 'Sales', 'Finance', 'HR', 'Legal'] },
  { question: "What's their email address?", field: 'email', type: 'text' },
  { question: 'Phone number?', field: 'phone', type: 'text' },
  { question: 'Office location?', field: 'location', type: 'text' },
  { question: 'What is their start date?', field: 'startDate', type: 'date' },
  { question: 'Please upload their profile photo.', field: 'photo', type: 'file' },
];

const automationSteps = [
  { name: 'Identity Verification', agent: 'Shield Verifier', duration: 900 },
  { name: 'Background Check Initiated', agent: 'Data Fetcher v4', duration: 900 },
  { name: 'Google Workspace Account Created', agent: 'Action Exec Alpha', duration: 900 },
  { name: 'Slack and GitHub Provisioned', agent: 'Action Exec Alpha', duration: 900 },
  { name: 'Hardware Request Submitted', agent: 'Nexus Orchestrator', duration: 900 },
  { name: 'Manager Notification Sent', agent: 'Action Exec Alpha', duration: 900 },
  { name: 'Day 1 Calendar Created', agent: 'Action Exec Alpha', duration: 900 },
  { name: 'Onboarding Complete', agent: 'Shield Verifier', duration: 900 },
];

const emptyOnboardingDraft = {
  name: '',
  role: '',
  department: '',
  email: '',
  phone: '',
  location: '',
  startDate: '',
  photo: null,
};

function formatEmployeeStartDate(value) {
  if (!value || typeof value !== 'string') {
    return value || '';
  }

  const isoDateMatch = value.match(/^(\d{4}-\d{2}-\d{2})T/);
  if (isoDateMatch) {
    return isoDateMatch[1];
  }

  return value;
}

function findNextMissingStep(formData) {
  return onboardingAgentSteps.findIndex((step) => !formData[step.field]);
}

function buildHandoffSummary(routeAction) {
  if (!routeAction?.prefill) {
    return '';
  }

  const bits = [];
  if (routeAction.prefill.role) {
    bits.push(`role ${routeAction.prefill.role}`);
  }
  if (routeAction.prefill.department) {
    bits.push(`department ${routeAction.prefill.department}`);
  }
  if (routeAction.prefill.startDate) {
    bits.push(`start date ${routeAction.prefill.startDate}`);
  }
  if (routeAction.prefill.suggestedEmail) {
    bits.push(`suggested company email ${routeAction.prefill.suggestedEmail}`);
  }

  return bits.length > 0
    ? `Routed from Nexus Orchestrator with ${bits.join(', ')}.`
    : 'Routed from Nexus Orchestrator for guided onboarding.';
}

function buildRoutePrefill(routeAction) {
  const prefill = routeAction?.prefill ?? {};
  return {
    ...emptyOnboardingDraft,
    name: prefill.name ?? '',
    role: prefill.role ?? '',
    department: prefill.department ?? '',
    email: prefill.email ?? prefill.suggestedEmail ?? '',
    phone: prefill.phone ?? '',
    location: prefill.location ?? '',
    startDate: prefill.startDate ?? '',
    photo: null,
  };
}

export function OnboardingView({ token, routeAction = null, onRouteConsumed }) {
  const [view, setView] = useState('portal');
  const [employees, setEmployees] = useState([]);
  const [selectedEmployee, setSelectedEmployee] = useState(null);
  const [searchQuery, setSearchQuery] = useState('');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [handoffSummary, setHandoffSummary] = useState('');

  const [currentStep, setCurrentStep] = useState(0);
  const [formData, setFormData] = useState({});
  const [chatHistory, setChatHistory] = useState([]);
  const [userInput, setUserInput] = useState('');
  const [isAgentTyping, setIsAgentTyping] = useState(false);
  const [automationPhase, setAutomationPhase] = useState(false);
  const [automationIdx, setAutomationIdx] = useState(-1);
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    let cancelled = false;

    const loadEmployees = async () => {
      setLoading(true);
      try {
        const data = await fetchEmployees(token);
        if (!cancelled) {
          setEmployees(data);
          setError('');
        }
      } catch (err) {
        if (!cancelled) {
          setError(err.message || 'Unable to load employees.');
        }
      } finally {
        if (!cancelled) {
          setLoading(false);
        }
      }
    };

    loadEmployees();
    return () => {
      cancelled = true;
    };
  }, [token]);

  const filteredEmployees = employees.filter(employee =>
    employee.name.toLowerCase().includes(searchQuery.toLowerCase()) ||
    employee.department.toLowerCase().includes(searchQuery.toLowerCase()) ||
    employee.role.toLowerCase().includes(searchQuery.toLowerCase())
  );

  const queueAutomation = useCallback((draft) => {
    setChatHistory(prev => [...prev, {
      sender: 'agent',
      text: `Excellent! I have all the details for ${draft.name || 'the new employee'}. Initiating automated onboarding sequence now...`
    }]);
    window.setTimeout(() => {
      setAutomationPhase(true);
      setAutomationIdx(0);
    }, 800);
  }, []);

  const startOnboarding = useCallback((prefill = emptyOnboardingDraft, summary = '') => {
    const nextFormData = { ...emptyOnboardingDraft, ...prefill };
    const nextStep = findNextMissingStep(nextFormData);
    const initialHistory = [];

    if (summary) {
      initialHistory.push({ sender: 'agent', text: summary });
    }
    if (nextStep >= 0) {
      initialHistory.push({ sender: 'agent', text: onboardingAgentSteps[nextStep].question });
    }

    setView('new');
    setCurrentStep(nextStep >= 0 ? nextStep : onboardingAgentSteps.length - 1);
    setFormData(nextFormData);
    setChatHistory(initialHistory);
    setUserInput('');
    setAutomationPhase(false);
    setAutomationIdx(-1);
    setSubmitting(false);
    setError('');
    setHandoffSummary(summary);

    if (nextStep < 0) {
      window.setTimeout(() => {
        queueAutomation(nextFormData);
      }, 300);
    }
  }, [queueAutomation]);

  useEffect(() => {
    if (!routeAction || routeAction.targetTab !== 'onboarding') {
      return;
    }

    startOnboarding(buildRoutePrefill(routeAction), buildHandoffSummary(routeAction));
    onRouteConsumed?.();
  }, [routeAction, onRouteConsumed, startOnboarding]);

  const handleSubmitAnswer = () => {
    if (!userInput.trim() && onboardingAgentSteps[currentStep].type !== 'file') return;

    const step = onboardingAgentSteps[currentStep];
    const answer = userInput.trim();
    const nextFormData = { ...formData, [step.field]: answer };
    const nextStep = findNextMissingStep(nextFormData);

    setChatHistory(prev => [...prev, { sender: 'user', text: answer }]);
    setFormData(nextFormData);
    setUserInput('');
    setIsAgentTyping(true);

    window.setTimeout(() => {
      setIsAgentTyping(false);
      if (nextStep >= 0) {
        setCurrentStep(nextStep);
        setChatHistory(prev => [...prev, { sender: 'agent', text: onboardingAgentSteps[nextStep].question }]);
      } else {
        queueAutomation(nextFormData);
      }
    }, 600);
  };

  const handleFileUpload = (e) => {
    const file = e.target.files[0];
    if (!file) return;
    const reader = new FileReader();
    reader.onload = (event) => {
      const photoData = event.target.result;
      const nextFormData = { ...formData, photo: photoData };
      setFormData(nextFormData);
      setChatHistory(prev => [...prev, { sender: 'user', text: 'Photo uploaded', isPhoto: true, photoUrl: photoData }]);
      setIsAgentTyping(true);
      window.setTimeout(() => {
        setIsAgentTyping(false);
        queueAutomation(nextFormData);
      }, 600);
    };
    reader.readAsDataURL(file);
  };

  useEffect(() => {
    if (!automationPhase || automationIdx < 0 || automationIdx >= automationSteps.length) return;

    const timer = window.setTimeout(async () => {
      if (automationIdx >= automationSteps.length - 1) {
        if (submitting) return;
        setSubmitting(true);
        try {
          const createdEmployee = await createEmployee(token, {
            name: formData.name || 'New Employee',
            role: formData.role || 'Team Member',
            department: formData.department || 'Engineering',
            email: formData.email || 'new@nexuscore.ai',
            phone: formData.phone || '',
            location: formData.location || '',
            startDate: formData.startDate || 'TBD',
            photoUrl: formData.photo || null,
          });
          setEmployees(prev => [createdEmployee, ...prev]);
          setSelectedEmployee(createdEmployee);
          setAutomationIdx(prev => prev + 1);
        } catch (err) {
          setError(err.message || 'Unable to complete onboarding.');
          setAutomationPhase(false);
          setAutomationIdx(-1);
        } finally {
          setSubmitting(false);
        }
      } else {
        setAutomationIdx(prev => prev + 1);
      }
    }, automationSteps[automationIdx]?.duration || 900);

    return () => window.clearTimeout(timer);
  }, [automationIdx, automationPhase, formData, submitting, token]);

  return (
    <div>
      <div className="flex items-center justify-between mb-8">
        <h1 className="text-3xl font-light text-white">Employee <span className="font-bold text-cyan-400">
          {view === 'portal' ? 'Management' : view === 'new' ? 'Onboarding' : 'Profile'}
        </span></h1>
        <div className="flex gap-2">
          {view !== 'portal' && (
            <button onClick={() => setView('portal')} className="px-4 py-2 bg-zinc-800 rounded-xl text-sm text-zinc-400 hover:text-white transition-colors">
              ← Back to Portal
            </button>
          )}
          {view === 'portal' && (
            <button onClick={() => startOnboarding()} className="flex items-center gap-2 px-5 py-2.5 bg-gradient-to-r from-cyan-500 to-purple-600 rounded-xl text-sm font-semibold text-white shadow-lg shadow-cyan-500/20 hover:shadow-cyan-500/40 transition-all">
              <UserPlus className="h-4 w-4" /> New Employee
            </button>
          )}
        </div>
      </div>

      {error && (
        <div className="mb-6 rounded-2xl border border-red-500/20 bg-red-500/10 px-4 py-3 text-sm text-red-300">
          {error}
        </div>
      )}

      {view === 'portal' && (
        <>
          <div className="grid grid-cols-1 md:grid-cols-4 gap-4 mb-8">
            <div className="glass-panel p-4 rounded-2xl text-center">
              <p className="text-zinc-400 text-xs uppercase tracking-wider mb-1">Total Employees</p>
              <p className="text-3xl font-bold text-white">{employees.length}</p>
            </div>
            <div className="glass-panel p-4 rounded-2xl text-center">
              <p className="text-zinc-400 text-xs uppercase tracking-wider mb-1">Active</p>
              <p className="text-3xl font-bold text-green-400">{employees.filter(employee => employee.status === 'active').length}</p>
            </div>
            <div className="glass-panel p-4 rounded-2xl text-center">
              <p className="text-zinc-400 text-xs uppercase tracking-wider mb-1">Onboarding</p>
              <p className="text-3xl font-bold text-cyan-400">{employees.filter(employee => employee.status === 'onboarding').length}</p>
            </div>
            <div className="glass-panel p-4 rounded-2xl text-center">
              <p className="text-zinc-400 text-xs uppercase tracking-wider mb-1">Departments</p>
              <p className="text-3xl font-bold text-purple-400">{new Set(employees.map(employee => employee.department)).size}</p>
            </div>
          </div>

          <div className="relative mb-6">
            <Search className="absolute left-4 top-1/2 -translate-y-1/2 h-4 w-4 text-zinc-500" />
            <input
              type="text"
              placeholder="Search employees by name, role, or department..."
              value={searchQuery}
              onChange={e => setSearchQuery(e.target.value)}
              className="w-full pl-11 pr-4 py-3 bg-zinc-900/80 border border-zinc-800 rounded-xl text-sm text-white placeholder-zinc-500 focus:outline-none focus:border-cyan-500/50 transition-colors"
            />
          </div>

          {loading ? (
            <div className="glass-panel p-8 rounded-2xl text-zinc-400">Loading employees...</div>
          ) : (
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
              {filteredEmployees.map(employee => (
                <div
                  key={employee.id}
                  onClick={() => { setSelectedEmployee(employee); setView('detail'); }}
                  className="glass-panel p-5 rounded-2xl cursor-pointer hover:border-cyan-500/30 transition-all group"
                >
                  <div className="flex items-center gap-4 mb-4">
                    <div className="h-12 w-12 rounded-full bg-gradient-to-br from-cyan-500/20 to-purple-500/20 flex items-center justify-center text-white font-bold text-sm border border-zinc-700 overflow-hidden">
                      {employee.photo ? <img src={employee.photo} alt="" className="h-full w-full object-cover" /> : employee.avatar}
                    </div>
                    <div>
                      <h3 className="text-white font-medium group-hover:text-cyan-400 transition-colors">{employee.name}</h3>
                      <p className="text-xs text-zinc-500">{employee.role}</p>
                    </div>
                  </div>
                  <div className="flex items-center justify-between">
                    <span className="text-xs text-zinc-400 flex items-center gap-1"><Building className="h-3 w-3" /> {employee.department}</span>
                    <span className={`px-2 py-0.5 rounded-full text-[10px] font-bold uppercase ${
                      employee.status === 'active' ? 'bg-green-400/10 text-green-400' : 'bg-cyan-400/10 text-cyan-400'
                    }`}>{employee.status}</span>
                  </div>
                </div>
              ))}
            </div>
          )}
        </>
      )}

      {view === 'detail' && selectedEmployee && (
        <div className="glass-panel p-8 rounded-2xl max-w-2xl mx-auto">
          <div className="flex items-center gap-6 mb-8">
            <div className="h-20 w-20 rounded-full bg-gradient-to-br from-cyan-500/20 to-purple-500/20 flex items-center justify-center text-white font-bold text-2xl border border-zinc-700 overflow-hidden">
              {selectedEmployee.photo ? <img src={selectedEmployee.photo} alt="" className="h-full w-full object-cover" /> : selectedEmployee.avatar}
            </div>
            <div>
              <h2 className="text-2xl font-bold text-white">{selectedEmployee.name}</h2>
              <p className="text-cyan-400 text-sm">{selectedEmployee.role}</p>
              <span className={`inline-block mt-1 px-2 py-0.5 rounded-full text-[10px] font-bold uppercase ${
                selectedEmployee.status === 'active' ? 'bg-green-400/10 text-green-400' : 'bg-cyan-400/10 text-cyan-400'
              }`}>{selectedEmployee.status}</span>
            </div>
          </div>
          <div className="grid grid-cols-2 gap-4 text-sm">
            {[
              { icon: Mail, label: 'Email', value: selectedEmployee.email },
              { icon: Phone, label: 'Phone', value: selectedEmployee.phone },
              { icon: Building, label: 'Department', value: selectedEmployee.department },
              { icon: MapPin, label: 'Location', value: selectedEmployee.location },
              { icon: Calendar, label: 'Start Date', value: formatEmployeeStartDate(selectedEmployee.startDate) },
              { icon: Briefcase, label: 'Onboarding', value: `${selectedEmployee.progress}% Complete` },
            ].map((item, i) => (
              <div key={i} className="bg-black/30 p-4 rounded-xl border border-zinc-800">
                <div className="flex items-center gap-2 text-zinc-500 text-xs mb-1">
                  <item.icon className="h-3 w-3" /> {item.label}
                </div>
                <p className="text-white">{item.value}</p>
              </div>
            ))}
          </div>
        </div>
      )}

      {view === 'new' && (
        <div className="max-w-3xl mx-auto">
          <div className="glass-panel rounded-2xl overflow-hidden">
            <div className="bg-zinc-900/80 p-4 border-b border-zinc-800 flex items-center gap-3">
              <div className="h-8 w-8 rounded-full bg-cyan-500/20 flex items-center justify-center text-cyan-400">
                <Bot className="h-4 w-4" />
              </div>
              <div>
                <h3 className="text-sm font-bold text-white">Onboarding Agent</h3>
                <p className="text-[10px] text-green-400">Online • Step {Math.min(currentStep + 1, onboardingAgentSteps.length)} of {onboardingAgentSteps.length}</p>
              </div>
            </div>

            {handoffSummary && (
              <div className="border-b border-zinc-800 bg-cyan-500/10 px-4 py-3">
                <p className="text-xs text-cyan-200">{handoffSummary}</p>
              </div>
            )}

            <div className="p-6 max-h-[400px] overflow-y-auto space-y-4">
              {chatHistory.map((msg, idx) => (
                <div key={idx} className={`flex ${msg.sender === 'user' ? 'justify-end' : 'justify-start'} animate-fade-in`}>
                  <div className={`max-w-[75%] px-4 py-3 rounded-2xl text-sm ${
                    msg.sender === 'user'
                      ? 'bg-cyan-600/20 text-cyan-100 rounded-br-none border border-cyan-500/20'
                      : 'bg-zinc-800 text-zinc-200 rounded-bl-none border border-zinc-700'
                  }`}>
                    {msg.isPhoto && msg.photoUrl ? (
                      <div>
                        <img src={msg.photoUrl} alt="uploaded" className="h-16 w-16 rounded-lg object-cover mb-1" />
                        <p className="text-xs opacity-70">Photo uploaded</p>
                      </div>
                    ) : msg.text}
                  </div>
                </div>
              ))}
              {isAgentTyping && (
                <div className="flex justify-start animate-fade-in">
                  <div className="bg-zinc-800 px-4 py-3 rounded-2xl rounded-bl-none border border-zinc-700 text-sm text-zinc-400 flex items-center gap-2">
                    <Loader className="h-3 w-3 animate-spin" /> Typing...
                  </div>
                </div>
              )}
            </div>

            {automationPhase && (
              <div className="px-6 pb-4">
                <div className="bg-black/40 rounded-xl p-4 border border-zinc-800">
                  <h4 className="text-xs text-cyan-400 font-bold uppercase tracking-wider mb-3 flex items-center gap-1">
                    <Bot className="h-3 w-3" /> Automated Onboarding Sequence
                  </h4>
                  <div className="space-y-2">
                    {automationSteps.map((step, idx) => (
                      <div key={idx} className={`flex items-center gap-3 text-sm transition-all duration-500 ${idx <= automationIdx ? 'opacity-100' : 'opacity-20'}`}>
                        <span className="flex-shrink-0">
                          {idx < automationIdx ? <CheckCircle2 className="h-4 w-4 text-green-400" /> :
                           idx === automationIdx ? <Loader className="h-4 w-4 text-cyan-400 animate-spin" /> :
                           <Clock className="h-4 w-4 text-zinc-600" />}
                        </span>
                        <span className="text-zinc-300 flex-1">{step.name}</span>
                        <span className="text-[10px] text-cyan-400 font-mono">{step.agent}</span>
                      </div>
                    ))}
                  </div>
                  {automationIdx >= automationSteps.length && (
                    <div className="mt-4 pt-3 border-t border-zinc-800 text-center">
                      <p className="text-green-400 text-sm font-bold">✓ Employee Successfully Onboarded!</p>
                      <button
                        onClick={() => setView('portal')}
                        className="mt-2 px-4 py-2 bg-cyan-500/10 text-cyan-400 rounded-lg text-xs hover:bg-cyan-500/20"
                      >
                        View in Employee Portal →
                      </button>
                    </div>
                  )}
                </div>
              </div>
            )}

            {!automationPhase && (
              <div className="p-4 border-t border-zinc-800">
                {onboardingAgentSteps[currentStep]?.type === 'file' ? (
                  <label className="flex items-center justify-center gap-2 p-4 border-2 border-dashed border-zinc-700 rounded-xl cursor-pointer hover:border-cyan-500/50 transition-colors">
                    <Camera className="h-5 w-5 text-zinc-400" />
                    <span className="text-sm text-zinc-400">Click to upload photo</span>
                    <input type="file" accept="image/*" className="hidden" onChange={handleFileUpload} />
                  </label>
                ) : onboardingAgentSteps[currentStep]?.type === 'select' ? (
                  <div className="flex flex-wrap gap-2">
                    {onboardingAgentSteps[currentStep].options.map(option => (
                      <button
                        key={option}
                        onClick={() => setUserInput(option)}
                        className={`px-4 py-2 rounded-xl text-sm border transition-all ${
                          userInput === option ? 'bg-cyan-500/20 border-cyan-500/50 text-cyan-400' : 'bg-zinc-800 border-zinc-700 text-zinc-400 hover:border-zinc-500'
                        }`}
                      >
                        {option}
                      </button>
                    ))}
                    {userInput && (
                      <button onClick={handleSubmitAnswer} className="px-4 py-2 bg-cyan-600 rounded-xl text-sm font-semibold text-white ml-auto">
                        Confirm →
                      </button>
                    )}
                  </div>
                ) : (
                  <div className="flex gap-2">
                    <input
                      type={onboardingAgentSteps[currentStep]?.type === 'date' ? 'date' : 'text'}
                      value={userInput}
                      onChange={e => setUserInput(e.target.value)}
                      onKeyDown={e => e.key === 'Enter' && handleSubmitAnswer()}
                      placeholder="Type your answer..."
                      className="flex-1 px-4 py-3 bg-zinc-900 border border-zinc-800 rounded-xl text-sm text-white placeholder-zinc-500 focus:outline-none focus:border-cyan-500/50"
                    />
                    <button onClick={handleSubmitAnswer} className="px-5 py-3 bg-cyan-600 rounded-xl text-sm font-semibold text-white hover:bg-cyan-500 transition-colors">
                      Send
                    </button>
                  </div>
                )}
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
