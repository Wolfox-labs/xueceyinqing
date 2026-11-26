"""
schemas 层 — 项目数据结构定义。

模块：
  resources      → 资源生成输出：MindmapOutput / DocumentOutput / ExerciseOutput / PPTOutput
  learning_path  → 学习路径：PathNode / LearningPath
  profile        → 用户画像：StudentProfile
  classroom      → 虚拟课堂：ClassroomSlide / ClassroomQuiz / ClassroomScript
  api_responses  → API 响应模型：HealthResponse / SessionResponse / MessageResponse / ...
"""
from schemas.resources import (
    MindmapBranch,
    MindmapOutput,
    DocumentSection,
    DocumentOutput,
    ExerciseItem,
    ExerciseOutput,
    PPTSlide,
    PPTOutput,
    QUESTION_TAGS,
    DOCUMENT_TAGS,
    DOCUMENT_TEMPLATE,
    PPT_TAGS,
    PPT_TEMPLATE,
)
from schemas.learning_path import (
    PathNode,
    LearningPath,
)
from schemas.profile import StudentProfile
from schemas.profile_dashboard import (
    ProfileActivity,
    ProfileCard,
    ProfileCardItem,
    ProfileDashboardResponse,
)
from schemas.classroom import (
    ClassroomQuiz,
    ClassroomSlide,
    ClassroomScript,
)
from schemas.adaptive import (
    MasteryStateInput,
    KnowledgeNodeInput,
    EvidenceObservation,
    AdaptiveEvidenceRequest,
    AdaptiveRecommendRequest,
    RecommendationResponse,
    PolicySelectRequest,
    PolicyUpdateRequest,
)
from schemas.assessment import AssessmentResult, AssessmentTask, QuestionItem, AssessGenerateResponse, AnswerItem, AssessSubmitRequest, AssessGenerateRequest
from schemas.api_responses import (
    ChartsResponse,
    ErrorResponse,
    HealthResponse,
    LearningPathResponse,
    MessageResponse,
    ProfileResponse,
    ReportSummaryResponse,
    ReportSuggestionsResponse,
    SessionResponse,
)

__all__ = [
    "MindmapBranch",
    "MindmapOutput",
    "DocumentSection",
    "DocumentOutput",
    "ExerciseItem",
    "ExerciseOutput",
    "PPTSlide",
    "PPTOutput",
    "QUESTION_TAGS",
    "DOCUMENT_TAGS",
    "DOCUMENT_TEMPLATE",
    "PPT_TAGS",
    "PPT_TEMPLATE",
    "PathNode",
    "LearningPath",
    "StudentProfile",
    "ProfileActivity",
    "ProfileCard",
    "ProfileCardItem",
    "ProfileDashboardResponse",
    "ClassroomQuiz",
    "ClassroomSlide",
    "ClassroomScript",
    "MasteryStateInput",
    "KnowledgeNodeInput",
    "EvidenceObservation",
    "AdaptiveEvidenceRequest",
    "AdaptiveRecommendRequest",
    "RecommendationResponse",
    "PolicySelectRequest",
    "PolicyUpdateRequest",
    "AssessmentResult",
    "AssessmentTask",
    "QuestionItem",
    "AssessGenerateResponse",
    "AnswerItem",
    "AssessSubmitRequest",
    "AssessGenerateRequest",
    "ChartsResponse",
    "ErrorResponse",
    "HealthResponse",
    "LearningPathResponse",
    "MessageResponse",
    "ProfileResponse",
    "ReportSummaryResponse",
    "ReportSuggestionsResponse",
    "SessionResponse",
]



