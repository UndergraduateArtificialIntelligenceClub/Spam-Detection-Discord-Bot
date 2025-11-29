import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    DISCORD_TOKEN = os.getenv('DISCORD_TOKEN')
    LOG_CHANNEL_ID = int(os.getenv('LOG_CHANNEL_ID', 0))
    
    MODEL_NAME = os.getenv('MODEL_NAME', 'mrm8488/bert-tiny-finetuned-sms-spam-detection')
    SCAM_THRESHOLD = float(os.getenv('SCAM_THRESHOLD', 0.85))
    
    ENVIRONMENT = os.getenv('ENVIRONMENT', 'development')
    
    @classmethod
    def validate(cls):
        if not cls.DISCORD_TOKEN:
            raise ValueError("DISCORD_TOKEN is required in .env file")
        if cls.LOG_CHANNEL_ID == 0:
            raise ValueError("LOG_CHANNEL_ID is required in .env file")
        
        return True
