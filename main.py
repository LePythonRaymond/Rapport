import streamlit as st
import pandas as pd
from datetime import date, timedelta, datetime
import time
import traceback

# Import our modules
from src.google_chat.client import GoogleChatClient, get_messages_for_client
from src.utils.data_extractor import (
    group_messages_by_intervention,
    extract_team_members,
    clean_text,
    apply_off_rule_filtering
)
from src.ai_processor.text_enhancer import TextEnhancer
from src.utils.image_handler import ImageHandler, process_intervention_images_batch
from src.notion.database import NotionDatabaseManager
from src.notion.page_builder import ReportPageBuilder
import config

# Page configuration
st.set_page_config(
    page_title="MERCI RAYMOND - Générateur de Rapports",
    page_icon="🌿",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom CSS
st.markdown("""
<style>
    .main-header {
        font-size: 2.5rem;
        font-weight: bold;
        color: #2E8B57;
        text-align: center;
        margin-bottom: 2rem;
    }
    .success-message {
        background-color: #d4edda;
        border: 1px solid #c3e6cb;
        color: #155724;
        padding: 1rem;
        border-radius: 0.5rem;
        margin: 1rem 0;
    }
    .error-message {
        background-color: #f8d7da;
        border: 1px solid #f5c6cb;
        color: #721c24;
        padding: 1rem;
        border-radius: 0.5rem;
        margin: 1rem 0;
    }
    .info-box {
        background-color: #d1ecf1;
        border: 1px solid #bee5eb;
        color: #0c5460;
        padding: 1rem;
        border-radius: 0.5rem;
        margin: 1rem 0;
    }
</style>
""", unsafe_allow_html=True)

def main():
    """Main Streamlit application."""

    # Header
    st.markdown('<div class="main-header">🌿 Au Rapport RAYMOND ! 🫡</div>', unsafe_allow_html=True)

    # Main content
    col1, col2 = st.columns([2, 1])

    # Initialize session state for dates
    if 'start_date' not in st.session_state:
        st.session_state.start_date = date.today() - timedelta(days=30)
    if 'end_date' not in st.session_state:
        st.session_state.end_date = date.today()

    with col1:
        st.header("📅 Sélection de la Période")

        # Date range selector
        col_start, col_end = st.columns(2)
        with col_start:
            start_date = st.date_input(
                "Date de début",
                value=st.session_state.start_date,
                help="Date de début de la période d'intervention"
            )
            st.session_state.start_date = start_date
        with col_end:
            end_date = st.date_input(
                "Date de fin",
                value=st.session_state.end_date,
                help="Date de fin de la période d'intervention"
            )
            st.session_state.end_date = end_date

        # Validate date range
        if start_date > end_date:
            st.error("❌ La date de début doit être antérieure à la date de fin")
            return

        # Display date range
        st.info(f"📊 Période sélectionnée: {start_date.strftime('%d/%m/%Y')} au {end_date.strftime('%d/%m/%Y')}")

    with col2:
        st.header("⚡ Options Rapides")

        # Quick date presets
        if st.button("📅 Dernière semaine"):
            st.session_state.start_date = date.today() - timedelta(days=7)
            st.session_state.end_date = date.today()
            st.rerun()

        if st.button("📅 Dernier mois"):
            st.session_state.start_date = date.today() - timedelta(days=30)
            st.session_state.end_date = date.today()
            st.rerun()

        if st.button("📅 2 derniers mois"):
            st.session_state.start_date = date.today() - timedelta(days=60)
            st.session_state.end_date = date.today()
            st.rerun()

        if st.button("📅 Trimestre"):
            st.session_state.start_date = date.today() - timedelta(days=90)
            st.session_state.end_date = date.today()
            st.rerun()

    # Client selection
    st.header("👥 Sélection des Clients")

    # Load clients dynamically from Notion
    try:
        config.load_clients_from_notion()
        available_clients = list(config.CLIENT_CHAT_MAPPING.keys())
    except Exception as e:
        # Display full error with traceback for debugging
        error_message = str(e)
        st.error(f"❌ Erreur lors du chargement des clients depuis Notion")
        st.exception(e)  # This shows the full traceback

        # Display debug information if available
        if 'notion_debug' in st.session_state:
            with st.expander("🔍 Informations de débogage"):
                debug_info = st.session_state.notion_debug
                st.json(debug_info)
                if debug_info.get('api_key_present'):
                    st.success("✅ Clé API Notion trouvée")
                else:
                    st.error("❌ Clé API Notion manquante ou invalide")
                if debug_info.get('db_id'):
                    st.info(f"📊 ID Base de données: {debug_info.get('db_id')}")

        available_clients = []

    if not available_clients:
        # More helpful error message with troubleshooting tips
        st.error("❌ Aucun client trouvé dans la base de données Notion.")

        # Show debug info even when no clients found
        if 'notion_debug' in st.session_state:
            with st.expander("🔍 Informations de débogage"):
                debug_info = st.session_state.notion_debug
                st.json(debug_info)

                if debug_info.get('clients_found', 0) == 0:
                    st.warning("⚠️ La requête a réussi mais aucun client n'a été trouvé dans la base de données.")
                    st.info("💡 Vérifiez que:\n- La base de données contient des clients\n- Les clients ont un nom (propriété 'Nom')\n- Les clients ont un canal chat (propriété 'Canal Chat')")
                else:
                    st.info(f"ℹ️ {debug_info.get('clients_found', 0)} client(s) trouvé(s) mais aucun n'a pu être mappé.")
                    st.info("💡 Vérifiez que les clients ont les propriétés requises: 'Nom' et 'Canal Chat'")

        st.info("💡 **Conseils de dépannage:**\n"
                "1. Vérifiez que votre intégration Notion a accès à la base de données\n"
                "2. Vérifiez que la base de données contient des clients\n"
                "3. Vérifiez que les secrets Streamlit sont correctement configurés\n"
                "4. Consultez les logs ci-dessus pour plus de détails")
        return

    # Client selection interface
    col1, col2 = st.columns([3, 1])

    with col1:
        # Select all/none buttons
        col_select_all, col_select_none = st.columns(2)
        with col_select_all:
            if st.button("✅ Tout sélectionner"):
                st.session_state.selected_clients = available_clients
                st.rerun()
        with col_select_none:
            if st.button("❌ Tout désélectionner"):
                st.session_state.selected_clients = []
                st.rerun()

        # Client checkboxes
        if 'selected_clients' not in st.session_state:
            st.session_state.selected_clients = []

        selected_clients = st.multiselect(
            "Sélectionner les clients pour lesquels générer des rapports:",
            options=available_clients,
            default=st.session_state.selected_clients,
            help="Cochez les clients pour lesquels vous souhaitez générer des rapports"
        )

    with col2:
        st.metric("Clients sélectionnés", len(selected_clients))
        st.metric("Période (jours)", (end_date - start_date).days)

    # Generate reports button
    st.header("🚀 Génération des Rapports")

    if st.button("📊 Générer les rapports", type="primary", use_container_width=True):
        if not selected_clients:
            st.error("❌ Veuillez sélectionner au moins un client")
            return

        # Initialize progress tracking
        progress_bar = st.progress(0)
        status_text = st.empty()
        results_container = st.container()

        try:
            # Initialize components
            status_text.text("🔄 Initialisation des composants...")

            # Initialize AI enhancer
            text_enhancer = TextEnhancer()

            # Initialize Notion components
            db_manager = NotionDatabaseManager()
            page_builder = ReportPageBuilder()

            # Initialize Google Chat client
            chat_client = GoogleChatClient()

            # Initialize image handler
            image_handler = ImageHandler(chat_client.service, db_manager.client)

            results = []

            # Process each client
            for i, client_name in enumerate(selected_clients):
                try:
                    status_text.text(f"📊 Traitement: {client_name}")

                    # Get messages for this client
                    messages = get_messages_for_client(
                        client_name,
                        datetime.combine(start_date, datetime.min.time()),
                        datetime.combine(end_date, datetime.max.time())
                    )

                    if not messages:
                        st.warning(f"⚠️ Aucun message trouvé pour {client_name}")
                        results.append({
                            'client': client_name,
                            'status': 'warning',
                            'message': 'Aucun message trouvé'
                        })
                        continue

                    # Apply OFF rule filtering before grouping
                    filtered_messages = apply_off_rule_filtering(messages)

                    if not filtered_messages:
                        st.warning(f"⚠️ Tous les messages ont été exclus par le filtre OFF pour {client_name}")
                        results.append({
                            'client': client_name,
                            'status': 'warning',
                            'message': 'Tous les messages exclus (OFF rule)'
                        })
                        continue

                    # Group messages into interventions
                    interventions = group_messages_by_intervention(filtered_messages)

                    if not interventions:
                        st.warning(f"⚠️ Aucune intervention trouvée pour {client_name}")
                        results.append({
                            'client': client_name,
                            'status': 'warning',
                            'message': 'Aucune intervention trouvée'
                        })
                        continue

                    # Enhance text with AI
                    interventions = text_enhancer.batch_enhance_interventions(interventions)

                    # Process images
                    print(f"🖼️ Processing images for {len(interventions)} interventions...")

                    # Debug: Count total attachments before processing
                    total_attachments = 0
                    for intervention in interventions:
                        total_attachments += len(intervention.get('images', []))
                    print(f"📎 Found {total_attachments} total attachments in interventions")

                    space_id = config.CLIENT_CHAT_MAPPING[client_name]
                    interventions = process_intervention_images_batch(
                        interventions, space_id, chat_client.service, db_manager.client
                    )

                    # Debug: Count processed images after processing
                    total_processed_images = 0
                    for intervention in interventions:
                        total_processed_images += len(intervention.get('notion_images', []))
                    print(f"✅ Processed {total_processed_images} images to Notion")

                    # Extract team information
                    team_members = extract_team_members(messages)
                    team_info = {
                        'jardiniers': [member['name'] for member in team_members],
                        'team_description': f"Équipe de {len(team_members)} jardiniers professionnels"
                    }

                    # Create report page
                    date_range_str = f"{start_date.strftime('%d/%m/%Y')} - {end_date.strftime('%d/%m/%Y')}"
                    report_page_id = page_builder.create_report_page(
                        client_name=client_name,
                        interventions=interventions,
                        team_info=team_info,
                        date_range=date_range_str
                    )

                    # Add individual interventions to database
                    intervention_ids = []
                    for intervention in interventions:
                        # Categorize intervention
                        from src.utils.data_extractor import categorize_intervention_type
                        categorie = categorize_intervention_type(intervention.get('all_text', ''))

                        intervention_data = {
                            'titre': intervention.get('title', 'Intervention de maintenance'),
                            'date': intervention.get('start_time', datetime.now()).isoformat(),
                            'client_name': client_name,
                            'description': intervention.get('enhanced_text', ''),
                            'commentaire_brut': intervention.get('all_text', ''),
                            'responsable': intervention.get('author_name', 'Unknown'),
                            'canal': f"Chat {client_name}",
                            'categorie': categorie,
                            'images': intervention.get('notion_images', [])
                        }
                        intervention_id = db_manager.add_intervention_to_db(intervention_data)
                        if intervention_id:
                            intervention_ids.append(intervention_id)

                    # Link interventions to report
                    if report_page_id and intervention_ids:
                        db_manager.link_interventions_to_report(report_page_id, intervention_ids)

                    results.append({
                        'client': client_name,
                        'status': 'success',
                        'message': f'Rapport généré avec {len(interventions)} interventions',
                        'interventions_count': len(interventions)
                    })

                    st.success(f"✅ {client_name}: Rapport généré avec {len(interventions)} interventions")

                except Exception as e:
                    error_msg = f"Erreur pour {client_name}: {str(e)}"
                    st.error(f"❌ {error_msg}")
                    results.append({
                        'client': client_name,
                        'status': 'error',
                        'message': error_msg
                    })

                # Update progress
                progress_bar.progress((i + 1) / len(selected_clients))

            # Display results
            status_text.text("✅ Génération terminée!")

            with results_container:
                st.header("📋 Résultats de la Génération")

                # Create results DataFrame
                df_results = pd.DataFrame(results)

                if not df_results.empty:
                    # Display results table
                    st.dataframe(df_results, use_container_width=True)

                    # Summary statistics
                    col1, col2, col3 = st.columns(3)

                    with col1:
                        st.metric("Rapports générés", len([r for r in results if r['status'] == 'success']))

                    with col2:
                        st.metric("Avertissements", len([r for r in results if r['status'] == 'warning']))

                    with col3:
                        st.metric("Erreurs", len([r for r in results if r['status'] == 'error']))

                    # Success message
                    if any(r['status'] == 'success' for r in results):
                        st.markdown('<div class="success-message">🎉 Génération des rapports terminée avec succès!</div>', unsafe_allow_html=True)

        except Exception as e:
            st.error(f"❌ Erreur lors de la génération: {str(e)}")
            st.error(f"Détails: {traceback.format_exc()}")

if __name__ == "__main__":
    main()
