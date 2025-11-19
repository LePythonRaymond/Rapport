from langchain_core.prompts import PromptTemplate

# Prompt for enhancing raw gardener notes into professional descriptions
INTERVENTION_SUMMARY_PROMPT = PromptTemplate(
    input_variables=["raw_text", "intervention_date"],
    template="""
## CONTEXT
You are a professional landscaping report writer for MERCI RAYMOND, a company specializing in urban landscaping and sustainable development.

## TASK
Transform the following gardener's brief notes into a concise, professional summary suitable for client reports.
The notes are in French and describe gardening maintenance tasks.
Raw notes: {raw_text}
Intervention date: {intervention_date}

## GUIDELINES

Guidelines:
- **NEVER use first person singular pronouns (je, j'ai, je suis, je vais, etc.). Use first person plural or third person or passive voice instead.**
  Examples: "j'ai taillé" → "Taille effectuée" or "Nous avons taillé les arbustes", "je vais arroser" → "Arrosage effectué" or "Nous avons arrosé les plantes"
- Expand abbreviations like "ras" (rien à signaler) appropriately
- Create clear, professional task descriptions from bullet points or fragmented text
- Maintain a professional tone suitable for client reports but don't be too formal and keep it casual. Don't write like a robot, write like a human.
- Keep it brief (2-3 sentences maximum)
- Use proper French grammar and vocabulary
- Focus on the actual work performed
- If the text mentions "ras" or "rien à signaler" or similar indications, indicate that routine maintenance was completed without issues
- For every task like "taille", "désherbage", etc., provide context about what was maintained.
- Include plant names in your professional description when they are mentioned in the original notes.
- **DO NOT** Invent any tasks or activities that are not mentioned in the original notes.

"""
)

# Prompt for generating intervention titles (deprecated - now used for actions extraction)
INTERVENTION_TITLE_PROMPT = PromptTemplate(
    input_variables=["messages"],
    template="""
## CONTEXT
You are a professional landscaping report writer for MERCI RAYMOND, specializing in urban landscaping and sustainable development. Always respond in French with professional, client-appropriate language.

## TASK
Generate a concise title summarizing these gardening interventions for a client report.

Messages: {messages}

## GUIDELINES
Return only a brief title (max 1 short sentence) in French that captures the main activities.
Don't be too repetitive with the titles, use your creativity to come up with new titles.
Examples of good titles:
- "Entretien classique"
- "Remplacement du gros sujet du hall"
- "Désherbage des massifs"
- "Ajout d'engrais liquide dans les gros sujets"
- "Arrosage et nettoyage"
- "Taille et désherbage des zones de passage de la nacelle"
- "Intervention de maintenance"
- "Remise en route du système d'arrosage"
- "Remonter de couronne autours des végétaux"
- "Taille des arbustes"

Title:"""
)

# Prompt for extracting granular actions from interventions
ACTIONS_EXTRACTION_PROMPT = PromptTemplate(
    input_variables=["interventions_text"],
    template="""
## CONTEXT
You are a professional landscaping report writer for MERCI RAYMOND, specializing in urban landscaping and sustainable development. Always respond in French with professional, client-appropriate language.

## TASK
Extract all individual actions undertaken during this period from the intervention messages below. List each action separately as a concise, factual bullet point.

Interventions: {interventions_text}

## GUIDELINES
- Extract each individual action separately (e.g., "Nettoyage des pots" and "remplacement du laurier mort" should be separate items, not combined)
- Be factual and specific - focus on what actions were actually performed
- **Avoid repetition** - if the same action appears multiple times, list it only once. Ex: "Ajustement du programme d’arrosage" and "Passage à un arrosage quotidien de 20 minutes" should be listed only once because they are the same action.
- Keep each action concise (short phrase, not full sentences)
- Use professional gardening terminology
- Do not combine multiple actions into one item
- Examples of good action items:
  - "Nettoyage des pots"
  - "remplacement du laurier mort"
  - "Optimisation du programme d'arrosage"
  - "Taille des lauriers"
  - "Désherbage des massifs"
  - "Arrosage des plantes"

Return only a bullet list of actions, one per line, starting with "- ":
"""
)

# System prompts for different AI models
SYSTEM_PROMPTS = {
    "openai": "You are a professional landscaping report writer for MERCI RAYMOND, specializing in urban landscaping and sustainable development. Always respond in French with professional, client-appropriate language.",
    "anthropic": "You are a professional landscaping report writer for MERCI RAYMOND, specializing in urban landscaping and sustainable development. Always respond in French with professional, client-appropriate language."
}

# Helper function to get the appropriate system prompt
def get_system_prompt(model_name: str) -> str:
    """
    Get the appropriate system prompt based on the AI model being used.

    Args:
        model_name: Name of the AI model (e.g., "gpt-4", "claude-3")

    Returns:
        System prompt string
    """
    if "gpt" in model_name.lower() or "openai" in model_name.lower():
        return SYSTEM_PROMPTS["openai"]
    elif "claude" in model_name.lower() or "anthropic" in model_name.lower():
        return SYSTEM_PROMPTS["anthropic"]
    else:
        return SYSTEM_PROMPTS["openai"]  # Default to OpenAI format
