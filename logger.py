# logger.py
import logging
import os

os.makedirs('logs', exist_ok=True)

error_logger = logging.getLogger('error_logger')
error_logger.setLevel(logging.ERROR)
error_handler = logging.FileHandler('logs/error.log')
error_handler.setFormatter(logging.Formatter('%(asctime)s - %(message)s'))
error_logger.addHandler(error_handler)

check_logger = logging.getLogger('check_logger')
check_logger.setLevel(logging.INFO)
check_handler = logging.FileHandler('logs/checks.log')
check_handler.setFormatter(logging.Formatter('%(asctime)s - %(message)s'))
check_logger.addHandler(check_handler)

transaction_logger = logging.getLogger('transaction_logger')
transaction_logger.setLevel(logging.INFO)
transaction_handler = logging.FileHandler('logs/transactions.log')
transaction_handler.setFormatter(logging.Formatter('%(asctime)s - %(message)s'))
transaction_logger.addHandler(transaction_handler)

def log_error(message):
    error_logger.error(message)

def log_check(user_id, username, gate, card, result, response):
    check_logger.info(f"User:{user_id} (@{username}) Gate:{gate} Card:{card[:6]}... Result:{result} Response:{response[:50]}")

def log_transaction(user_id, amount, trans_type, description):
    transaction_logger.info(f"User:{user_id} Amount:{amount} Type:{trans_type} Desc:{description}")
