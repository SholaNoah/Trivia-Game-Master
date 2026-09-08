# Trivia Game Master

A LangGraph agent that runs a full trivia game show — pulling questions from the Open Trivia DB, tracking score/streaks, adjusting difficulty on the fly, and using Gemini to generate hints, host commentary, and an end-of-game recap.

## How it works

The game runs as a LangGraph `StateGraph`:

```
init → get_question → get_answer → commentary → advance_round → (loop back to get_question, or → recap → END)
```

- **get_question** — pulls a question from the [Open Trivia DB](https://opentdb.com/) API (no key required) based on the current difficulty level
- **get_answer** — waits for the player's answer (interrupt-based), supports hint requests, and updates score, streak, and miss count in graph state
- **commentary** — Gemini generates game-show-host style commentary reacting to the answer and the cash swing
- **advance_round** — difficulty scales up on a strong streak and eases off after a couple of misses; routes back into another round or on to the recap once the round limit (or a player quit) is reached
- **recap** — Gemini writes a short summary of the player's performance, calling out strong and weak categories

 <img width="607" height="482" alt="LangGraph Trivia agent" src="https://github.com/user-attachments/assets/9a042ae5-2130-4027-91c2-23e7f1783178" />


### Cash mechanic

Correct answers pay out based on difficulty — easy $500, medium $1,000, hard $2,000 — and a wrong answer halves the player's current cash. Commentary and the recap both reference the cash swing, not just right/wrong.

## Tech stack

- **LangGraph** — game state machine and orchestration
- **Gemini** — hints, commentary, and recap generation
- **Open Trivia DB API** — question source, free, no API key needed

## Running it locally

```bash
python -m venv trivia-env
trivia-env\Scripts\Activate.ps1   # Windows PowerShell
pip install -r requirements.txt
```

Create a `.env` file in the project root with your own Gemini key:

```
GOOGLE_API_KEY=your_key_here
```

Then run it in LangGraph Studio:

```bash
python -m langgraph_cli dev
```

This opens a local LangGraph Studio session where you can play through a full game via the visual interface. (If you're on a locked-down network/Windows Application Control policy, `python -m langgraph_cli dev` is the more reliable way to launch it over the plain `langgraph` command.)

## Frontend

A player-facing frontend ("Trivia Showdown") was built separately in Lovable, connecting to this backend over a live tunnel. That frontend code isn't included in this repo — this is the backend/agent only.

## Notes

- Built as an assigned project during my IT placement, to get hands-on with LangGraph state graphs, branching logic, and LLM-generated content beyond a simple chatbot.
- The Gemini free tier has a daily request quota — if hints/commentary/recap start failing, you've likely hit it.
