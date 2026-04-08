import React, { useEffect, useState } from 'react';
import {
  Video, Calendar, Clock, Users, ChevronRight, X,
  MessageSquare, Zap, CheckCircle2, AlertTriangle,
  ArrowRight, User, Search, Bot, Loader,
  CalendarPlus, BrainCircuit, Mic
} from 'lucide-react';
import { analyzeMeeting, fetchMeetings, scheduleMeeting } from '../api';

const providerLogos = {
  zoom: { name: 'Zoom', color: 'text-blue-400', bg: 'bg-blue-500/10', border: 'border-blue-500/20' },
  gmeet: { name: 'Google Meet', color: 'text-green-400', bg: 'bg-green-500/10', border: 'border-green-500/20' },
  teams: { name: 'MS Teams', color: 'text-purple-400', bg: 'bg-purple-500/10', border: 'border-purple-500/20' },
};

export function MeetingsView({ token }) {
  const [meetings, setMeetings] = useState([]);
  const [selectedMeetingId, setSelectedMeetingId] = useState(null);
  const [showTranscript, setShowTranscript] = useState(false);
  const [showExtracted, setShowExtracted] = useState(false);
  const [filterProvider, setFilterProvider] = useState('all');
  const [searchQuery, setSearchQuery] = useState('');
  const [showScheduler, setShowScheduler] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [analyzing, setAnalyzing] = useState(false);

  const [schedForm, setSchedForm] = useState({
    title: '', provider: 'zoom', date: '', time: '', attendees: '', agentJoin: true
  });
  const [scheduling, setScheduling] = useState(false);
  const [scheduleSteps, setScheduleSteps] = useState([]);
  const [scheduleIdx, setScheduleIdx] = useState(-1);

  useEffect(() => {
    let cancelled = false;

    const loadMeetings = async () => {
      setLoading(true);
      try {
        const data = await fetchMeetings(token);
        if (!cancelled) {
          setMeetings(data);
          setError('');
        }
      } catch (err) {
        if (!cancelled) {
          setError(err.message || 'Unable to load meetings.');
        }
      } finally {
        if (!cancelled) {
          setLoading(false);
        }
      }
    };

    loadMeetings();
    return () => {
      cancelled = true;
    };
  }, [token]);

  const selectedMeeting = meetings.find(meeting => meeting.id === selectedMeetingId) ?? null;

  const filteredMeetings = meetings.filter(meeting => {
    const matchProvider = filterProvider === 'all' || meeting.provider === filterProvider;
    const matchSearch = meeting.title.toLowerCase().includes(searchQuery.toLowerCase());
    return matchProvider && matchSearch;
  });

  const handleSchedule = () => {
    if (!schedForm.title || !schedForm.date || !schedForm.time) return;
    setScheduling(true);
    setScheduleSteps([
      'Validating meeting details...',
      `Connecting to ${providerLogos[schedForm.provider].name} API...`,
      'Creating calendar event...',
      schedForm.agentJoin ? 'Assigning MeetIntel Agent to join meeting...' : 'Skipping agent assignment...',
      'Persisting meeting details in NexusCore...',
      'Meeting scheduled successfully!',
    ]);
    setScheduleIdx(0);
  };

  useEffect(() => {
    if (!scheduling || scheduleIdx < 0 || scheduleIdx >= scheduleSteps.length) return;

    const timer = window.setTimeout(async () => {
      if (scheduleIdx >= scheduleSteps.length - 1) {
        try {
          const createdMeeting = await scheduleMeeting(token, {
            title: schedForm.title,
            provider: schedForm.provider,
            date: schedForm.date,
            time: schedForm.time,
            attendees: schedForm.attendees
              ? schedForm.attendees.split(',').map(item => item.trim()).filter(Boolean)
              : [],
            agentJoin: schedForm.agentJoin,
          });
          setMeetings(prev => [createdMeeting, ...prev]);
          setShowScheduler(false);
          setScheduling(false);
          setScheduleIdx(-1);
          setSchedForm({ title: '', provider: 'zoom', date: '', time: '', attendees: '', agentJoin: true });
        } catch (err) {
          setError(err.message || 'Unable to schedule the meeting.');
          setScheduling(false);
          setScheduleIdx(-1);
        }
      } else {
        setScheduleIdx(prev => prev + 1);
      }
    }, 900);

    return () => window.clearTimeout(timer);
  }, [scheduleIdx, scheduleSteps, scheduling, schedForm, token]);

  const handleAnalyzeMeeting = async () => {
    if (!selectedMeeting || selectedMeeting.extracted.length > 0) {
      setShowExtracted(true);
      setShowTranscript(false);
      return;
    }

    setAnalyzing(true);
    try {
      const extracted = await analyzeMeeting(token, selectedMeeting.id);
      setMeetings(prev =>
        prev.map(meeting =>
          meeting.id === selectedMeeting.id
            ? { ...meeting, extracted, status: 'analyzed' }
            : meeting
        )
      );
      setShowExtracted(true);
      setShowTranscript(false);
      setError('');
    } catch (err) {
      setError(err.message || 'Unable to analyze the meeting.');
    } finally {
      setAnalyzing(false);
    }
  };

  return (
    <div>
      <div className="flex items-center justify-between mb-8">
        <h1 className="text-3xl font-light text-white">Meeting <span className="font-bold text-cyan-400">Intelligence</span></h1>
        {!selectedMeeting && (
          <button
            onClick={() => setShowScheduler(true)}
            className="flex items-center gap-2 px-5 py-2.5 bg-gradient-to-r from-cyan-500 to-purple-600 rounded-xl text-sm font-semibold text-white shadow-lg shadow-cyan-500/20 hover:shadow-cyan-500/40 transition-all"
          >
            <CalendarPlus className="h-4 w-4" /> Schedule Meeting
          </button>
        )}
      </div>

      {error && (
        <div className="mb-6 rounded-2xl border border-red-500/20 bg-red-500/10 px-4 py-3 text-sm text-red-300">
          {error}
        </div>
      )}

      {showScheduler && (
        <div className="fixed inset-0 z-[100] flex items-center justify-center" onClick={() => !scheduling && setShowScheduler(false)}>
          <div className="absolute inset-0 bg-black/60 backdrop-blur-sm"></div>
          <div className="relative w-full max-w-lg glass-panel rounded-2xl p-6 animate-fade-in" onClick={e => e.stopPropagation()}>
            <div className="flex justify-between items-center mb-6">
              <h2 className="text-xl font-bold text-white flex items-center gap-2">
                <CalendarPlus className="h-5 w-5 text-cyan-400" /> Schedule New Meeting
              </h2>
              {!scheduling && (
                <button onClick={() => setShowScheduler(false)} className="p-2 rounded-lg hover:bg-zinc-800 text-zinc-400">
                  <X className="h-5 w-5" />
                </button>
              )}
            </div>

            {!scheduling ? (
              <div className="space-y-4">
                <div>
                  <label className="text-xs text-zinc-400 uppercase tracking-wider mb-1 block">Meeting Title</label>
                  <input
                    type="text"
                    value={schedForm.title}
                    onChange={e => setSchedForm({ ...schedForm, title: e.target.value })}
                    placeholder="e.g. Q4 Planning Session"
                    className="w-full px-4 py-3 bg-zinc-900 border border-zinc-800 rounded-xl text-sm text-white placeholder-zinc-500 focus:outline-none focus:border-cyan-500/50"
                  />
                </div>
                <div>
                  <label className="text-xs text-zinc-400 uppercase tracking-wider mb-1 block">Platform</label>
                  <div className="flex gap-2">
                    {Object.entries(providerLogos).map(([key, prov]) => (
                      <button
                        key={key}
                        onClick={() => setSchedForm({ ...schedForm, provider: key })}
                        className={`flex-1 p-3 rounded-xl flex items-center justify-center gap-2 text-sm font-medium border transition-all ${
                          schedForm.provider === key ? `${prov.bg} ${prov.border} ${prov.color} border` : 'bg-zinc-800 border-transparent text-zinc-500 hover:text-zinc-300'
                        }`}
                      >
                        <Video className="h-4 w-4" /> {prov.name}
                      </button>
                    ))}
                  </div>
                </div>
                <div className="grid grid-cols-2 gap-4">
                  <div>
                    <label className="text-xs text-zinc-400 uppercase tracking-wider mb-1 block">Date</label>
                    <input
                      type="date"
                      value={schedForm.date}
                      onChange={e => setSchedForm({ ...schedForm, date: e.target.value })}
                      className="w-full px-4 py-3 bg-zinc-900 border border-zinc-800 rounded-xl text-sm text-white focus:outline-none focus:border-cyan-500/50"
                    />
                  </div>
                  <div>
                    <label className="text-xs text-zinc-400 uppercase tracking-wider mb-1 block">Time</label>
                    <input
                      type="time"
                      value={schedForm.time}
                      onChange={e => setSchedForm({ ...schedForm, time: e.target.value })}
                      className="w-full px-4 py-3 bg-zinc-900 border border-zinc-800 rounded-xl text-sm text-white focus:outline-none focus:border-cyan-500/50"
                    />
                  </div>
                </div>
                <div>
                  <label className="text-xs text-zinc-400 uppercase tracking-wider mb-1 block">Attendees (comma separated)</label>
                  <input
                    type="text"
                    value={schedForm.attendees}
                    onChange={e => setSchedForm({ ...schedForm, attendees: e.target.value })}
                    placeholder="e.g. Sarah Chen, Rupam Jana"
                    className="w-full px-4 py-3 bg-zinc-900 border border-zinc-800 rounded-xl text-sm text-white placeholder-zinc-500 focus:outline-none focus:border-cyan-500/50"
                  />
                </div>

                <div
                  className={`p-4 rounded-xl border transition-all cursor-pointer ${
                    schedForm.agentJoin ? 'bg-cyan-500/5 border-cyan-500/30' : 'bg-zinc-900 border-zinc-800'
                  }`}
                  onClick={() => setSchedForm({ ...schedForm, agentJoin: !schedForm.agentJoin })}
                >
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-3">
                      <div className={`h-10 w-10 rounded-xl flex items-center justify-center ${schedForm.agentJoin ? 'bg-cyan-500/20 text-cyan-400' : 'bg-zinc-800 text-zinc-500'}`}>
                        <BrainCircuit className="h-5 w-5" />
                      </div>
                      <div>
                        <h4 className="text-sm font-medium text-white">Send AI Agent to Meeting</h4>
                        <p className="text-[10px] text-zinc-500">MeetIntel Agent will join, record, transcribe, and extract action items automatically</p>
                      </div>
                    </div>
                    <div className={`h-6 w-11 rounded-full flex items-center transition-all ${schedForm.agentJoin ? 'bg-cyan-500 justify-end' : 'bg-zinc-700 justify-start'}`}>
                      <div className="h-5 w-5 bg-white rounded-full mx-0.5 shadow-sm"></div>
                    </div>
                  </div>
                  {schedForm.agentJoin && (
                    <div className="mt-3 pt-3 border-t border-cyan-500/10 grid grid-cols-3 gap-2">
                      {[
                        { icon: Mic, label: 'Auto-Record' },
                        { icon: MessageSquare, label: 'Live Transcribe' },
                        { icon: Zap, label: 'Extract Intel' },
                      ].map((feat, i) => (
                        <div key={i} className="flex items-center gap-1.5 text-[10px] text-cyan-300">
                          <feat.icon className="h-3 w-3" /> {feat.label}
                        </div>
                      ))}
                    </div>
                  )}
                </div>

                <button
                  onClick={handleSchedule}
                  disabled={!schedForm.title || !schedForm.date || !schedForm.time}
                  className="w-full py-3 bg-gradient-to-r from-cyan-500 to-purple-600 rounded-xl text-sm font-semibold text-white hover:shadow-lg hover:shadow-cyan-500/20 transition-all disabled:opacity-30 disabled:cursor-not-allowed"
                >
                  Schedule Meeting
                </button>
              </div>
            ) : (
              <div className="space-y-3 py-4">
                {scheduleSteps.map((step, idx) => (
                  <div key={idx} className={`flex items-center gap-3 text-sm transition-all duration-500 ${idx <= scheduleIdx ? 'opacity-100' : 'opacity-20'}`}>
                    <span className="flex-shrink-0">
                      {idx < scheduleIdx ? <CheckCircle2 className="h-4 w-4 text-green-400" /> :
                       idx === scheduleIdx ? <Loader className="h-4 w-4 text-cyan-400 animate-spin" /> :
                       <Clock className="h-4 w-4 text-zinc-600" />}
                    </span>
                    <span className="text-zinc-300">{step}</span>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      )}

      {selectedMeeting ? (
        <div className="animate-fade-in">
          <button
            onClick={() => {
              setSelectedMeetingId(null);
              setShowTranscript(false);
              setShowExtracted(false);
            }}
            className="flex items-center gap-1 text-sm text-zinc-400 hover:text-white mb-6 transition-colors"
          >
            ← Back to Meetings
          </button>

          <div className="glass-panel p-6 rounded-2xl mb-6">
            <div className="flex items-start justify-between">
              <div className="flex items-center gap-4">
                <div className={`p-3 rounded-xl ${providerLogos[selectedMeeting.provider].bg} border ${providerLogos[selectedMeeting.provider].border}`}>
                  <Video className={`h-6 w-6 ${providerLogos[selectedMeeting.provider].color}`} />
                </div>
                <div>
                  <h2 className="text-2xl font-bold text-white">{selectedMeeting.title}</h2>
                  <div className="flex items-center gap-4 mt-1 text-sm text-zinc-400">
                    <span className="flex items-center gap-1"><Calendar className="h-3 w-3" /> {selectedMeeting.date}</span>
                    <span className="flex items-center gap-1"><Clock className="h-3 w-3" /> {selectedMeeting.time}</span>
                    <span className={`px-2 py-0.5 rounded-full text-[10px] font-bold uppercase ${providerLogos[selectedMeeting.provider].bg} ${providerLogos[selectedMeeting.provider].color}`}>
                      {providerLogos[selectedMeeting.provider].name}
                    </span>
                  </div>
                </div>
              </div>
              <div className="flex items-center gap-2">
                {selectedMeeting.agentJoined && (
                  <span className="flex items-center gap-1 px-3 py-1 bg-cyan-500/10 text-cyan-400 border border-cyan-500/20 rounded-full text-xs font-bold">
                    <Bot className="h-3 w-3" /> Agent Joined
                  </span>
                )}
                {selectedMeeting.status === 'live' && (
                  <span className="flex items-center gap-1 px-3 py-1 bg-red-500/10 text-red-400 border border-red-500/20 rounded-full text-xs font-bold animate-pulse">
                    <span className="h-2 w-2 rounded-full bg-red-500"></span> LIVE
                  </span>
                )}
                {selectedMeeting.status === 'scheduled' && (
                  <span className="px-3 py-1 bg-yellow-500/10 text-yellow-400 border border-yellow-500/20 rounded-full text-xs font-bold">SCHEDULED</span>
                )}
              </div>
            </div>
            <div className="flex flex-wrap gap-2 mt-4">
              {selectedMeeting.attendees.map((attendee, i) => (
                <span key={i} className={`px-2 py-1 rounded-full text-xs flex items-center gap-1 ${
                  attendee.includes('Agent') ? 'bg-cyan-500/10 text-cyan-400 border border-cyan-500/20' : 'bg-zinc-800 text-zinc-400'
                }`}>
                  {attendee.includes('Agent') ? <Bot className="h-3 w-3" /> : <User className="h-3 w-3" />} {attendee}
                </span>
              ))}
            </div>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mb-6">
            <button
              onClick={() => {
                setShowTranscript(!showTranscript);
                setShowExtracted(false);
              }}
              disabled={selectedMeeting.transcript.length === 0}
              className={`glass-panel p-5 rounded-2xl flex items-center gap-4 transition-all ${
                showTranscript ? 'border-cyan-500/30 bg-cyan-950/10' : 'hover:border-zinc-600'
              } ${selectedMeeting.transcript.length === 0 ? 'opacity-40 cursor-not-allowed' : 'cursor-pointer'}`}
            >
              <div className="p-3 bg-cyan-500/10 rounded-xl text-cyan-400"><MessageSquare className="h-6 w-6" /></div>
              <div className="text-left">
                <h3 className="text-white font-medium">Show Transcript</h3>
                <p className="text-xs text-zinc-500">{selectedMeeting.transcript.length > 0 ? `${selectedMeeting.transcript.length} messages captured` : 'Transcript not yet available'}</p>
              </div>
              <ChevronRight className="h-5 w-5 text-zinc-600 ml-auto" />
            </button>
            <button
              onClick={handleAnalyzeMeeting}
              disabled={analyzing}
              className={`glass-panel p-5 rounded-2xl flex items-center gap-4 transition-all ${
                showExtracted ? 'border-purple-500/30 bg-purple-950/10' : 'hover:border-zinc-600'
              } ${analyzing ? 'opacity-70 cursor-wait' : 'cursor-pointer'}`}
            >
              <div className="p-3 bg-purple-500/10 rounded-xl text-purple-400">
                {analyzing ? <Loader className="h-6 w-6 animate-spin" /> : <Zap className="h-6 w-6" />}
              </div>
              <div className="text-left">
                <h3 className="text-white font-medium">{selectedMeeting.extracted.length > 0 ? 'Extracted Intelligence' : 'Run Intelligence'}</h3>
                <p className="text-xs text-zinc-500">
                  {selectedMeeting.extracted.length > 0 ? `${selectedMeeting.extracted.length} items extracted` : 'Generate analysis from meeting transcript'}
                </p>
              </div>
              <ChevronRight className="h-5 w-5 text-zinc-600 ml-auto" />
            </button>
          </div>

          {showTranscript && (
            <div className="glass-panel p-6 rounded-2xl animate-fade-in">
              <h3 className="text-lg font-bold text-white mb-4 flex items-center gap-2"><MessageSquare className="h-5 w-5 text-cyan-400" /> Full Transcript</h3>
              <div className="space-y-3 max-h-[500px] overflow-y-auto pr-2">
                {selectedMeeting.transcript.map((line, idx) => (
                  <div key={idx} className="flex items-start gap-3">
                    <div className="flex-shrink-0 mt-1 h-7 w-7 rounded-full bg-zinc-800 flex items-center justify-center text-[10px] text-zinc-400 font-mono">
                      {line.speaker.split(' ').map(word => word[0]).join('')}
                    </div>
                    <div>
                      <div className="flex items-center gap-2 mb-0.5">
                        <span className="text-xs font-semibold text-cyan-300">{line.speaker}</span>
                        <span className="text-[10px] text-zinc-600 font-mono">{line.time}</span>
                      </div>
                      <p className="text-sm text-zinc-300">{line.text}</p>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {showExtracted && (
            <div className="glass-panel p-6 rounded-2xl animate-fade-in">
              <h3 className="text-lg font-bold text-white mb-4 flex items-center gap-2"><Zap className="h-5 w-5 text-purple-400" /> Extracted Intelligence</h3>
              <div className="space-y-3 max-h-[500px] overflow-y-auto pr-1">
                {selectedMeeting.extracted.map((item, idx) => (
                  <div key={idx} className="bg-black/40 p-4 rounded-xl border border-zinc-800">
                    <div className="flex items-start justify-between mb-2">
                      <div className="flex items-center gap-2">
                        {item.type === 'decision' && <CheckCircle2 className="h-4 w-4 text-green-400" />}
                        {item.type === 'action' && <ArrowRight className="h-4 w-4 text-cyan-400" />}
                        {item.type === 'escalation' && <AlertTriangle className="h-4 w-4 text-yellow-400" />}
                        <span className={`text-xs uppercase font-bold tracking-wider ${
                          item.type === 'decision' ? 'text-green-400' : item.type === 'action' ? 'text-cyan-400' : 'text-yellow-400'
                        }`}>{item.type}</span>
                      </div>
                      <span className={`px-2 py-0.5 rounded-full text-[10px] font-semibold ${
                        item.status === 'decided' || item.status === 'resolved' ? 'bg-green-400/10 text-green-400' :
                        item.status === 'in-progress' ? 'bg-cyan-400/10 text-cyan-400' :
                        'bg-zinc-700/50 text-zinc-400'
                      }`}>{item.status}</span>
                    </div>
                    <p className="text-sm text-zinc-200 mb-2">{item.text}</p>
                    <div className="flex items-center justify-between text-xs text-zinc-500">
                      <span className="flex items-center gap-1"><User className="h-3 w-3" /> {item.owner}</span>
                      {item.deadline && <span className="flex items-center gap-1"><Clock className="h-3 w-3" /> {item.deadline}</span>}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      ) : (
        <>
          <div className="flex flex-wrap items-center gap-4 mb-6">
            <div className="relative flex-1 min-w-[200px]">
              <Search className="absolute left-4 top-1/2 -translate-y-1/2 h-4 w-4 text-zinc-500" />
              <input
                type="text"
                placeholder="Search meetings..."
                value={searchQuery}
                onChange={e => setSearchQuery(e.target.value)}
                className="w-full pl-11 pr-4 py-3 bg-zinc-900/80 border border-zinc-800 rounded-xl text-sm text-white placeholder-zinc-500 focus:outline-none focus:border-cyan-500/50"
              />
            </div>
            <div className="flex gap-2">
              {['all', 'zoom', 'gmeet', 'teams'].map(filter => (
                <button
                  key={filter}
                  onClick={() => setFilterProvider(filter)}
                  className={`px-4 py-2.5 rounded-xl text-xs font-semibold transition-all capitalize ${
                    filterProvider === filter ? 'bg-cyan-500/10 text-cyan-400 border border-cyan-500/30' : 'bg-zinc-800 text-zinc-500 border border-transparent hover:text-zinc-300'
                  }`}
                >
                  {filter === 'all' ? 'All' : providerLogos[filter].name}
                </button>
              ))}
            </div>
          </div>

          {loading ? (
            <div className="glass-panel p-8 rounded-2xl text-zinc-400">Loading meetings...</div>
          ) : (
            <div className="space-y-4">
              {filteredMeetings.map(meeting => {
                const provider = providerLogos[meeting.provider];
                return (
                  <div
                    key={meeting.id}
                    onClick={() => setSelectedMeetingId(meeting.id)}
                    className="glass-panel p-5 rounded-2xl cursor-pointer hover:border-cyan-500/20 transition-all group flex items-center gap-5"
                  >
                    <div className={`p-3 rounded-xl ${provider.bg} border ${provider.border} flex-shrink-0`}>
                      <Video className={`h-5 w-5 ${provider.color}`} />
                    </div>
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2 mb-1">
                        <h3 className="text-white font-medium group-hover:text-cyan-400 transition-colors truncate">{meeting.title}</h3>
                        {meeting.status === 'live' && (
                          <span className="flex items-center gap-1 px-2 py-0.5 bg-red-500/10 text-red-400 border border-red-500/20 rounded-full text-[10px] font-bold animate-pulse">LIVE</span>
                        )}
                        {meeting.status === 'scheduled' && (
                          <span className="px-2 py-0.5 bg-yellow-500/10 text-yellow-400 border border-yellow-500/20 rounded-full text-[10px] font-bold">SCHEDULED</span>
                        )}
                        {meeting.agentJoined && (
                          <span className="px-2 py-0.5 bg-cyan-500/10 text-cyan-400 border border-cyan-500/20 rounded-full text-[10px] font-bold flex items-center gap-1"><Bot className="h-2.5 w-2.5" /> Agent</span>
                        )}
                      </div>
                      <div className="flex items-center gap-4 text-xs text-zinc-500">
                        <span className="flex items-center gap-1"><Calendar className="h-3 w-3" /> {meeting.date}</span>
                        <span className="flex items-center gap-1"><Clock className="h-3 w-3" /> {meeting.duration}</span>
                        <span className="flex items-center gap-1"><Users className="h-3 w-3" /> {meeting.attendees.length}</span>
                        <span className={`${provider.color} font-semibold`}>{provider.name}</span>
                      </div>
                    </div>
                    <div className="flex items-center gap-3 flex-shrink-0">
                      {meeting.extracted.length > 0 && (
                        <span className="px-2 py-1 bg-purple-500/10 text-purple-400 rounded-lg text-xs border border-purple-500/20">
                          {meeting.extracted.length} items
                        </span>
                      )}
                      <ChevronRight className="h-5 w-5 text-zinc-600 group-hover:text-cyan-400 transition-colors" />
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </>
      )}
    </div>
  );
}
