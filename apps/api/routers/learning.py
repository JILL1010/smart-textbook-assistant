from datetime import datetime
import json

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import update
from sqlalchemy.orm import Session

from db import get_db
from models.chapter import Chapter
from models.learning import StudyProgress, QuizAttempt, ReviewItem
from services.learning import quiz_token, serialize_attempt

router = APIRouter()
CHAPTER_PATH = "/textbooks/{textbook_id}/chapters/{chapter_id}"


def get_chapter(db, textbook_id, chapter_id):
    chapter = db.query(Chapter).filter(Chapter.id == chapter_id, Chapter.textbook_id == textbook_id).first()
    if not chapter:
        raise HTTPException(404, "章节不存在")
    return chapter


def progress_for(db, chapter_id):
    progress = db.get(StudyProgress, chapter_id)
    if not progress:
        progress = StudyProgress(chapter_id=chapter_id, read_completed=False, draft_seq=0)
        db.add(progress)
    return progress


def guard_quiz(db, chapter, token):
    if not chapter.quiz_data or quiz_token(chapter.quiz_data) != token:
        raise HTTPException(409, "练习题已更新，请刷新后重新作答")
    result = db.execute(update(Chapter).where(
        Chapter.id == chapter.id, Chapter.generation_revision == chapter.generation_revision,
        Chapter.quiz_data == chapter.quiz_data,
    ).values(generation_revision=chapter.generation_revision))
    if result.rowcount != 1:
        db.rollback()
        raise HTTPException(409, "章节已更新，请刷新后重新作答")


@router.get(CHAPTER_PATH + "/learning")
def learning_summary(textbook_id: int, chapter_id: int, db: Session = Depends(get_db)):
    chapter = get_chapter(db, textbook_id, chapter_id)
    token = quiz_token(chapter.quiz_data)
    progress = db.get(StudyProgress, chapter_id)
    attempts = db.query(QuizAttempt).filter(QuizAttempt.chapter_id == chapter_id).order_by(QuizAttempt.id.desc()).limit(20).all()
    current = next((item for item in attempts if item.quiz_token == token and item.generation_revision == chapter.generation_revision), None)
    draft = {"answers": json.loads(progress.draft_answers), "quiz_token": token} if progress and progress.draft_token == token and progress.draft_answers else None
    pending = db.query(ReviewItem).filter(ReviewItem.chapter_id == chapter_id, ReviewItem.resolved.is_(False)).count()
    return {"read_completed": bool(progress and progress.read_completed), "draft": draft,
            "current_attempt": serialize_attempt(current) if current else None,
            "attempts": [serialize_attempt(item) for item in attempts], "pending_reviews": pending}


class ReadRequest(BaseModel):
    read_completed: bool


@router.post(CHAPTER_PATH + "/learning/read")
def mark_read(textbook_id: int, chapter_id: int, body: ReadRequest, db: Session = Depends(get_db)):
    get_chapter(db, textbook_id, chapter_id)
    progress = progress_for(db, chapter_id)
    progress.read_completed = body.read_completed
    db.commit()
    return {"read_completed": progress.read_completed}


class DraftRequest(BaseModel):
    quiz_token: str
    answers: dict[int, int]
    sequence: int = Field(ge=0, default=0)


@router.post(CHAPTER_PATH + "/quiz/draft")
def save_draft(textbook_id: int, chapter_id: int, body: DraftRequest, db: Session = Depends(get_db)):
    chapter = get_chapter(db, textbook_id, chapter_id)
    guard_quiz(db, chapter, body.quiz_token)
    questions = json.loads(chapter.quiz_data)
    if any(index < 0 or index >= len(questions) or answer < 0 or answer > 3 for index, answer in body.answers.items()):
        raise HTTPException(400, "作答选项无效")
    progress = progress_for(db, chapter_id)
    if body.sequence < progress.draft_seq:
        db.rollback()
        return {"status": "superseded"}
    progress.draft_token = body.quiz_token
    progress.draft_answers = json.dumps(body.answers)
    progress.draft_seq = body.sequence
    db.commit()
    return {"status": "saved"}


class SubmitRequest(BaseModel):
    quiz_token: str
    answers: list[int]
    sequence: int = Field(ge=0, default=0)


@router.post(CHAPTER_PATH + "/quiz/submit")
def submit_quiz(textbook_id: int, chapter_id: int, body: SubmitRequest, db: Session = Depends(get_db)):
    chapter = get_chapter(db, textbook_id, chapter_id)
    guard_quiz(db, chapter, body.quiz_token)
    questions = json.loads(chapter.quiz_data)
    if len(body.answers) != len(questions) or any(answer < 0 or answer > 3 for answer in body.answers):
        raise HTTPException(400, "请完成全部题目后提交")
    if any(type(question.get("answer")) is not int or not 0 <= question["answer"] <= 3 for question in questions):
        raise HTTPException(400, "题目答案数据无效，请重新生成练习")
    correct = sum(answer == question["answer"] for answer, question in zip(body.answers, questions))
    attempt = QuizAttempt(chapter_id=chapter_id, generation_revision=chapter.generation_revision,
                          quiz_token=body.quiz_token, quiz_snapshot=chapter.quiz_data,
                          answers=json.dumps(body.answers), correct=correct, total=len(questions))
    db.add(attempt)
    for index, (answer, question) in enumerate(zip(body.answers, questions)):
        if answer == question["answer"]:
            continue
        item = db.query(ReviewItem).filter_by(chapter_id=chapter_id, quiz_token=body.quiz_token, question_index=index).first()
        if item:
            item.selected_answer, item.resolved = answer, False
        else:
            db.add(ReviewItem(chapter_id=chapter_id, quiz_token=body.quiz_token, question_index=index,
                              question_snapshot=json.dumps(question, ensure_ascii=False), selected_answer=answer))
    progress = progress_for(db, chapter_id)
    progress.draft_answers, progress.draft_token = None, None
    progress.draft_seq = max(progress.draft_seq, body.sequence)
    db.commit()
    return serialize_attempt(attempt)


@router.get("/textbooks/{textbook_id}/reviews")
def list_reviews(textbook_id: int, db: Session = Depends(get_db)):
    rows = db.query(ReviewItem, Chapter).join(Chapter, ReviewItem.chapter_id == Chapter.id).filter(Chapter.textbook_id == textbook_id).order_by(ReviewItem.resolved, ReviewItem.id.desc()).all()
    return [{"id": item.id, "chapter_id": chapter.id, "chapter_title": chapter.title,
             "question": json.loads(item.question_snapshot), "selected_answer": item.selected_answer,
             "resolved": item.resolved, "review_count": item.review_count} for item, chapter in rows]


class ReviewRequest(BaseModel):
    answer: int = Field(ge=0, le=3)


@router.post("/textbooks/{textbook_id}/reviews/{review_id}")
def review_question(textbook_id: int, review_id: int, body: ReviewRequest, db: Session = Depends(get_db)):
    item = db.query(ReviewItem).join(Chapter, Chapter.id == ReviewItem.chapter_id).filter(Chapter.textbook_id == textbook_id, ReviewItem.id == review_id).first()
    if not item:
        raise HTTPException(404, "错题不存在")
    question = json.loads(item.question_snapshot)
    item.resolved = body.answer == question["answer"]
    item.review_count += 1
    item.last_reviewed_at = datetime.now()
    db.commit()
    return {"correct": item.resolved, "explanation": question.get("explanation", ""), "answer": question["answer"]}
