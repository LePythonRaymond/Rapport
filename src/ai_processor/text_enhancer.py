from typing import List, Dict, Any, Optional
from langchain_openai import ChatOpenAI
from langchain_core.output_parsers import StrOutputParser
from datetime import datetime
import random
import config
from .prompts import (
    INTERVENTION_SUMMARY_PROMPT,
    INTERVENTION_TITLE_PROMPT,
    ACTIONS_EXTRACTION_PROMPT
)

class TextEnhancer:
    """
    AI-powered text enhancement for gardening intervention reports.
    Uses LangChain with OpenAI or Anthropic models to transform raw gardener notes
    into professional client-ready descriptions.
    """

    def __init__(self, model_name: Optional[str] = None, temperature: Optional[float] = None):
        """
        Initialize the text enhancer with AI model configuration.

        Args:
            model_name: AI model to use (defaults to config.AI_MODEL)
            temperature: Model temperature (defaults to config.AI_TEMPERATURE)
        """
        self.model_name = model_name or config.AI_MODEL
        self.temperature = temperature or config.AI_TEMPERATURE

        # Initialize the LLM
        self.llm = self._initialize_llm()

        # Initialize chains
        self._initialize_chains()

    def _initialize_llm(self):
        """Initialize the language model based on configuration."""
        if not config.OPENAI_API_KEY:
            raise ValueError("OpenAI API key not found in environment variables")

        return ChatOpenAI(
            model=self.model_name,
            temperature=self.temperature,
            openai_api_key=config.OPENAI_API_KEY
        )

    def _initialize_chains(self):
        """Initialize LangChain chains for different text enhancement tasks using the modern Runnable interface."""
        # Use the modern LangChain API: prompt | llm | output_parser
        self.intervention_chain = INTERVENTION_SUMMARY_PROMPT | self.llm | StrOutputParser()

        self.title_chain = INTERVENTION_TITLE_PROMPT | self.llm | StrOutputParser()

        self.actions_chain = ACTIONS_EXTRACTION_PROMPT | self.llm | StrOutputParser()




    def enhance_intervention_text(self, raw_text: str, intervention_date: Optional[str] = None) -> str:
        """
        Transform raw gardener notes into professional description.

        Args:
            raw_text: Raw text from gardener messages
            intervention_date: Optional date string in DD/MM format

        Returns:
            Enhanced professional description
        """
        try:
            if not raw_text or not raw_text.strip():
                return "Aucune intervention documentée."

            # Format date for display
            if not intervention_date or intervention_date == "Date non spécifiée":
                intervention_date = "Date non spécifiée"

            result = self.intervention_chain.invoke({
                "raw_text": raw_text.strip(),
                "intervention_date": intervention_date
            })
            return result.strip()
        except Exception as e:
            print(f"Error enhancing intervention text: {e}")
            if intervention_date and intervention_date != "Date non spécifiée":
                return f"Durant l'intervention du {intervention_date}, {raw_text}"
            return f"Intervention effectuée: {raw_text}"

    def _get_random_gardening_emoji(self) -> str:
        """
        Get a random emoji from the expanded gardening/plant emoji pool.

        Returns:
            Random emoji string
        """
        gardening_emojis = [
            '🌿', '🌱', '🌳', '🌲', '🌴', '🌾', '🌷', '🌻', '🌺', '🌸',
            '🌼', '🍃', '🍀', '🌵', '🌰', '🥀', '🌹', '🌺', '🌻', '🌷',
            '🌼', '🌾', '🌿', '🌱', '🌳', '🌲', '🌴', '🍃', '🍀', '🌵'
        ]
        return random.choice(gardening_emojis)

    def _format_date_french(self, date_obj: datetime) -> str:
        """
        Format a date object to French format: "15 octobre 2025"

        Args:
            date_obj: datetime object

        Returns:
            Formatted date string in French
        """
        french_months = {
            1: 'janvier', 2: 'février', 3: 'mars', 4: 'avril',
            5: 'mai', 6: 'juin', 7: 'juillet', 8: 'août',
            9: 'septembre', 10: 'octobre', 11: 'novembre', 12: 'décembre'
        }

        day = date_obj.day
        month = date_obj.month
        year = date_obj.year
        month_name = french_months.get(month, f'mois {month}')

        return f"{day} {month_name} {year}"

    def generate_intervention_title(self, intervention_date: Optional[datetime] = None) -> str:
        """
        Generate intervention title in format "Intervention du {Date}" (no emoji in title).

        Args:
            intervention_date: Optional datetime object for the intervention date

        Returns:
            Title in format "Intervention du {Date}" (emoji is handled separately in callout icon)
        """
        try:
            # Format date
            if intervention_date:
                if isinstance(intervention_date, datetime):
                    date_str = self._format_date_french(intervention_date)
                else:
                    # If it's a date object, convert to datetime
                    date_str = self._format_date_french(datetime.combine(intervention_date, datetime.min.time()))
            else:
                # Fallback to current date if no date provided
                date_str = self._format_date_french(datetime.now())

            return f"Intervention du {date_str}"
        except Exception as e:
            print(f"Error generating intervention title: {e}")
            return "Intervention de maintenance"

    def batch_enhance_interventions(self, interventions: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Enhance multiple interventions in batch for efficiency.

        Args:
            interventions: List of intervention dictionaries

        Returns:
            List of enhanced intervention dictionaries
        """
        enhanced_interventions = []

        for intervention in interventions:
            try:
                # Enhance the main text
                raw_text = intervention.get('all_text', '')

                # Extract and format intervention date
                intervention_date_obj = intervention.get('intervention_date')
                if intervention_date_obj:
                    # Format as DD/MM
                    formatted_date = intervention_date_obj.strftime('%d/%m')
                else:
                    formatted_date = "Date non spécifiée"

                enhanced_text = self.enhance_intervention_text(raw_text, formatted_date)
                intervention['enhanced_text'] = enhanced_text

                # Generate title if not present
                if not intervention.get('title'):
                    intervention_date_obj = intervention.get('intervention_date')
                    title = self.generate_intervention_title(intervention_date_obj)
                    intervention['title'] = title

                enhanced_interventions.append(intervention)

            except Exception as e:
                print(f"Error enhancing intervention: {e}")
                # Keep original intervention if enhancement fails
                intervention['enhanced_text'] = intervention.get('all_text', 'Intervention effectuée')
                intervention['title'] = "Intervention de maintenance"
                enhanced_interventions.append(intervention)

        return enhanced_interventions

    def extract_actions_from_interventions(self, interventions: List[Dict[str, Any]]) -> List[str]:
        """
        Extract granular, factual actions from all interventions using AI.

        Args:
            interventions: List of intervention dictionaries

        Returns:
            List of individual action strings
        """
        try:
            if not interventions:
                return []

            # Collect all intervention enhanced descriptions (prioritize enhanced_text)
            intervention_texts = []
            for intervention in interventions:
                # Use enhanced_text first (better quality), fallback to all_text if not available
                text = intervention.get('enhanced_text', '') or intervention.get('all_text', '')
                if text:
                    intervention_texts.append(text)

            if not intervention_texts:
                return []

            # Combine all texts
            combined_text = "\n---\n".join(intervention_texts)

            # Call AI to extract actions
            result = self.actions_chain.invoke({"interventions_text": combined_text})

            # Parse the result - extract bullet points
            actions = []
            for line in result.strip().split('\n'):
                line = line.strip()
                # Remove bullet markers (-, •, etc.)
                if line.startswith('- '):
                    actions.append(line[2:].strip())
                elif line.startswith('• '):
                    actions.append(line[2:].strip())
                elif line.startswith('-'):
                    actions.append(line[1:].strip())
                elif line and not line.startswith('#') and not line.startswith('##'):
                    # If no bullet, assume it's an action
                    actions.append(line)

            # Filter out empty strings
            actions = [action for action in actions if action]

            return actions if actions else []
        except Exception as e:
            print(f"Error extracting actions from interventions: {e}")
            # Fallback: return basic actions from intervention titles
            return [intervention.get('title', 'Intervention de maintenance') for intervention in interventions if intervention.get('title')]

    def test_enhancement(self, sample_text: str) -> Dict[str, str]:
        """
        Test the enhancement capabilities with sample text.

        Args:
            sample_text: Sample text to test

        Returns:
            Dictionary with different enhancement results
        """
        results = {
            'original': sample_text,
            'enhanced': self.enhance_intervention_text(sample_text),
            'title': self.generate_intervention_title()
        }

        return results

# Convenience function for quick enhancement
def enhance_text(raw_text: str, context: str = "") -> str:
    """
    Quick function to enhance a single text.

    Args:
        raw_text: Raw text to enhance
        context: Optional context (not used, kept for compatibility)

    Returns:
        Enhanced text
    """
    enhancer = TextEnhancer()
    return enhancer.enhance_intervention_text(raw_text)

if __name__ == "__main__":
    # Test the text enhancer
    enhancer = TextEnhancer()

    sample_text = "ras\nDésherbage\nTaille\nPalissage\nNettoyage"
    results = enhancer.test_enhancement(sample_text)

    print("Original:", results['original'])
    print("Enhanced:", results['enhanced'])
    print("Title:", results['title'])
