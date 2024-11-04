import os

class Config:
    SECRET_KEY = os.urandom(24)
    MYSQL_HOST = 'localhost'
    MYSQL_USER = 'voterturnout'
    MYSQL_PASSWORD = 'python3721'
    MYSQL_DB = 'voter_turnout_db'
