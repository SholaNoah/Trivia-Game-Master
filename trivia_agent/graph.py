import html
import random 
import requests 
import operator
from typing import Annotated
from typing import TypedDict, Optional
from langgraph.types import interrupt
from langgraph.graph import StateGraph, START, END
from langchain_google_genai import ChatGoogleGenerativeAI

llm = ChatGoogleGenerativeAI(model="gemini-3.5-flash", temperature=0.9)


class TriviaState(TypedDict):
    difficulty: str          # "easy" | "medium" | "hard"
    streak: int               # consecutive correct answers
    misses_in_a_row: int      # consecutive wrong answers
    score: int
    round_num: int
    max_rounds: int
    current_question: Optional[dict]   # the question object from the API
    player_answer: Optional[str]
    last_result: Optional[str]         # "correct" | "incorrect"
    commentary: Optional[str]          # live commentary from the host
    recap: Optional[str]              # final recap from the host
    history: Annotated[list, operator.add]
    cash: int


def init(state: TriviaState) -> dict:
    return {
        "streak": state.get("streak") or 0,
        "misses_in_a_row": state.get("misses_in_a_row") or 0,
        "score": state.get("score") or 0,
        "round_num": state.get("round_num") or 1,
        "max_rounds": state.get("max_rounds") or 5,
        "difficulty": state.get("difficulty") or "easy",
        "history": state.get("history") or [],
        "cash": state.get("cash") or 0,
    }


def get_question(state: TriviaState) -> dict:
    resp = requests.get(
        "https://opentdb.com/api.php",
        params={"amount": 1, "difficulty": state["difficulty"], "type": "multiple"},
    )
    resp.raise_for_status()
    data = resp.json()["results"][0]

    question_text = html.unescape(data["question"])
    correct = html.unescape(data["correct_answer"])
    incorrect = [html.unescape(a) for a in data["incorrect_answers"]]

    options = incorrect + [correct]
    random.shuffle(options)

    return {
        "current_question": {
            "category": data["category"],
            "question": question_text,
            "options": options,
            "correct_answer": correct,
        }
    }



def get_answer(state: TriviaState) -> dict:
    q = state["current_question"]
    options_text = "\n".join(f"{i+1}. {opt}" for i, opt in enumerate(q["options"]))

    choice = interrupt(f"{q['question']}\n\n{options_text}\n\nYour answer (1-4, or 'hint'):")

    if isinstance(choice, str) and choice.strip().lower() == "hint":
        hint_prompt = (
            f"Question: {q['question']}\n"
            f"Correct answer: {q['correct_answer']}\n"
            "Write a one-sentence hint that nudges toward the answer without giving it away directly."
        )
        hint_response = llm.invoke(hint_prompt)
        hint_text = hint_response.content
        if isinstance(hint_text, list):
            hint_text = "".join(p.get("text", "") for p in hint_text if isinstance(p, dict))

        choice = interrupt(f"Hint: {hint_text}\n\n{options_text}\n\nYour answer (1-4):")

    try:
        idx = int(choice) - 1
        chosen = q["options"][idx] if 0 <= idx <= 3 else None
    except (ValueError, TypeError, IndexError):
        chosen = None

    is_correct = chosen == q["correct_answer"]
    payout = {"easy": 500, "medium": 1000, "hard": 2000}[state["difficulty"]]
    current_cash = state.get("cash", 0)
    updates = {
        "player_answer": chosen,
        "last_result": "correct" if is_correct else "incorrect",
    }
    if is_correct:
        updates["score"] = state.get("score", 0) + 1
        updates["streak"] = state.get("streak", 0) + 1
        updates["misses_in_a_row"] = 0
        updates["cash"] = current_cash + payout
    else:
        updates["streak"] = 0
        updates["misses_in_a_row"] = state.get("misses_in_a_row", 0) + 1
        updates["cash"] = current_cash // 2

        updates["history"] = [{"category": q["category"], "correct": is_correct, "cash": updates["cash"]}]

    return updates


def advance_round(state: TriviaState) -> dict:
    difficulty = state["difficulty"]
    streak = state.get("streak", 0)
    misses = state.get("misses_in_a_row", 0)

    if streak >= 2:
        difficulty = {"easy": "medium", "medium": "hard", "hard": "hard"}[difficulty]
    elif misses >= 2:
        difficulty = {"hard": "medium", "medium": "easy", "easy": "easy"}[difficulty]

    return {
        "round_num": state["round_num"] + 1,
        "difficulty": difficulty,
    }


def route_after_round(state: TriviaState) -> str:
    if state["round_num"] > state["max_rounds"]:
        return "done"
    return "continue"


def commentary(state: TriviaState) -> dict:
    q = state["current_question"]
    cash = state.get("cash", 0)

    if state["last_result"] == "correct":
        payout = {"easy": 500, "medium": 1000, "hard": 2000}[state["difficulty"]]
        cash_note = f"They just won ${payout}, bringing their total to ${cash}."
    else:
        cash_note = f"Getting it wrong halved their cash, now down to ${cash}."

    prompt = (
        "You are an enthusiastic game show host reacting live to a trivia answer. "
        f"Question: {q['question']}\n"
        f"Player answered: {state['player_answer']}\n"
        f"Correct answer: {q['correct_answer']}\n"
        f"Result: {state['last_result']}\n"
        f"Current streak: {state.get('streak', 0)}\n"
        f"{cash_note}\n"
        "Write 1-2 punchy sentences of live commentary that naturally mentions the cash change. "
        "Host tone only, nothing else."
    )
    response = llm.invoke(prompt)
    text = response.content
    if isinstance(text, list):
        text = "".join(p.get("text", "") for p in text if isinstance(p, dict))
    return {"commentary": text}

def recap(state: TriviaState) -> dict:
    history = state.get("history", [])
    total = len(history)
    correct = sum(1 for h in history if h["correct"])

    by_category = {}
    for h in history:
        stats = by_category.setdefault(h["category"], {"correct": 0, "total": 0})
        stats["total"] += 1
        if h["correct"]:
            stats["correct"] += 1

    category_lines = "\n".join(
        f"- {cat}: {s['correct']}/{s['total']}" for cat, s in by_category.items()
    )

    prompt = (
        "You are a game show host wrapping up a trivia game. "
        f"Final score: {correct}/{total} correct.\n"
        f"Category breakdown:\n{category_lines}\n"
        "Write a short, warm recap (3-4 sentences): overall performance, "
        "and call out their strongest and weakest categories by name."
    )
    response = llm.invoke(prompt)
    text = response.content
    if isinstance(text, list):
        text = "".join(p.get("text", "") for p in text if isinstance(p, dict))
    return {"recap": text}

builder = StateGraph(TriviaState)

builder.add_node("init", init)
builder.add_node("get_question", get_question)
builder.add_node("get_answer", get_answer)
builder.add_node("advance_round", advance_round)
builder.add_node("commentary", commentary)
builder.add_node("recap", recap)

builder.add_edge(START, "init")
builder.add_edge("init", "get_question")
builder.add_edge("get_question", "get_answer")
builder.add_edge("get_answer", "commentary")
builder.add_edge("commentary", "advance_round")
builder.add_conditional_edges(
    "advance_round",
    route_after_round,
    {"continue": "get_question", "done": "recap"},
)
builder.add_edge("recap", END)

graph = builder.compile()