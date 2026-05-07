"""
Question Engine — auto-generate mining quiz questions
- Built-in: math, logic, pattern recognition (works offline)
- LLM: OpenAI API for richer questions (optional, needs OPENAI_API_KEY)
"""
import os, random, re, math, json
import urllib.request

# ─── Difficulty tiers ───

DIFFICULTIES = {
    1: {"name": "Easy",   "time_limit": 30, "reward": 0.01,  "accuracy_bonus": 0.005},
    2: {"name": "Medium", "time_limit": 25, "reward": 0.025, "accuracy_bonus": 0.01},
    3: {"name": "Hard",   "time_limit": 20, "reward": 0.05,  "accuracy_bonus": 0.02},
}

# ═══════════════════════════════════════
#  BUILT-IN QUESTION GENERATORS
# ═══════════════════════════════════════

def gen_basic_math(difficulty=1):
    """Arithmetic questions"""
    if difficulty == 1:
        a, b = random.randint(10,99), random.randint(10,99)
        op = random.choice(['+','-'])
        if op == '-': a, b = max(a,b), min(a,b)
    elif difficulty == 2:
        a, b = random.randint(2,20), random.randint(2,20)
        op = random.choice(['+','-','×'])
    else:
        a, b = random.randint(10,50), random.randint(2,15)
        op = random.choice(['×','÷'])
        if op == '÷':
            a = a * b  # ensure clean division

    if op == '+': ans = a + b
    elif op == '-': ans = a - b
    elif op == '×': ans = a * b
    elif op == '÷': ans = a // b

    return {
        "question": f"What is {a} {op} {b}?",
        "answer": str(ans),
        "type": "math",
        "options": None,
    }


def gen_pattern(difficulty=1):
    """Number pattern completion"""
    start = random.randint(1, 10)
    if difficulty == 1:
        step = random.randint(2, 5)
        seq = [start + i * step for i in range(4)]
        answer = start + 4 * step
        hint = f"Arithmetic sequence (+{step})"
    elif difficulty == 2:
        step = random.choice([-3, -2, 2, 3, 5])
        seq = [start + i * step for i in range(5)]
        answer = start + 5 * step
        hint = f"Sequence ({'+' if step > 0 else ''}{step})"
    else:
        mult = random.choice([2, 3, 4])
        seq = [start * (mult ** i) for i in range(4)]
        answer = start * (mult ** 4)
        hint = f"Geometric sequence (×{mult})"

    display = ", ".join(str(x) for x in seq) + ", ?"
    return {
        "question": f"Complete the pattern: {display}",
        "answer": str(answer),
        "type": "pattern",
        "options": None,
    }


def gen_logic(difficulty=1):
    """Logic / reasoning"""
    problems = []

    if difficulty == 1:
        # Simple if-then
        a = random.randint(1, 20)
        b = random.randint(1, 20)
        c = a + b
        problems = [
            {
                "question": f"If {a} + {b} = {c}, what is {c} - {b}?",
                "answer": str(a),
                "type": "logic",
            },
        ]
    elif difficulty == 2:
        # Order of operations
        a, b, c = random.randint(2, 15), random.randint(2, 15), random.randint(2, 15)
        # (a + b) * c
        ans = (a + b) * c
        problems = [
            {
                "question": f"What is ({a} + {b}) × {c}?",
                "answer": str(ans),
                "type": "logic",
            },
        ]
    else:
        # Pythagorean / exponents
        base = random.randint(2, 12)
        exp = random.choice([2, 3])
        ans = base ** exp
        problems = [
            {
                "question": f"What is {base}^{exp} ({base} raised to power {exp})?",
                "answer": str(ans),
                "type": "logic",
            },
        ]

    return problems[0] if problems else gen_basic_math(difficulty)


def gen_word_math(difficulty=1):
    """Word problem math"""
    if difficulty == 1:
        a, b = random.randint(5, 50), random.randint(5, 50)
        return {
            "question": f"A miner found {a} blocks in the morning and {b} blocks in the afternoon. How many blocks total?",
            "answer": str(a + b),
            "type": "word_math",
        }
    elif difficulty == 2:
        price = random.randint(2, 10)
        qty = random.randint(3, 15)
        return {
            "question": f"If SLAM costs {price} gwei each and you buy {qty}, how much total (in gwei)?",
            "answer": str(price * qty),
            "type": "word_math",
        }
    else:
        rate = random.randint(10, 50)
        hours = random.randint(2, 8)
        return {
            "question": f"A miner mines at {rate} H/s for {hours} hours. How many hashes total? (just the number)",
            "answer": str(rate * hours * 3600),
            "type": "word_math",
        }


def gen_binary(difficulty=1):
    """Binary/decimal conversion"""
    if difficulty == 1:
        num = random.randint(1, 31)
        return {
            "question": f"What is {num} in binary? (just the bits, e.g. 101)",
            "answer": bin(num)[2:],
            "type": "binary",
        }
    elif difficulty == 2:
        num = random.randint(32, 127)
        return {
            "question": f"Convert decimal {num} to binary:",
            "answer": bin(num)[2:],
            "type": "binary",
        }
    else:
        bits = format(random.randint(8, 255), '08b')
        num = int(bits, 2)
        return {
            "question": f"What decimal is binary {bits}?",
            "answer": str(num),
            "type": "binary",
        }


# ─── Generator pool ───

BUILTIN_GENERATORS = [
    gen_basic_math,
    gen_pattern,
    gen_logic,
    gen_word_math,
    gen_binary,
]


def generate_builtin_question(difficulty=1):
    """Pick random generator and produce a question"""
    gen = random.choice(BUILTIN_GENERATORS)
    return gen(min(difficulty, 3))


# ═══════════════════════════════════════
#  LLM QUESTION GENERATOR (OpenAI)
# ═══════════════════════════════════════

OPENAI_KEY = os.getenv("OPENAI_API_KEY", "")
LLM_MODEL = os.getenv("LLM_MODEL", "gpt-4o-mini")

LLM_PROMPT = """You are a mining quiz bot for a crypto mining game on Base L2.

Generate ONE short trivia/quiz question suitable for difficulty level {difficulty}.
- Level 1 (Easy): Basic math, simple trivia
- Level 2 (Medium): Harder math, crypto knowledge, logic puzzles
- Level 3 (Hard): Advanced math, blockchain concepts, complex reasoning

IMPORTANT: Return ONLY valid JSON, no markdown, no explanation:
{{"question": "...", "answer": "...", "type": "..."}}

Where:
- "question": the question text (short, clear)
- "answer": the correct answer (a short string or number)
- "type": one of: "trivia", "crypto", "math", "riddle"

Do NOT include options. Just the question and answer. Make sure the answer is unambiguous.
"""


def generate_llm_question(difficulty=1):
    """Use OpenAI API to generate a question"""
    if not OPENAI_KEY:
        return None

    try:
        prompt = LLM_PROMPT.format(difficulty=difficulty)
        data = json.dumps({
            "model": LLM_MODEL,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.9,
            "max_tokens": 200,
        }).encode()

        req = urllib.request.Request(
            "https://api.openai.com/v1/chat/completions",
            data=data,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {OPENAI_KEY}",
            },
        )

        with urllib.request.urlopen(req, timeout=15) as resp:
            result = json.loads(resp.read())

        content = result["choices"][0]["message"]["content"].strip()
        # Try to parse JSON from response
        content = re.sub(r"```json\s*|```", "", content).strip()
        parsed = json.loads(content)

        if "question" in parsed and "answer" in parsed:
            parsed["type"] = parsed.get("type", "llm")
            parsed["options"] = None
            return parsed

    except Exception as e:
        print(f"⚠️ LLM question gen failed: {e}")

    return None


# ═══════════════════════════════════════
#  MAIN QUESTION FACTORY
# ═══════════════════════════════════════

def generate_question(difficulty=1, use_llm=True):
    """
    Generate a mining question.
    Tries LLM first (if OPENAI_API_KEY set), falls back to built-in.
    """
    if use_llm and OPENAI_KEY:
        q = generate_llm_question(difficulty)
        if q:
            return q

    return generate_builtin_question(difficulty)


def verify_answer(question: str, user_answer: str, correct_answer: str) -> bool:
    """Verify answer with tolerance for formatting differences"""
    u = user_answer.strip().lower()
    c = correct_answer.strip().lower()

    if u == c:
        return True

    # Numeric comparison with tolerance
    try:
        if abs(float(u) - float(c)) < 0.01:
            return True
    except ValueError:
        pass

    # Remove commas and spaces
    u_clean = u.replace(",", "").replace(" ", "")
    c_clean = c.replace(",", "").replace(" ", "")
    if u_clean == c_clean:
        return True

    return False


def get_difficulty_config(difficulty=1):
    return DIFFICULTIES.get(min(difficulty, 3), DIFFICULTIES[1])
