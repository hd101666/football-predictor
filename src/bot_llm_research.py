"""
Example: use Grok Bot as LLM research step in hybrid predictor.
This script shows the flow; actual Bot calls are done via bot_send_prompt.
"""

import json


def build_research_prompt(home: str, away: str, league: str) -> str:
    return f"""
请研究以下足球比赛，只基于可查证信息，输出严格 JSON（不要其他文字）。

比赛：{home} vs {away}
联赛：{league}

输出格式：
{{
  "home_form": "近5场如 WWDLL",
  "away_form": "近5场",
  "key_absences": ["确定缺阵的核心球员，无则空列表"],
  "news_impact": "none/low/medium/high",
  "suggested_result": "H/D/A",
  "confidence": 0.6,
  "reason": "不超过30字"
}}
"""


def parse_bot_reply(text: str) -> dict:
    """Extract JSON from Bot reply."""
    try:
        start = text.find("{")
        end = text.rfind("}") + 1
        if start >= 0 and end > start:
            return json.loads(text[start:end])
    except Exception:
        pass
    return {"error": "parse_failed", "raw": text[:200]}


# Example usage (to be called from main conversation with bot_send_prompt)
EXAMPLE_MATCHES = [
    ("Arsenal", "Chelsea", "Premier League"),
    ("Bayern Munich", "Dortmund", "Bundesliga"),
    ("Real Madrid", "Barcelona", "La Liga"),
]


if __name__ == "__main__":
    for home, away, league in EXAMPLE_MATCHES:
        print("---")
        print(build_research_prompt(home, away, league))
        print()
