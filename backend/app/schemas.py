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


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
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


class AgentOut(BaseModel):
    id: str
    name: str
    role: str
    status: str
    successRate: float
    currentTask: str
    avatar: str


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


class ChatRequest(BaseModel):
    agentId: str
    message: str


class ChatResponse(BaseModel):
    agentId: str
    message: str
    invokedTools: list[dict] = Field(default_factory=list)


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
