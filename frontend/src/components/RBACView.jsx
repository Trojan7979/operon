import React, { useEffect, useMemo, useState } from 'react';
import {
  BarChart3,
  Check,
  Cpu,
  GitMerge,
  Lock,
  MessageSquare,
  Plus,
  Search,
  Shield,
  ShieldCheck,
  UserPlus,
  Users,
  X,
} from 'lucide-react';
import { createUser, fetchUsers, updateUser } from '../api';

const allModules = [
  { id: 'dashboard', name: 'Command Center', icon: BarChart3, desc: 'View system metrics and status' },
  { id: 'simulator', name: 'Live Simulator', icon: GitMerge, desc: 'Run workflow simulations' },
  { id: 'onboarding', name: 'Onboarding', icon: UserPlus, desc: 'Manage employee onboarding' },
  { id: 'workflows', name: 'Workflows', icon: GitMerge, desc: 'View process orchestration' },
  { id: 'agents', name: 'Swarm Agents', icon: Cpu, desc: 'Monitor AI agent swarm' },
  { id: 'collab', name: 'Agent Collab', icon: Users, desc: 'View agent collaboration' },
  { id: 'meetings', name: 'Meetings', icon: MessageSquare, desc: 'Meeting intelligence & scheduling' },
  { id: 'sla', name: 'SLA Monitor', icon: Shield, desc: 'Track SLA health and bottlenecks' },
  { id: 'chat', name: 'Agent Chat', icon: MessageSquare, desc: 'Chat with AI agents' },
  { id: 'audit', name: 'Audit Trail', icon: ShieldCheck, desc: 'View system audit logs' },
  { id: 'rbac', name: 'Access Control', icon: Lock, desc: 'Manage user permissions' },
];

const roleTemplates = [
  { name: 'Super Admin', permissions: allModules.map((module) => module.id) },
  { name: 'VP Engineering', permissions: ['dashboard', 'simulator', 'workflows', 'agents', 'collab', 'meetings', 'sla', 'chat', 'audit'] },
  { name: 'Product Manager', permissions: ['dashboard', 'workflows', 'meetings', 'chat'] },
  { name: 'UX Designer', permissions: ['dashboard', 'meetings', 'chat'] },
  { name: 'Backend Lead', permissions: ['dashboard', 'simulator', 'workflows', 'agents', 'collab', 'sla', 'chat', 'audit'] },
  { name: 'HR Manager', permissions: ['dashboard', 'onboarding', 'meetings', 'chat'] },
  { name: 'Auditor', permissions: ['dashboard', 'audit'] },
];

function sortUsersByName(users) {
  return [...users].sort((left, right) => left.name.localeCompare(right.name));
}

export function RBACView({ token }) {
  const [users, setUsers] = useState([]);
  const [selectedUserId, setSelectedUserId] = useState(null);
  const [searchQuery, setSearchQuery] = useState('');
  const [showAddUser, setShowAddUser] = useState(false);
  const [newUser, setNewUser] = useState({
    name: '',
    email: '',
    role: 'Product Manager',
    department: '',
  });
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');

  useEffect(() => {
    let cancelled = false;

    const loadUsers = async () => {
      if (!token) {
        setLoading(false);
        return;
      }

      setLoading(true);
      setError('');

      try {
        const response = await fetchUsers(token);
        if (cancelled) {
          return;
        }

        const nextUsers = sortUsersByName(response);
        setUsers(nextUsers);
        setSelectedUserId((current) => {
          if (current && nextUsers.some((user) => user.id === current)) {
            return current;
          }
          return nextUsers[0]?.id ?? null;
        });
      } catch (err) {
        if (!cancelled) {
          setError(err.message || 'Unable to load access control data.');
        }
      } finally {
        if (!cancelled) {
          setLoading(false);
        }
      }
    };

    loadUsers();

    return () => {
      cancelled = true;
    };
  }, [token]);

  const selectedUser = useMemo(
    () => users.find((user) => user.id === selectedUserId) ?? null,
    [selectedUserId, users],
  );

  const filteredUsers = useMemo(
    () =>
      users.filter((user) =>
        [user.name, user.email, user.role, user.department]
          .join(' ')
          .toLowerCase()
          .includes(searchQuery.toLowerCase()),
      ),
    [searchQuery, users],
  );

  const persistUserUpdate = async (userId, payload) => {
    if (!token) {
      return;
    }

    setSaving(true);
    setError('');

    try {
      const updatedUser = await updateUser(token, userId, payload);
      setUsers((currentUsers) =>
        sortUsersByName(
          currentUsers.map((user) => (user.id === userId ? updatedUser : user)),
        ),
      );
    } catch (err) {
      setError(err.message || 'Unable to save access changes.');
    } finally {
      setSaving(false);
    }
  };

  const togglePermission = async (userId, moduleId) => {
    const targetUser = users.find((user) => user.id === userId);
    if (!targetUser) {
      return;
    }

    const hasPermission = targetUser.permissions.includes(moduleId);
    const nextPermissions = hasPermission
      ? targetUser.permissions.filter((permission) => permission !== moduleId)
      : [...targetUser.permissions, moduleId];

    await persistUserUpdate(userId, { permissions: nextPermissions });
  };

  const applyTemplate = async (userId, templateName) => {
    const template = roleTemplates.find((role) => role.name === templateName);
    if (!template) {
      return;
    }

    await persistUserUpdate(userId, {
      role: templateName,
      permissions: template.permissions,
    });
  };

  const toggleStatus = async (userId) => {
    const targetUser = users.find((user) => user.id === userId);
    if (!targetUser) {
      return;
    }

    const nextStatus = targetUser.status === 'active' ? 'inactive' : 'active';
    await persistUserUpdate(userId, { status: nextStatus });
  };

  const addUser = async () => {
    if (!token || !newUser.name || !newUser.email) {
      return;
    }

    setSaving(true);
    setError('');

    try {
      const createdUser = await createUser(token, {
        name: newUser.name,
        email: newUser.email,
        role: newUser.role,
        department: newUser.department || 'General',
      });
      setUsers((currentUsers) => sortUsersByName([...currentUsers, createdUser]));
      setSelectedUserId(createdUser.id);
      setShowAddUser(false);
      setNewUser({ name: '', email: '', role: 'Product Manager', department: '' });
    } catch (err) {
      setError(err.message || 'Unable to create the user.');
    } finally {
      setSaving(false);
    }
  };

  const activeUsers = users.filter((user) => user.status === 'active').length;
  const uniqueRoles = new Set(users.map((user) => user.role)).size;

  return (
    <div>
      <div className="flex items-center justify-between mb-8">
        <h1 className="text-3xl font-light text-white">
          Access <span className="font-bold text-cyan-400">Control</span>
        </h1>
        <button
          onClick={() => setShowAddUser(true)}
          className="flex items-center gap-2 px-5 py-2.5 bg-gradient-to-r from-cyan-500 to-purple-600 rounded-xl text-sm font-semibold text-white shadow-lg shadow-cyan-500/20 hover:shadow-cyan-500/40 transition-all"
        >
          <Plus className="h-4 w-4" /> Add User
        </button>
      </div>

      {error && (
        <div className="mb-6 rounded-2xl border border-red-500/20 bg-red-500/10 px-4 py-3 text-sm text-red-300">
          {error}
        </div>
      )}

      <div className="grid grid-cols-1 md:grid-cols-4 gap-4 mb-8">
        <div className="glass-panel p-4 rounded-2xl text-center">
          <p className="text-zinc-400 text-xs uppercase tracking-wider mb-1">Total Users</p>
          <p className="text-3xl font-bold text-white">{users.length}</p>
        </div>
        <div className="glass-panel p-4 rounded-2xl text-center">
          <p className="text-zinc-400 text-xs uppercase tracking-wider mb-1">Active</p>
          <p className="text-3xl font-bold text-green-400">{activeUsers}</p>
        </div>
        <div className="glass-panel p-4 rounded-2xl text-center">
          <p className="text-zinc-400 text-xs uppercase tracking-wider mb-1">Roles</p>
          <p className="text-3xl font-bold text-purple-400">{uniqueRoles}</p>
        </div>
        <div className="glass-panel p-4 rounded-2xl text-center">
          <p className="text-zinc-400 text-xs uppercase tracking-wider mb-1">Modules</p>
          <p className="text-3xl font-bold text-cyan-400">{allModules.length}</p>
        </div>
      </div>

      {showAddUser && (
        <div
          className="fixed inset-0 z-[100] flex items-center justify-center"
          onClick={() => setShowAddUser(false)}
        >
          <div className="absolute inset-0 bg-black/60 backdrop-blur-sm"></div>
          <div
            className="relative glass-panel rounded-2xl p-6 w-full max-w-md animate-fade-in"
            onClick={(event) => event.stopPropagation()}
          >
            <div className="flex justify-between items-center mb-6">
              <h2 className="text-xl font-bold text-white">Add New User</h2>
              <button
                onClick={() => setShowAddUser(false)}
                className="p-2 rounded-lg hover:bg-zinc-800 text-zinc-400"
              >
                <X className="h-5 w-5" />
              </button>
            </div>
            <div className="space-y-4">
              <div>
                <label className="text-xs text-zinc-400 uppercase tracking-wider mb-1 block">
                  Full Name
                </label>
                <input
                  type="text"
                  value={newUser.name}
                  onChange={(event) => setNewUser({ ...newUser, name: event.target.value })}
                  placeholder="John Doe"
                  className="w-full px-4 py-3 bg-zinc-900 border border-zinc-800 rounded-xl text-sm text-white placeholder-zinc-500 focus:outline-none focus:border-cyan-500/50"
                />
              </div>
              <div>
                <label className="text-xs text-zinc-400 uppercase tracking-wider mb-1 block">
                  Email
                </label>
                <input
                  type="email"
                  value={newUser.email}
                  onChange={(event) => setNewUser({ ...newUser, email: event.target.value })}
                  placeholder="john@nexuscore.ai"
                  className="w-full px-4 py-3 bg-zinc-900 border border-zinc-800 rounded-xl text-sm text-white placeholder-zinc-500 focus:outline-none focus:border-cyan-500/50"
                />
              </div>
              <div>
                <label className="text-xs text-zinc-400 uppercase tracking-wider mb-1 block">
                  Department
                </label>
                <input
                  type="text"
                  value={newUser.department}
                  onChange={(event) => setNewUser({ ...newUser, department: event.target.value })}
                  placeholder="Engineering"
                  className="w-full px-4 py-3 bg-zinc-900 border border-zinc-800 rounded-xl text-sm text-white placeholder-zinc-500 focus:outline-none focus:border-cyan-500/50"
                />
              </div>
              <div>
                <label className="text-xs text-zinc-400 uppercase tracking-wider mb-1 block">
                  Role Template
                </label>
                <div className="flex flex-wrap gap-2">
                  {roleTemplates.map((template) => (
                    <button
                      key={template.name}
                      onClick={() => setNewUser({ ...newUser, role: template.name })}
                      className={`px-3 py-2 rounded-xl text-xs font-medium border transition-all ${
                        newUser.role === template.name
                          ? 'bg-cyan-500/10 border-cyan-500/30 text-cyan-400'
                          : 'bg-zinc-800 border-transparent text-zinc-500 hover:text-zinc-300'
                      }`}
                    >
                      {template.name}
                    </button>
                  ))}
                </div>
              </div>
              <button
                onClick={addUser}
                disabled={saving || !newUser.name || !newUser.email}
                className="w-full py-3 bg-gradient-to-r from-cyan-500 to-purple-600 rounded-xl text-sm font-bold text-white disabled:opacity-30"
              >
                {saving ? 'Creating User...' : 'Add User'}
              </button>
            </div>
          </div>
        </div>
      )}

      <div className="flex gap-6">
        <div className="w-80 flex-shrink-0">
          <div className="relative mb-4">
            <Search className="absolute left-4 top-1/2 -translate-y-1/2 h-4 w-4 text-zinc-500" />
            <input
              type="text"
              placeholder="Search users..."
              value={searchQuery}
              onChange={(event) => setSearchQuery(event.target.value)}
              className="w-full pl-11 pr-4 py-3 bg-zinc-900/80 border border-zinc-800 rounded-xl text-sm text-white placeholder-zinc-500 focus:outline-none focus:border-cyan-500/50"
            />
          </div>
          <div className="space-y-2 max-h-[600px] overflow-y-auto pr-1">
            {loading && (
              <div className="glass-panel p-4 rounded-2xl text-sm text-zinc-400">
                Loading access directory...
              </div>
            )}
            {!loading &&
              filteredUsers.map((user) => (
                <button
                  key={user.id}
                  onClick={() => setSelectedUserId(user.id)}
                  className={`w-full p-4 rounded-xl flex items-center gap-3 transition-all text-left ${
                    selectedUserId === user.id
                      ? 'bg-cyan-500/10 border border-cyan-500/30'
                      : 'glass-panel hover:border-zinc-600'
                  }`}
                >
                  <div className="h-10 w-10 rounded-full bg-gradient-to-br from-cyan-500/20 to-purple-500/20 flex items-center justify-center text-white text-xs font-bold border border-zinc-700 flex-shrink-0">
                    {user.avatar}
                  </div>
                  <div className="flex-1 min-w-0">
                    <h4 className="text-sm font-medium text-white truncate">{user.name}</h4>
                    <p className="text-[10px] text-zinc-500">{user.role}</p>
                  </div>
                  <div className="flex flex-col items-end gap-1">
                    <span
                      className={`h-2 w-2 rounded-full ${
                        user.status === 'active' ? 'bg-green-500' : 'bg-zinc-600'
                      }`}
                    ></span>
                    <span className="text-[10px] text-zinc-600">{user.permissions.length}</span>
                  </div>
                </button>
              ))}
            {!loading && filteredUsers.length === 0 && (
              <div className="glass-panel p-4 rounded-2xl text-sm text-zinc-400">
                No users matched that search.
              </div>
            )}
          </div>
        </div>

        <div className="flex-1">
          {selectedUser ? (
            <div className="glass-panel p-6 rounded-2xl animate-fade-in">
              <div className="flex items-center justify-between mb-6 gap-4">
                <div className="flex items-center gap-4">
                  <div className="h-14 w-14 rounded-full bg-gradient-to-br from-cyan-500/20 to-purple-500/20 flex items-center justify-center text-white font-bold border border-zinc-700">
                    {selectedUser.avatar}
                  </div>
                  <div>
                    <h2 className="text-xl font-bold text-white">{selectedUser.name}</h2>
                    <p className="text-sm text-zinc-500">
                      {selectedUser.email} • {selectedUser.department}
                    </p>
                  </div>
                </div>
                <div className="flex items-center gap-3">
                  <button
                    onClick={() => toggleStatus(selectedUser.id)}
                    disabled={saving}
                    className="px-3 py-2 rounded-xl border border-zinc-700 text-xs font-semibold text-zinc-300 hover:border-cyan-500/30 hover:text-cyan-300 transition-colors disabled:opacity-50"
                  >
                    Mark as {selectedUser.status === 'active' ? 'Inactive' : 'Active'}
                  </button>
                  <span
                    className={`px-3 py-1 rounded-full text-xs font-bold ${
                      selectedUser.status === 'active'
                        ? 'bg-green-400/10 text-green-400'
                        : 'bg-zinc-700/50 text-zinc-400'
                    }`}
                  >
                    {selectedUser.status}
                  </span>
                </div>
              </div>

              <div className="mb-6">
                <p className="text-xs text-zinc-400 uppercase tracking-wider mb-2">Role Template</p>
                <div className="flex flex-wrap gap-2">
                  {roleTemplates.map((template) => (
                    <button
                      key={template.name}
                      onClick={() => applyTemplate(selectedUser.id, template.name)}
                      disabled={saving}
                      className={`px-3 py-1.5 rounded-lg text-xs font-medium border transition-all ${
                        selectedUser.role === template.name
                          ? 'bg-cyan-500/10 border-cyan-500/30 text-cyan-400'
                          : 'bg-zinc-800 border-transparent text-zinc-500 hover:text-zinc-300'
                      } disabled:opacity-50`}
                    >
                      {template.name} ({template.permissions.length})
                    </button>
                  ))}
                </div>
              </div>

              <div>
                <p className="text-xs text-zinc-400 uppercase tracking-wider mb-3">
                  Module Access ({selectedUser.permissions.length}/{allModules.length})
                </p>
                <div className="space-y-2">
                  {allModules.map((module) => {
                    const hasAccess = selectedUser.permissions.includes(module.id);
                    return (
                      <button
                        key={module.id}
                        type="button"
                        onClick={() => togglePermission(selectedUser.id, module.id)}
                        disabled={saving}
                        className={`w-full flex items-center justify-between p-3 rounded-xl border transition-all ${
                          hasAccess
                            ? 'bg-green-500/5 border-green-500/20 hover:border-green-500/40'
                            : 'bg-zinc-900/50 border-zinc-800 hover:border-zinc-600'
                        } disabled:opacity-60`}
                      >
                        <div className="flex items-center gap-3 text-left">
                          <div
                            className={`h-8 w-8 rounded-lg flex items-center justify-center ${
                              hasAccess
                                ? 'bg-green-500/10 text-green-400'
                                : 'bg-zinc-800 text-zinc-600'
                            }`}
                          >
                            <module.icon className="h-4 w-4" />
                          </div>
                          <div>
                            <h4
                              className={`text-sm font-medium ${
                                hasAccess ? 'text-white' : 'text-zinc-500'
                              }`}
                            >
                              {module.name}
                            </h4>
                            <p className="text-[10px] text-zinc-600">{module.desc}</p>
                          </div>
                        </div>
                        <div
                          className={`h-6 w-11 rounded-full flex items-center transition-all ${
                            hasAccess ? 'bg-green-500 justify-end' : 'bg-zinc-700 justify-start'
                          }`}
                        >
                          <div className="h-5 w-5 bg-white rounded-full mx-0.5 shadow-sm flex items-center justify-center">
                            {hasAccess && <Check className="h-3 w-3 text-green-500" />}
                          </div>
                        </div>
                      </button>
                    );
                  })}
                </div>
              </div>
            </div>
          ) : (
            <div className="glass-panel p-12 rounded-2xl flex flex-col items-center justify-center text-center">
              <Shield className="h-16 w-16 text-zinc-700 mb-4" />
              <h3 className="text-xl font-bold text-zinc-500 mb-2">Select a User</h3>
              <p className="text-sm text-zinc-600">
                Choose a user from the directory to view and manage their module access.
              </p>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
