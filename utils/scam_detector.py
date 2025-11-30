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

        cleaned_text = text

        # Remove mention markers and IDs, replace with placeholder text
        # <@123456> -> "user"
        # <@&123456> -> "role"  
        # @everyone -> "everyone"
        cleaned_text = re.sub(r'<@!?\d+>', 'user', cleaned_text)
        cleaned_text = re.sub(r'<@&\d+>', 'role', cleaned_text)
        cleaned_text = cleaned_text.replace('@everyone', 'everyone')
        cleaned_text = cleaned_text.replace('@here', 'here')
        cleaned_text = re.sub(r'@\w+', '', cleaned_text)  # Remove other @mentions
        cleaned_text = cleaned_text.strip()

        # If message is empty after cleaning, skip it
        if not cleaned_text or len(cleaned_text.strip()) == 0:
            return False, 0.0, "Empty message"

        # Run ML model on cleaned text
        result = self.classifier(cleaned_text)[0]
        score = result['score']
        label = result['label']

        # Map numeric labels to text
        label_map = {
            'LABEL_0': 'HAM',   # Legitimate message
            'LABEL_1': 'SPAM'   # Spam/Scam message
        }
        label = label_map.get(label, label).upper()

        # DEBUG OUTPUT
        print(f"\n[DETECTOR] Original: {text[:80]}")
        print(f"[DETECTOR] Cleaned: {cleaned_text[:80]}")
        print(f"[DETECTOR] Label: {label} | Score: {score:.4f}")
        print(f"[DETECTOR] Threshold: {Config.SCAM_THRESHOLD}")
        print(f"[DETECTOR] Check (label=SPAM AND score > threshold): {label == 'SPAM'} and {score > Config.SCAM_THRESHOLD}\n")

        # Determine if it's a scam
        is_scam = False
        reason = ""

        # Simple check: Model says SPAM and score above threshold
        if label == 'SPAM' and score > Config.SCAM_THRESHOLD:
            is_scam = True
            reason = f"ML Detection ({score:.2%})"

        return is_scam, score, reason
