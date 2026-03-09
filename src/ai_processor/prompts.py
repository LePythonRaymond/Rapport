from langchain_core.prompts import PromptTemplate

# Prompt for enhancing raw gardener notes into professional descriptions
INTERVENTION_SUMMARY_PROMPT = PromptTemplate(
    input_variables=["raw_text", "intervention_date"],
    template="""
## CONTEXT
You are a professional landscaping report writer for MERCI RAYMOND, a company specializing in urban landscaping and sustainable development.
You are writing from the office, synthesizing information sent by the field team to the client.

## TASK
Transform the following gardener's brief notes into a concise, professional summary suitable for client reports.
The notes are in French and describe gardening maintenance tasks.
Raw notes: {raw_text}
Intervention date: {intervention_date}

## GUIDELINES

**Tone and Perspective:**
- **Write from the office perspective:** Use "nous" (we) and "notre intervention" (our intervention) to sound like a cohesive team.
- **Use "Site":** Refer to the maintenance location/area as "le Site" or "la zone" where appropriate.
- **Professional yet natural:** Avoid robotic or overly formal language. Write like a human communicating with a client.
- **Never use first person singular ("je").** Always use "nous" or passive voice if absolutely necessary, but prefer "nous".

**Structure and Phrasing:**
- **Vary the start of the summary:** Do NOT always start with "Lors de notre intervention du...". Be creative with introductions.
- **Date usage:** The date is already in the section title, so you do not always need to repeat it in the text unless it helps with clarity or context.
- **Sentence variety:** Use different sentence structures to make the report engaging to read.

**Content:**
- Expand abbreviations (e.g., "ras" -> routine maintenance completed without issues).
- Create clear, professional task descriptions.
- Keep it brief (2-3 sentences maximum).
- Use professional vocabulary (e.g., "nécessité", "approfondi", "indispensable", "finaliser", "achever").
- **Include specific details:** Plant names, specific zones mentioned.
- **DO NOT invent tasks** not mentioned in the notes.
- **Avoid generic closing sentences.** Do NOT use phrases such as: "Le Site est satisfaisant et ne nécessite pas d'action corrective pour le moment", "L'état général du Site est satisfaisant", "L'état général des végétaux et des installations est satisfaisant et ne nécessite aucune action corrective", "aucune intervention supplémentaire n'est requise pour l'instant". These sound robotic and imply there is nothing to report. Instead, briefly describe what was done and the current state in concrete terms (e.g. what was checked, what is in good order) without falling back on these formulas.

## EXAMPLES

**Example 1 (Desired Style):**
*Input:* "besoin gros nettoyage pour l'irrigation avant de replanter. 27/01 gros nettoyage presque fini. reste irrigation et finir nettoyage. dechets laissés sur place pour la prochaine fois."
*Output:* "Notre compte rendu précédent nous témoignait de la nécessité d’un nettoyage approfondi du Site afin de préparer la zone pour la remise en service de l’irrigation, indispensable avant toute réimplantation de plants. Le nettoyage approfondi est désormais quasiment terminé. Il reste à finaliser l’installation du système d’irrigation et à achever le nettoyage de cette zone. Les déchets générés ont été laissés sur place pour être évacués lors du prochain passage."

**Example 2:**
*Input:* "taille des rosiers et desherbage massif entrée. arrosage ok."
*Output:* "Nous avons procédé ce jour à la taille des rosiers ainsi qu'au désherbage du massif situé à l'entrée du Site. En complément, l'arrosage des plantations a été vérifié et assuré par nos équipes."

**Example 3 (routine visit, no issues – describe what was done, avoid generic "satisfaisant" formulas):**
*Input:* "Arrosage des jardinières du 6ème. tout va bien"
*Output:* "L'entretien des jardinières du 6ème étage s'est poursuivi avec un arrosage complet. Les végétaux ont été contrôlés et l'arrosage est assuré jusqu'au prochain passage."
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
    "anthropic": "You are a professional landscaping report writer for MERCI RAYMOND, specializing in urban landscaping and sustainable development. Always respond in French with professional, client-appropriate language.",
    "gemini": "You are a professional landscaping report writer for MERCI RAYMOND, specializing in urban landscaping and sustainable development. Always respond in French with professional, client-appropriate language.",
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
    elif "gemini" in model_name.lower():
        return SYSTEM_PROMPTS["gemini"]
    else:
        return SYSTEM_PROMPTS["openai"]  # Default to OpenAI format
