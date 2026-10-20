"""
Chinese to English team name mapping for major European clubs.
"""

TEAM_MAP = {
    # Premier League
    "阿森纳": "Arsenal",
    "切尔西": "Chelsea",
    "曼联": "Man United",
    "曼彻斯特联": "Man United",
    "热刺": "Tottenham",
    "托特纳姆热刺": "Tottenham",
    "利物浦": "Liverpool",
    "曼城": "Man City",
    "曼彻斯特城": "Man City",
    "纽卡斯尔": "Newcastle",
    "富勒姆": "Fulham",
    "埃弗顿": "Everton",
    "布莱顿": "Brighton",
    "西汉姆": "West Ham",
    "阿斯顿维拉": "Aston Villa",
    "水晶宫": "Crystal Palace",
    "伯恩茅斯": "Bournemouth",
    "诺丁汉森林": "Nott'm Forest",
    "狼队": "Wolves",
    "布伦特福德": "Brentford",
    # La Liga
    "皇家马德里": "Real Madrid",
    "皇马": "Real Madrid",
    "巴塞罗那": "Barcelona",
    "巴萨": "Barcelona",
    "马德里竞技": "Ath Madrid",
    "马竞": "Ath Madrid",
    "塞维利亚": "Sevilla",
    "皇家社会": "Sociedad",
    "比利亚雷亚尔": "Villarreal",
    "贝蒂斯": "Betis",
    "毕尔巴鄂": "Ath Bilbao",
    # Serie A
    "国际米兰": "Inter",
    "国米": "Inter",
    "AC米兰": "Milan",
    "米兰": "Milan",
    "尤文图斯": "Juventus",
    "尤文": "Juventus",
    "那不勒斯": "Napoli",
    "罗马": "Roma",
    "拉齐奥": "Lazio",
    "亚特兰大": "Atalanta",
    "佛罗伦萨": "Fiorentina",
    # Bundesliga
    "拜仁慕尼黑": "Bayern Munich",
    "拜仁": "Bayern Munich",
    "多特蒙德": "Dortmund",
    "多特": "Dortmund",
    "勒沃库森": "Leverkusen",
    "莱比锡红牛": "RB Leipzig",
    "莱比锡": "RB Leipzig",
    "法兰克福": "Ein Frankfurt",
    "沃尔夫斯堡": "Wolfsburg",
    "门兴": "M'gladbach",
    # Ligue 1
    "巴黎圣日耳曼": "Paris SG",
    "巴黎": "Paris SG",
    "马赛": "Marseille",
    "摩纳哥": "Monaco",
    "里昂": "Lyon",
    "里尔": "Lille",
    "尼斯": "Nice",
    "雷恩": "Rennes",
}


def cn_to_en(name: str) -> str:
    """Convert Chinese team name to English."""
    name = name.strip()
    if name in TEAM_MAP:
        return TEAM_MAP[name]
    # Partial match
    for cn, en in TEAM_MAP.items():
        if cn in name or name in cn:
            return en
    return name
