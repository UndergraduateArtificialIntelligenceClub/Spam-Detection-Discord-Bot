from transformers import pipeline
import re
from typing import Tuple
from config import Config

class ScamDetector:
    def __init__(self):
        """Initialize the scam detection model."""
        print(f"Loading model: {Config.MODEL_NAME}")
        self.classifier = pipeline(
            "text-classification",
            model=Config.MODEL_NAME,
            device=-1  # Use CPU, change to 0 for GPU
        )
        print("Model loaded successfully!")
    
    def detect(self, text: str) -> Tuple[bool, float, str]:
        """
        Detect if a message is a scam.
        
        Args:
            text: Message content to analyze
            
        Returns:
            Tuple of (is_scam, confidence_score, reason)
        """
        if not text or len(text.strip()) == 0:
            return False, 0.0, "Empty message"
        
        # Run ML model
        result = self.classifier(text)[0]
        score = result['score']
        label = result['label'].upper()
        
        # Check for suspicious patterns
        has_suspicious = self._check_suspicious_patterns(text)
        
        # Determine if it's a scam
        is_scam = False
        reason = ""
        
        if label in ['SPAM', 'SCAM'] and score > Config.SCAM_THRESHOLD:
            is_scam = True
            reason = f"ML Detection ({score:.2%})"
        elif score > 0.6 and has_suspicious:
            is_scam = True
            reason = f"ML Detection + Suspicious Patterns ({score:.2%})"
        
        return is_scam, score, reason
    
    def _check_suspicious_patterns(self, text: str) -> bool:
        """Check for known scam patterns."""
        text_lower = text.lower()
        
        suspicious_patterns = [
            # Discord-specific scams
            r'(?:free|click|win|claim).*(?:nitro|discord)',
            r'@everyone.*(?:giveaway|free)',
            r'discord\.(?:gift|com/gift)',
            
            # Crypto scams
            r'(?:free|airdrop|claim).*(?:crypto|btc|eth|nft)',
            
            # Phishing
            r'(?:verify|click|urgent).*(?:account|suspended|banned)',
            
            # URL shorteners (often used in scams)
            r'bit\.ly|tinyurl\.com|t\.co',
            
            # Common scam phrases
            r'act now|limited time|click here|verify now',
        ]
        
        return any(re.search(pattern, text_lower) for pattern in suspicious_patterns)
