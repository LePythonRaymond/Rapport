from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta
import re
import os
import random
from .client import NotionClient
from .database import NotionDatabaseManager
import config

class ReportPageBuilder:
    """
    Builds professional report pages for MERCI RAYMOND clients.
    Creates structured Notion pages with consistent formatting.
    """

    def __init__(self, notion_client: Optional[NotionClient] = None):
        """
        Initialize the page builder.

        Args:
            notion_client: NotionClient instance (creates new one if None)
        """
        self.client = notion_client or NotionClient()
        self.db_manager = NotionDatabaseManager(self.client)

    def build_report_page(self, client_name: str, interventions: List[Dict[str, Any]],
                         team_info: Dict[str, Any], date_range: str, report_date: Optional[datetime] = None) -> List[Dict[str, Any]]:
        """
        Build a complete report page structure with new format.

        Args:
            client_name: Name of the client
            interventions: List of intervention dictionaries
            team_info: Team member information
            date_range: Date range string (e.g., "01/10/2025 - 03/11/2025")
            report_date: Optional report date for title generation (defaults to today)

        Returns:
            List of Notion blocks for the report page
        """
        blocks = []

        # Note: Title is not included in page content (only in page properties)

        # 1. Date quote block
        blocks.append(self._create_date_quote_block(date_range, interventions))

        # Empty line between dates and columns
        blocks.extend(self._create_empty_lines(1))

        # 2. Two-column layout (Intervenants + Actions)
        blocks.append(self._create_intervenants_actions_columns(interventions, team_info))

        # 3. Three empty lines
        blocks.extend(self._create_empty_lines(3))

        # 4. Commentaires callout (empty - header only)
        blocks.append(self._create_commentaires_callout())

        # 6. Three empty lines
        blocks.extend(self._create_empty_lines(3))

        # 7. Intervention descriptions with images (green callout headers)
        intervention_blocks_list = self._create_intervention_blocks_with_images(interventions)
        # intervention_blocks_list is a list where each item is a list of blocks for one intervention
        for i, intervention_blocks in enumerate(intervention_blocks_list):
            # Add all blocks for this intervention
            blocks.extend(intervention_blocks)
            # Add 3 empty lines between intervention sections (but not after the last one)
            if i < len(intervention_blocks_list) - 1:
                blocks.extend(self._create_empty_lines(3))

        return blocks

    def _generate_report_title(self, client_name: str, report_date: datetime) -> str:
        """
        Generate formatted report title with cleaned site name, French month, and year.

        Args:
            client_name: Original client/site name (may contain numbers like "- 203")
            report_date: Date to determine which month and year to use

        Returns:
            Formatted title string (e.g., "Rapport d'Intervention - Atome (Equalia) - Octobre 2025")
        """
        # Clean: remove trailing " - 123" pattern
        cleaned_name = re.sub(r'\s*-\s*\d+\s*$', '', client_name).strip()

        # Determine month: if day > 15, use current month; else previous
        if report_date.day > 15:
            month_date = report_date
        else:
            # Previous month
            month_date = (report_date.replace(day=1) - timedelta(days=1))

        # Convert to French month names
        french_months = {
            1: 'Janvier', 2: 'Février', 3: 'Mars', 4: 'Avril',
            5: 'Mai', 6: 'Juin', 7: 'Juillet', 8: 'Août',
            9: 'Septembre', 10: 'Octobre', 11: 'Novembre', 12: 'Décembre'
        }
        month_fr = french_months.get(month_date.month, month_date.strftime('%B'))
        year = month_date.year

        return f"Rapport d'Intervention - {cleaned_name} - {month_fr} {year}"

    def _create_empty_lines(self, count: int) -> List[Dict[str, Any]]:
        """
        Create empty paragraph blocks for spacing.

        Args:
            count: Number of empty lines to create

        Returns:
            List of empty paragraph blocks
        """
        return [self.client.create_text_block("") for _ in range(count)]

    def _create_title_block(self, title: str) -> Dict[str, Any]:
        """Create the main title block."""
        return self.client.create_heading_block(
            text=title,
            level=1
        )

    def _create_intervenants_section(self, team_info: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Create the Intervenants section."""
        blocks = []

        # Section heading
        blocks.append(self.client.create_heading_block("INTERVENANTS", level=2))

        # Team members list
        team_items = [
            "MERCI RAYMOND - Équipe de paysagistes professionnels"
        ]

        # Add specific team members if available
        if team_info.get('chef_chantier'):
            team_items.append(f"Chef de chantier: {team_info['chef_chantier']}")

        if team_info.get('jardiniers'):
            jardiniers = ", ".join(team_info['jardiniers'])
            team_items.append(f"Jardiniers: {jardiniers}")

        # Add team description
        if team_info.get('team_description'):
            team_items.append(team_info['team_description'])

        blocks.extend(self.client.create_bullet_list_block(team_items))

        return blocks

    def _create_date_quote_block(self, date_range: str, interventions: List[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Create quote block for dates de passage.

        Always: 📆 DATES DE PASSAGE (bold) \n "Période d'intervention: [Dates]"
        Then: List of all precise dates from interventions
        """
        # Create rich text with "DATES DE PASSAGE" in bold
        rich_text = [
            {"type": "text", "text": {"content": "📆 "}},
            {"type": "text", "text": {"content": "DATES DE PASSAGE"},
             "annotations": {"bold": True, "italic": False, "strikethrough": False,
                            "underline": False, "code": False, "color": "default"}},
            {"type": "text", "text": {"content": "\n"}},
            {"type": "text", "text": {"content": f'"Période d\'intervention: {date_range}"'}}
        ]

        # Extract and format unique dates from interventions
        if interventions:
            # French month names
            french_months = {
                1: 'janvier', 2: 'février', 3: 'mars', 4: 'avril',
                5: 'mai', 6: 'juin', 7: 'juillet', 8: 'août',
                9: 'septembre', 10: 'octobre', 11: 'novembre', 12: 'décembre'
            }

            # Extract unique dates
            unique_dates = set()
            for intervention in interventions:
                intervention_date = intervention.get('intervention_date')
                if intervention_date:
                    # Handle both datetime and date objects
                    if isinstance(intervention_date, datetime):
                        date_obj = intervention_date.date()
                    else:
                        date_obj = intervention_date
                    unique_dates.add(date_obj)

            # Sort dates chronologically
            sorted_dates = sorted(unique_dates)

            # Add dates list to rich text
            if sorted_dates:
                rich_text.append({"type": "text", "text": {"content": "\n\n"}})
                for i, date_obj in enumerate(sorted_dates):
                    day = date_obj.day
                    month = date_obj.month
                    year = date_obj.year
                    month_name = french_months.get(month, f'mois {month}')
                    date_str = f"{day} {month_name} {year}"

                    # Add bullet point
                    if i > 0:
                        rich_text.append({"type": "text", "text": {"content": "\n"}})
                    rich_text.append({"type": "text", "text": {"content": f"• {date_str}"}})

        return self.client.create_quote_block("", rich_text=rich_text)

    def _create_intervenants_actions_columns(self, interventions: List[Dict[str, Any]], team_info: Dict[str, Any] = None) -> Dict[str, Any]:
        """
        Create two-column layout with intervenants and actions callouts.

        Left: 👨‍🌾 INTERVENANTS (H3) with bullet list of gardener names INSIDE callout
        Right: ✅ ACTIONS EFFECTUÉS (H3) with bullet list of intervention titles INSIDE callout
        Both use grey background.

        Args:
            interventions: List of intervention dictionaries
            team_info: Team member information containing 'jardiniers' list (includes authors AND mentions)
        """
        # Extract unique gardener names from team_info (which includes both authors and mentions)
        gardener_names = set()
        office_team_members = [name.lower() for name in config.OFFICE_TEAM_MEMBERS]  # Case-insensitive comparison

        # Use team_info if available (contains both authors and mentions from extract_team_members)
        if team_info and team_info.get('jardiniers'):
            for gardener_name in team_info['jardiniers']:
                if not gardener_name or gardener_name == 'Unknown':
                    continue

                # Check if this is an office team member (case-insensitive)
                gardener_name_lower = gardener_name.lower()
                is_office_team = any(office_name.lower() == gardener_name_lower for office_name in config.OFFICE_TEAM_MEMBERS)

                if not is_office_team:
                    gardener_names.add(gardener_name)
                    print(f"✅ Added gardener to list: {gardener_name}")
                else:
                    print(f"🚫 Excluded office team member from gardener list: {gardener_name}")
        else:
            # Fallback: extract from interventions (only authors, no mentions)
            print("⚠️ No team_info provided, falling back to intervention authors only (mentions will be missing)")
            for intervention in interventions:
                author_name = intervention.get('author_name', 'Unknown')
                # Skip if Unknown or empty
                if not author_name or author_name == 'Unknown':
                    continue

                # Check if this is an office team member (case-insensitive)
                author_name_lower = author_name.lower()
                is_office_team = any(office_name.lower() == author_name_lower for office_name in config.OFFICE_TEAM_MEMBERS)

                if not is_office_team:
                    gardener_names.add(author_name)
                    print(f"✅ Added gardener to list: {author_name}")
                else:
                    print(f"🚫 Excluded office team member from gardener list: {author_name}")

        # If no gardeners after filtering, show empty list (don't default to Unknown)
        gardener_names = sorted(list(gardener_names)) if gardener_names else []

        # Debug logging
        print(f"📊 Final gardener names list: {gardener_names}")
        if not gardener_names:
            print(f"⚠️ No gardeners found after filtering (may be all office team members or Unknown)")

        # Extract actions from interventions using AI
        from src.ai_processor.text_enhancer import TextEnhancer
        text_enhancer = TextEnhancer()
        actions_list = text_enhancer.extract_actions_from_interventions(interventions)

        # Use extracted actions, or fallback if empty
        if actions_list:
            actions_list = sorted(list(set(actions_list)))  # Remove duplicates and sort
        else:
            actions_list = ['Aucune action documentée']

        # Create bullet list blocks for intervenants (as children of callout)
        # If no gardeners, show a message instead of empty list
        if gardener_names:
            intervenants_bullets = self.client.create_bullet_list_block(gardener_names)
        else:
            # Show a message when no gardeners are identified
            intervenants_bullets = self.client.create_bullet_list_block(['Aucun jardinier identifié'])

        # Create left column (Intervenants) with bullets inside callout
        intervenants_callout = self.client.create_callout_block(
            rich_text=[self.client.create_heading_3_rich_text("INTERVENANTS")],
            icon="👨‍🌾",
            color="gray_background",
            children=intervenants_bullets
        )
        left_column = [intervenants_callout]

        # Create bullet list blocks for actions (as children of callout)
        actions_bullets = self.client.create_bullet_list_block(actions_list)

        # Create right column (Actions) with bullets inside callout
        actions_callout = self.client.create_callout_block(
            rich_text=[self.client.create_heading_3_rich_text("ACTIONS EFFECTUÉS")],
            icon="✅",
            color="gray_background",
            children=actions_bullets
        )
        right_column = [actions_callout]

        # Create column list
        return self.client.create_column_list_block([left_column, right_column])

    def _create_commentaires_callout(self) -> Dict[str, Any]:
        """
        Create commentaires callout block.

        Always: 📕 COMMENTAIRES (H3) with grey background.
        """
        return self.client.create_callout_block(
            rich_text=[self.client.create_heading_3_rich_text("COMMENTAIRES")],
            icon="📕",
            color="gray_background"
        )

    def _create_commentaires_content(self, interventions: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Create expanded explanations for all interventions in commentaires section as bullet list.

        Format: "• **Title**: description" with bold title and description.
        Converts markdown bold (**text**) to Notion rich text bold.
        """
        bullet_items = []

        for intervention in interventions:
            title = intervention.get('title', 'Intervention de maintenance')
            enhanced_text = intervention.get('enhanced_text', intervention.get('all_text', ''))

            if enhanced_text:
                # Format: "**Title**: description"
                formatted_text = f"**{title}**: {enhanced_text}"
                bullet_items.append(formatted_text)
            else:
                # Just the title in bold
                bullet_items.append(f"**{title}**")

        if bullet_items:
            # Create bullet list with rich text (bold titles)
            bullet_blocks = []
            for item in bullet_items:
                # Convert markdown bold to rich text for each bullet item
                rich_text = self.client.convert_markdown_bold_to_rich_text(item)
                bullet_blocks.append({
                    "type": "bulleted_list_item",
                    "bulleted_list_item": {
                        "rich_text": rich_text
                    }
                })
            return bullet_blocks

        return []

    def _get_intervention_emoji(self, intervention: Dict[str, Any]) -> str:
        """
        Get appropriate emoji for intervention type using intelligent keyword matching.

        Uses flexible keyword matching to handle variations like "apport d'engrai" → 🌾
        """
        # Get text to search
        title = intervention.get('title', '').lower()
        text = intervention.get('all_text', '').lower()
        search_text = f"{title} {text}"

        # Define keyword mappings (extensive list for flexibility)
        emoji_mappings = {
            '✂️': ['taille', 'taillé', 'coupe', 'coupé', 'élagage', 'élagué', 'élaguer', 'tailler'],
            '💧': ['arrosage', 'arrosé', 'arroser', 'eau', 'irrigation', 'irrigué', 'arroser'],
            '🌱': ['désherbage', 'désherbé', 'désherber', 'mauvaises herbes', 'herbes', 'mauvaise herbe'],
            '🧹': ['nettoyage', 'nettoyé', 'nettoyer', 'propre', 'ramassage', 'ramassé', 'ramasser', 'nettoyer'],
            '🌿': ['plantation', 'planté', 'planter', 'semis', 'repiquage', 'repiqué', 'repiquer', 'planter'],
            '🌾': ['fertilisation', 'fertilisé', 'fertiliser', 'engrais', 'nutriments', 'apport d\'engrai', 'apport engrai', 'apport d\'engrais', 'apport engrais'],
            '🌳': ['palissage', 'palissé', 'palisser', 'tuteur', 'tuteurs', 'support', 'tuteurage', 'tuteuré', 'soutenir'],
            '👀': ['surveillance', 'surveillé', 'surveiller', 'suivi', 'suivre', 'contrôle', 'contrôlé', 'contrôler', 'monitoring', 'monitorer']
        }

        # Check each emoji's keywords
        for emoji, keywords in emoji_mappings.items():
            for keyword in keywords:
                if keyword in search_text:
                    return emoji

        # Default emoji
        return '📋'

    def _create_actions_section(self, interventions: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Create the Actions effectuées section."""
        blocks = []

        # Section heading
        blocks.append(self.client.create_heading_block("ACTIONS EFFECTUÉES", level=2))

        # Create bullet list of interventions
        action_items = []
        for intervention in interventions:
            title = intervention.get('title', 'Intervention de maintenance')
            enhanced_text = intervention.get('enhanced_text', intervention.get('all_text', ''))

            if enhanced_text:
                action_items.append(f"**{title}**: {enhanced_text}")
            else:
                action_items.append(f"**{title}**")

        if action_items:
            blocks.extend(self.client.create_bullet_list_block(action_items))
        else:
            blocks.append(self.client.create_text_block("Aucune intervention documentée pour cette période."))

        return blocks

    def _create_image_grid_columns(self, image_urls: List[str], images_per_row: int = 3) -> List[Dict[str, Any]]:
        """
        Create N-column grid layout for images.

        Args:
            image_urls: List of image URLs (Notion file upload references)
            images_per_row: Number of images per row (default 3)

        Returns:
            List of column_list blocks with images in grid layout
        """
        if not image_urls:
            return []

        column_blocks = []

        # Process images in chunks of images_per_row
        for i in range(0, len(image_urls), images_per_row):
            row_images = image_urls[i:i + images_per_row]

            # Notion requires at least 2 columns in a column_list
            # If only 1 image in this row, add it directly without column_list
            if len(row_images) == 1:
                column_blocks.append(self.client.create_image_block(row_images[0], caption=None))
            else:
                # Create column for each image in this row
                columns = []
                for image_url in row_images:
                    # Each column contains one image
                    column_content = [
                        self.client.create_image_block(image_url, caption=None)
                    ]
                    columns.append(column_content)

                # Create column list block for this row (only if 2+ columns)
                if len(columns) >= 2:
                    column_list = self.client.create_column_list_block(columns)
                    column_blocks.append(column_list)

        return column_blocks

    def _create_avant_apres_section(self, avant_images: List[str], apres_images: List[str]) -> List[Dict[str, Any]]:
        """
        Create AVANT/APRÈS section with column layouts.

        Args:
            avant_images: List of AVANT image URLs
            apres_images: List of APRÈS image URLs

        Returns:
            List of blocks forming the AVANT/APRÈS section
        """
        blocks = []

        if not avant_images and not apres_images:
            return blocks

        # AVANT section
        if avant_images:
            # Create AVANT heading (H3, bold, underlined)
            avant_heading = {
                "type": "heading_3",
                "heading_3": {
                    "rich_text": [
                        {
                            "type": "text",
                            "text": {"content": "AVANT"},
                            "annotations": {
                                "bold": True,
                                "italic": False,
                                "strikethrough": False,
                                "underline": True,
                                "code": False,
                                "color": "default"
                            }
                        }
                    ]
                }
            }
            blocks.append(avant_heading)

            # Create column grid for AVANT images (3 per row)
            avant_columns = self._create_image_grid_columns(avant_images, images_per_row=3)
            blocks.extend(avant_columns)

        # Add empty line between AVANT and APRÈS
        if avant_images and apres_images:
            blocks.append(self.client.create_text_block(""))

        # APRÈS section
        if apres_images:
            # Create APRÈS heading (H3, bold, underlined)
            apres_heading = {
                "type": "heading_3",
                "heading_3": {
                    "rich_text": [
                        {
                            "type": "text",
                            "text": {"content": "APRÈS"},
                            "annotations": {
                                "bold": True,
                                "italic": False,
                                "strikethrough": False,
                                "underline": True,
                                "code": False,
                                "color": "default"
                            }
                        }
                    ]
                }
            }
            blocks.append(apres_heading)

            # Create column grid for APRÈS images (3 per row)
            apres_columns = self._create_image_grid_columns(apres_images, images_per_row=3)
            blocks.extend(apres_columns)

        return blocks

    def _create_intervention_blocks_with_images(self, interventions: List[Dict[str, Any]]) -> List[List[Dict[str, Any]]]:
        """
        Create intervention blocks with green callout headers, descriptions, and images.
        Handles regular images and AVANT/APRÈS sections.

        Returns a list where each item is a list of blocks for one intervention.
        Each intervention gets:
        1. Green callout header with H3 title and adapted emoji
        2. Description text (with markdown bold converted to rich text)
        3. Regular images (if any)
        4. AVANT/APRÈS section (if has_avant_apres flag is set)
        """
        intervention_sections = []

        # Process all interventions (with or without images)
        for intervention in interventions:
            intervention_blocks = []

            # Get intervention title (no emoji in title anymore)
            title = intervention.get('title', 'Intervention de maintenance')
            # Generate random emoji for callout icon
            gardening_emojis = [
                '🌿', '🌱', '🌳', '🌲', '🌴', '🌾', '🌷', '🌻', '🌺', '🌸',
                '🌼', '🍃', '🍀', '🌵', '🌰', '🥀', '🌹'
            ]
            emoji = random.choice(gardening_emojis)

            # Create green callout header with H3 title
            header_callout = self.client.create_callout_block(
                rich_text=[self.client.create_heading_3_rich_text(title)],
                icon=emoji,
                color="green_background"
            )
            intervention_blocks.append(header_callout)

            # Add description with converted markdown bold
            enhanced_text = intervention.get('enhanced_text', intervention.get('all_text', ''))
            if enhanced_text:
                # Convert markdown bold to rich text
                rich_text = self.client.convert_markdown_bold_to_rich_text(enhanced_text)
                intervention_blocks.append(self.client.create_text_block_from_rich_text(rich_text))

            # Check if this intervention has avant/après sections
            has_avant_apres = intervention.get('has_avant_apres', False)

            if has_avant_apres:
                # Get already-categorized notion image URLs
                # These were categorized during image processing in image_handler.py
                regular_notion_images = intervention.get('notion_regular_images', [])
                avant_notion_images = intervention.get('notion_avant_images', [])
                apres_notion_images = intervention.get('notion_apres_images', [])

                # Show regular images first (if any)
                if regular_notion_images:
                    for i, image_url in enumerate(regular_notion_images):
                        caption = f"{title} - Photo {i + 1}" if len(regular_notion_images) > 1 else None
                        intervention_blocks.append(self.client.create_image_block(image_url, caption))

                # Add AVANT/APRÈS section if images exist
                if avant_notion_images or apres_notion_images:
                    # Create avant/après section with properly categorized images
                    avant_apres_blocks = self._create_avant_apres_section(avant_notion_images, apres_notion_images)
                    intervention_blocks.extend(avant_apres_blocks)
            else:
                # No avant/après - show all images as regular
                if intervention.get('notion_images'):
                    for i, image_url in enumerate(intervention['notion_images']):
                        if len(intervention['notion_images']) > 1:
                            caption = f"{title} - Photo {i + 1}"
                        else:
                            caption = None
                        intervention_blocks.append(self.client.create_image_block(image_url, caption))

            # Only add if there's content
            if intervention_blocks:
                intervention_sections.append(intervention_blocks)

        return intervention_sections

    def _create_animations_section(self, interventions: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Create Animations section if there are special events."""
        blocks = []

        # Look for special events or animations
        special_events = []
        for intervention in interventions:
            text = intervention.get('all_text', '').lower()
            if any(keyword in text for keyword in ['animation', 'événement', 'spécial', 'fête', 'cérémonie']):
                special_events.append(intervention)

        if special_events:
            blocks.append(self.client.create_heading_block("Animations", level=2))

            for event in special_events:
                description = event.get('enhanced_text', event.get('all_text', ''))
                if description:
                    blocks.append(self.client.create_text_block(description))

                # Add images if available
                if event.get('notion_images'):
                    for i, image_url in enumerate(event['notion_images']):
                        blocks.append(self.client.create_image_block(image_url, f"Animation - Photo {i + 1}"))

        return blocks

    def _create_quality_section(self, interventions: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Create quality assessment section."""
        blocks = []

        # Section heading
        blocks.append(self.client.create_heading_block("Évaluation de la Qualité", level=2))

        # Quality assessment text
        quality_text = "Toutes les interventions ont été effectuées selon les standards de qualité MERCI RAYMOND. "
        quality_text += "L'équipe a maintenu un niveau de professionnalisme élevé tout au long de la période d'intervention."

        blocks.append(self.client.create_callout_block(
            text=quality_text,
            icon="✅"
        ))

        return blocks

    def _group_interventions_by_type(self, interventions: List[Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
        """Group interventions by type."""
        groups = {
            'Taille des arbustes': [],
            'Désherbage': [],
            'Arrosage': [],
            'Nettoyage': [],
            'Plantation': [],
            'Autres interventions': []
        }

        for intervention in interventions:
            intervention_type = self._categorize_intervention(intervention)
            if intervention_type in groups:
                groups[intervention_type].append(intervention)
            else:
                groups['Autres interventions'].append(intervention)

        # Remove empty groups
        return {k: v for k, v in groups.items() if v}

    def _categorize_intervention(self, intervention: Dict[str, Any]) -> str:
        """Categorize an intervention by type."""
        text = intervention.get('all_text', '').lower()

        if any(keyword in text for keyword in ['taille', 'taillé', 'coupe', 'élagage']):
            return 'Taille des arbustes'
        elif any(keyword in text for keyword in ['désherbage', 'désherbé', 'mauvaises herbes']):
            return 'Désherbage'
        elif any(keyword in text for keyword in ['arrosage', 'arrosé', 'eau', 'irrigation']):
            return 'Arrosage'
        elif any(keyword in text for keyword in ['nettoyage', 'nettoyé', 'propre', 'ramassage']):
            return 'Nettoyage'
        elif any(keyword in text for keyword in ['plantation', 'planté', 'semis', 'repiquage']):
            return 'Plantation'
        else:
            return 'Autres interventions'

    def _create_type_description(self, intervention_type: str, interventions: List[Dict[str, Any]]) -> str:
        """Create a description for a specific intervention type."""
        if not interventions:
            return ""

        # Count interventions
        count = len(interventions)

        # Get first intervention for context
        first_intervention = interventions[0]
        enhanced_text = first_intervention.get('enhanced_text', '')

        if intervention_type == 'Taille des arbustes':
            return f"Interventions de taille effectuées sur {count} zone(s). {enhanced_text}"
        elif intervention_type == 'Désherbage':
            return f"Désherbage effectué sur {count} zone(s). {enhanced_text}"
        elif intervention_type == 'Arrosage':
            return f"Arrosage effectué sur {count} zone(s). {enhanced_text}"
        elif intervention_type == 'Nettoyage':
            return f"Nettoyage effectué sur {count} zone(s). {enhanced_text}"
        elif intervention_type == 'Plantation':
            return f"Plantations effectuées sur {count} zone(s). {enhanced_text}"
        else:
            return f"Interventions diverses effectuées sur {count} zone(s). {enhanced_text}"

    def create_report_page(self, client_name: str, interventions: List[Dict[str, Any]],
                          team_info: Dict[str, Any], date_range: str, report_date: Optional[datetime] = None) -> Optional[str]:
        """
        Create a complete report page in Notion with cover and icon.

        Args:
            client_name: Name of the client
            interventions: List of intervention dictionaries
            team_info: Team member information
            date_range: Date range string
            report_date: Optional report date for title generation (defaults to today)

        Returns:
            Created page ID or None if creation fails
        """
        try:
            # Get client for relation
            client = self.db_manager.get_client_by_name(client_name)
            if not client:
                print(f"❌ Client '{client_name}' not found")
                return None

            # Upload cover and icon assets
            cover_ref = None
            icon_ref = None

            # Upload cover image
            cover_path = config.REPORT_COVER_IMAGE_PATH
            if os.path.exists(cover_path):
                print(f"📤 Uploading cover image: {cover_path}")
                cover_ref = self.client.upload_local_file_for_asset(cover_path)
                if cover_ref:
                    print("✅ Cover image uploaded")
            else:
                # Try absolute path if relative doesn't work
                abs_cover_path = os.path.join(os.getcwd(), cover_path)
                if os.path.exists(abs_cover_path):
                    cover_ref = self.client.upload_local_file_for_asset(abs_cover_path)
                    if cover_ref:
                        print("✅ Cover image uploaded (absolute path)")
                else:
                    print(f"⚠️ Cover image not found: {cover_path}")

            # Upload icon
            icon_path = config.REPORT_ICON_IMAGE_PATH
            if os.path.exists(icon_path):
                print(f"📤 Uploading icon: {icon_path}")
                icon_ref = self.client.upload_local_file_for_asset(icon_path)
                if icon_ref:
                    print("✅ Icon uploaded")
            else:
                print(f"⚠️ Icon not found: {icon_path}")

            # Build page content
            if report_date is None:
                report_date = datetime.now()
            page_blocks = self.build_report_page(client_name, interventions, team_info, date_range, report_date)

            # Generate title for page properties
            title = self._generate_report_title(client_name, report_date)

            # Generate unique report ID
            import uuid
            report_id = f"RPT-{uuid.uuid4().hex[:8].upper()}"

            # Get current date/time for Date de création
            # Notion API requires ISO 8601 format (e.g., "2025-11-04T15:49:00")
            current_date = datetime.now()
            creation_date_str = current_date.isoformat()

            # Create the page with French properties including Client relation
            page_properties = {
                "Nom": {
                    "title": [
                        {
                            "text": {
                                "content": title
                            }
                        }
                    ]
                },
                "Client": {
                    "relation": [
                        {
                            "id": client['id']
                        }
                    ]
                },
                "Statut": {
                    "select": {
                        "name": "Brouillon"
                    }
                },
                "Date de création": {
                    "date": {
                        "start": creation_date_str
                    }
                }
            }

            response = self.client.create_page(
                parent_db_id=self.db_manager.rapports_db_id,
                properties=page_properties,
                children=page_blocks,
                cover=cover_ref,
                icon=icon_ref
            )

            print(f"✅ Created report page for {client_name}")
            return response['id']

        except Exception as e:
            print(f"❌ Error creating report page: {e}")
            import traceback
            traceback.print_exc()
            return None

    def create_simple_report(self, client_name: str, interventions: List[Dict[str, Any]],
                           date_range: str) -> Optional[str]:
        """
        Create a simplified report page.

        Args:
            client_name: Name of the client
            interventions: List of intervention dictionaries
            date_range: Date range string

        Returns:
            Created page ID or None if creation fails
        """
        try:
            # Simple page structure
            blocks = [
                self.client.create_heading_block(f"Rapport d'Intervention - {client_name}", level=1),
                self.client.create_heading_block("Interventions Effectuées", level=2)
            ]

            # Add interventions
            for intervention in interventions:
                title = intervention.get('title', 'Intervention')
                text = intervention.get('enhanced_text', intervention.get('all_text', ''))

                blocks.append(self.client.create_text_block(f"• {title}: {text}"))

            # Create the page
            page_properties = {
                "Name": {
                    "title": [
                        {
                            "text": {
                                "content": f"Rapport {client_name} - {date_range}"
                            }
                        }
                    ]
                }
            }

            response = self.client.create_page(
                parent_db_id=self.db_manager.rapports_db_id,
                properties=page_properties,
                children=blocks
            )

            print(f"✅ Created simple report page for {client_name}")
            return response['id']

        except Exception as e:
            print(f"❌ Error creating simple report page: {e}")
            return None

# Convenience functions
def create_report_page_builder() -> ReportPageBuilder:
    """
    Create a report page builder with default configuration.

    Returns:
        Configured ReportPageBuilder instance
    """
    return ReportPageBuilder()

def test_page_builder() -> bool:
    """
    Test the page builder functionality.

    Returns:
        True if test successful, False otherwise
    """
    try:
        builder = create_report_page_builder()

        # Test data
        test_interventions = [
            {
                'title': 'Taille des arbustes',
                'enhanced_text': 'Taille de formation effectuée sur les rosiers et les buis',
                'all_text': 'taille rosiers buis',
                'notion_images': []
            }
        ]

        test_team_info = {
            'chef_chantier': 'Jean Dupont',
            'jardiniers': ['Marie Martin', 'Pierre Durand']
        }

        # Build page structure
        blocks = builder.build_report_page(
            client_name="Test Client",
            interventions=test_interventions,
            team_info=test_team_info,
            date_range="2024-01-01 - 2024-01-31"
        )

        print(f"✅ Page builder test successful! Generated {len(blocks)} blocks")
        return True

    except Exception as e:
        print(f"❌ Page builder test failed: {e}")
        return False

if __name__ == "__main__":
    # Test the page builder
    test_page_builder()
