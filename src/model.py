from pydantic import BaseModel

class CacheMessage(BaseModel):
    id: int
    msg: str

class SubmitInput(BaseModel):
    thread_id: str | None = None
    parent_thread_ids: list[str] = []
    base_messages: list[CacheMessage] = []
    msg: str
