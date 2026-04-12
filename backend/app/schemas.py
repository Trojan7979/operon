from pydantic import BaseModel, ConfigDict, Field


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class UserOut(ORMModel):
    id: str
    name: str
    email: str
    role: str
    avatar: str
    status: str
    department: str
    permissions: list[str]


class LoginRequest(BaseModel):
    email: str
    password: str


class RegisterRequest(BaseModel):
    name: str
    email: str
    password: str = Field(min_length=8)
    role: str
    department: str = "General"


class RefreshTokenRequest(BaseModel):
    refreshToken: str


class LogoutRequest(BaseModel):
    refreshToken: str | None = None


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    refreshToken: str | None = None
    user: UserOut


class WorkflowStepOut(BaseModel):
    id: int
    name: str
    agent: str
    status: str
    time: str
    detail: str | None = None
    reasoning: str | None = None
    confidence: float | None = None
    duration: int | None = None
    alternatives: list[str] = Field(default_factory=list)
    canFail: bool = False
    failureScenario: dict | None = None


class WorkflowOut(BaseModel):
    id: str
    type: str
    name: str
    status: str
    health: int
    progress: int
    currentStep: str | None = None
    assignedAgent: str | None = None
    prediction: str | None = None
    autoAction: str | None = None
    steps: list[WorkflowStepOut] = Field(default_factory=list)


class WorkflowStepCreate(BaseModel):
    name: str
    agent: str
    status: str = "pending"
    detail: str | None = None


class CreateWorkflowRequest(BaseModel):
    type: str
    name: str
    assignedAgent: str | None = None
    prediction: str | None = None
    steps: list[WorkflowStepCreate] = Field(default_factory=list)


class UpdateWorkflowRequest(BaseModel):
    name: str | None = None
    status: str | None = None
    health: int | None = Field(default=None, ge=0, le=100)
    progress: int | None = Field(default=None, ge=0, le=100)
    currentStep: str | None = None
    assignedAgent: str | None = None
    prediction: str | None = None
    autoAction: str | None = None


class RetryWorkflowRequest(BaseModel):
    note: str | None = None


class EscalateWorkflowRequest(BaseModel):
    note: str = Field(min_length=3, max_length=255)
    escalateTo: str | None = None


class AgentOut(BaseModel):
    id: str
    name: str
    role: str
    status: str
    successRate: float
    currentTask: str
    avatar: str


class AgentMetricsOut(BaseModel):
    agentId: str
    totalRuns: int
    completedRuns: int
    failedRuns: int
    activeTasks: int
    averageDurationMs: int
    toolInvocations: int
    successRate: float


class AgentHistoryEntryOut(BaseModel):
    id: str
    entryType: str
    status: str
    summary: str
    createdAt: str


class AgentTaskOut(BaseModel):
    id: str
    title: str
    description: str
    status: str
    priority: str
    assignedAgentId: str
    workflowId: str | None = None
    conversationId: str | None = None
    createdAt: str
    updatedAt: str


class AssignAgentTaskRequest(BaseModel):
    title: str
    description: str
    priority: str = "normal"
    workflowId: str | None = None
    conversationId: str | None = None


class AuditLogOut(BaseModel):
    id: str
    time: str
    type: str
    agent: str
    message: str


class DashboardMetricsOut(BaseModel):
    activeWorkflows: int
    tasksAutomated: int
    humanEscalations: int
    selfCorrections: int
    uptime: str
    autonomyRate: str


class ToolConnectionOut(BaseModel):
    id: str
    name: str
    toolType: str
    description: str
    status: str
    mcpServer: str
    capabilities: list[str]


class DashboardOverview(BaseModel):
    systemMetrics: DashboardMetricsOut
    agents: list[AgentOut]
    workflows: list[WorkflowOut]
    auditLogs: list[AuditLogOut]
    connectedTools: list[ToolConnectionOut]


class ConversationMessageOut(BaseModel):
    id: str
    role: str
    senderName: str
    agentId: str | None = None
    content: str
    createdAt: str


class ConversationOut(BaseModel):
    id: str
    title: str
    status: str
    ownerUserId: str
    primaryAgentId: str | None = None
    workflowId: str | None = None
    lastMessageAt: str
    createdAt: str
    messages: list[ConversationMessageOut] = Field(default_factory=list)


class ChatRequest(BaseModel):
    agentId: str = "orchestrator"
    message: str
    conversationId: str | None = None


class ChatResponse(BaseModel):
    agentId: str
    conversationId: str
    message: str
    invokedTools: list[dict] = Field(default_factory=list)
    collaboration: list[dict] = Field(default_factory=list)
    workflowId: str | None = None
    routeAction: dict | None = None


class MeetingLineOut(BaseModel):
    time: str
    speaker: str
    text: str


class MeetingItemOut(BaseModel):
    type: str
    text: str
    owner: str
    status: str
    deadline: str | None = None
    daysLeft: int | None = None


class MeetingOut(BaseModel):
    id: str
    title: str
    provider: str
    date: str
    time: str
    duration: str
    attendees: list[str]
    status: str
    agentJoined: bool
    agentName: str | None = None
    transcript: list[MeetingLineOut] = Field(default_factory=list)
    extracted: list[MeetingItemOut] = Field(default_factory=list)


class ScheduleMeetingRequest(BaseModel):
    title: str
    provider: str
    date: str
    time: str
    attendees: list[str] = Field(default_factory=list)
    agentJoin: bool = True


class EmployeeOut(BaseModel):
    id: str
    name: str
    role: str
    department: str
    email: str
    phone: str
    location: str
    startDate: str
    status: str
    progress: int
    avatar: str
    photo: str | None = None


class CreateEmployeeRequest(BaseModel):
    name: str
    role: str
    department: str
    email: str
    phone: str = ""
    location: str = ""
    startDate: str
    photoUrl: str | None = None


class WorkflowExecutionResponse(BaseModel):
    workflow: WorkflowOut
    invokedTools: list[dict] = Field(default_factory=list)
    newLogs: list[AuditLogOut] = Field(default_factory=list)


class LlmProbeRequest(BaseModel):
    prompt: str = Field(min_length=1, max_length=240)
    maxOutputTokens: int = Field(default=96, ge=32, le=256)
    temperature: float = Field(default=0.2, ge=0, le=1)


class LlmProbeResponse(BaseModel):
    model: str
    text: str
    promptChars: int
    maxOutputTokens: int
    temperature: float
    usedFallback: bool = False


class SlaRecordOut(BaseModel):
    id: str
    name: str
    type: str
    slaHours: float
    elapsedHours: float
    status: str
    currentStep: str
    agent: str
    prediction: str
    health: int
    autoAction: str | None = None


class BottleneckOut(BaseModel):
    area: str
    avgDelay: str
    frequency: str
    risk: str
    suggestion: str


class SlaOverview(BaseModel):
    summary: dict
    workflows: list[SlaRecordOut]
    bottlenecks: list[BottleneckOut]


class CreateUserRequest(BaseModel):
    name: str
    email: str
    role: str
    department: str = "General"


class UpdateUserAccessRequest(BaseModel):
    role: str | None = None
    permissions: list[str] | None = None
    status: str | None = None


class ToolInvokeRequest(BaseModel):
    toolName: str
    action: str
    payload: dict = Field(default_factory=dict)


class ToolConnectionActionResponse(BaseModel):
    tool: ToolConnectionOut
    message: str


class WorkflowAnalyticsOut(BaseModel):
    total: int
    byStatus: dict[str, int]
    avgProgress: int
    activeWorkflowIds: list[str] = Field(default_factory=list)
