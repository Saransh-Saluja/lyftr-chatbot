from pydantic import BaseModel, field_validator


class ChatRequest(BaseModel):
    session_id: str
    message: str
    system_prompt: str | None = None

    @field_validator("session_id")
    @classmethod
    def _session_id(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("session_id must not be blank")
        if len(v) > 128:
            raise ValueError("session_id must be at most 128 characters")
        return v

    @field_validator("message")
    @classmethod
    def _message(cls, v: str) -> str:
        # Length is checked AFTER trimming, as the contract says.
        v = v.strip()
        if not 1 <= len(v) <= 4000:
            raise ValueError("message must be 1-4000 characters after trimming")
        return v

    @field_validator("system_prompt")
    @classmethod
    def _system_prompt(cls, v: str | None) -> str | None:
        if v is None:
            return None
        v = v.strip()
        if len(v) > 4000:
            raise ValueError("system_prompt must be at most 4000 characters")
        return v or None  # blank means "not provided"


class ChatMetadata(BaseModel):
    resolution_source: str
    model: str
    latency_ms: int
    input_tokens: int
    output_tokens: int
    key_id: str | None
    fallback_attempts: int


class ChatResponse(BaseModel):
    session_id: str
    reply: str
    metadata: ChatMetadata
