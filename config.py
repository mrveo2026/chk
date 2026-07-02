# config.py
TOKEN = '8785536380:AAGkXq_OiZk4NXPqGDL7pRlR5VSQ_A3WlCo'
SUBSCRIBER = '5831292144'
ADMIN_USERNAME = '@VEO3_2'
BOT_NAME = 'NO OK BRO'
COST_PER_CHECK = 1
WELCOME_BONUS = 3
MAX_CARDS_PER_CHECK = 500

MASS_RATE_LIMIT = {'max': 100, 'window': 60}

MASS_GATES = {
    "v1": {"gate_file": "gatet1", "amount_min": 0.5, "amount_max": 1.0, "name": "Gate 1"},
    "v2": {"gate_file": "gatet2", "amount_min": 0.7, "amount_max": 1.4, "name": "Gate 2"},
    "v3": {"gate_file": "gatet3", "amount_min": 0.9, "amount_max": 2.0, "name": "Gate 3"},
    "v4": {"gate_file": "gatet4", "amount_min": 1.0, "amount_max": 2.0, "name": "Gate 4"},
    "v5": {"gate_file": "gatet5", "amount_min": 5.0, "amount_max": 5.5, "name": "Gate 5"},
    "v6": {"gate_file": "gatetHB", "amount_min": 20.0, "amount_max": 25.0, "name": "High Balance"}
}

PREMIUM_PLANS = {
    "Starter": {"credits": 4000, "price": 6, "days": 31},
    "Basic": {"credits": 10000, "price": 11, "days": 31},
    "Medium": {"credits": 20000, "price": 19, "days": 31},
    "Pro": {"credits": 30000, "price": 25, "days": 60},
    "Super": {"credits": 50000, "price": 30, "days": 99},
    "Ultra": {"credits": 150000, "price": 70, "days": 999}
}
