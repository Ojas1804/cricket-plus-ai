from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.ai.orchestrator import handle_prompt
from app.database.session import get_session
from app.widgets.schemas import PromptRequest, PromptResponse

router = APIRouter(prefix="/prompts", tags=["prompts"])


@router.post("", response_model=PromptResponse)
def submit_prompt(req: PromptRequest, session: Session = Depends(get_session)) -> PromptResponse:
    return handle_prompt(req, session)
