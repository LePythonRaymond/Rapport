import streamlit as st
import pandas as pd
from datetime import date, timedelta, datetime
import calendar
import time
import traceback

# Import our modules
from src.google_chat.client import GoogleChatClient, get_messages_for_client
from src.utils.data_extractor import (
    group_messages_by_intervention,
    extract_team_members,
    clean_text,
    apply_on_off_filtering,
)
from src.ai_processor.text_enhancer import TextEnhancer
from src.utils.image_handler import ImageHandler, process_intervention_images_batch
from src.notion.database import NotionDatabaseManager
from src.notion.page_builder import ReportPageBuilder
from src.utils.batch_progress import (
    load_batch_progress,
    save_batch_progress,
    clear_batch_progress,
    progress_matches_period,
)
import config


def get_previous_month_range() -> tuple[date, date]:
    """Return (first_day, last_day) of the previous calendar month."""
    today = date.today()
    first_of_current = today.replace(day=1)
    last_of_previous = first_of_current - timedelta(days=1)
    first_of_previous = last_of_previous.replace(day=1)
    return first_of_previous, last_of_previous

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

def run_generation(
    selected_clients: list,
    start_date: date,
    end_date: date,
    progress_context: dict | None = None,
):
    """Run the full report generation pipeline for the given clients and date range.
    If progress_context is set (bulk run), counter shows X/total and progress is persisted after each client.
    """
    progress_bar = st.progress(0)
    status_text = st.empty()
    results_container = st.container()

    total_for_display = progress_context["total_count"] if progress_context else len(selected_clients)
    completed_list = list(progress_context["completed_clients"]) if progress_context else []
    progress_path = progress_context.get("progress_file_path") if progress_context else None
    period_start = progress_context.get("period_start") if progress_context else start_date
    period_end = progress_context.get("period_end") if progress_context else end_date

    try:
        status_text.text("🔄 Initialisation des composants...")

        text_enhancer = TextEnhancer()
        db_manager = NotionDatabaseManager()
        page_builder = ReportPageBuilder()
        chat_client = GoogleChatClient()
        image_handler = ImageHandler(chat_client.service, db_manager.client)

        results = []

        for i, client_name in enumerate(selected_clients):
            current_global = len(completed_list) + i + 1
            status_text.text(
                f"📊 Traitement: {client_name} ({current_global}/{total_for_display})"
            )
            try:
                messages = get_messages_for_client(
                    client_name,
                    datetime.combine(start_date, datetime.min.time()),
                    datetime.combine(end_date, datetime.max.time())
                )

                if not messages:
                    st.warning(f"⚠️ Aucun message trouvé pour {client_name}")
                    results.append({'client': client_name, 'status': 'warning', 'message': 'Aucun message trouvé'})
                    if progress_context:
                        completed_list.append(client_name)
                        save_batch_progress(
                            progress_path, period_start, period_end,
                            total_for_display, completed_list, client_name
                        )
                    progress_bar.progress(current_global / total_for_display)
                    continue

                filtered_messages = apply_on_off_filtering(messages)

                if not filtered_messages:
                    st.warning(f"⚠️ Tous les messages ont été exclus par le filtre OFF pour {client_name}")
                    results.append({'client': client_name, 'status': 'warning', 'message': 'Tous les messages exclus (OFF rule)'})
                    if progress_context:
                        completed_list.append(client_name)
                        save_batch_progress(
                            progress_path, period_start, period_end,
                            total_for_display, completed_list, client_name
                        )
                    progress_bar.progress(current_global / total_for_display)
                    continue

                interventions = group_messages_by_intervention(filtered_messages)

                if not interventions:
                    st.warning(f"⚠️ Aucune intervention trouvée pour {client_name}")
                    results.append({'client': client_name, 'status': 'warning', 'message': 'Aucune intervention trouvée'})
                    if progress_context:
                        completed_list.append(client_name)
                        save_batch_progress(
                            progress_path, period_start, period_end,
                            total_for_display, completed_list, client_name
                        )
                    progress_bar.progress(current_global / total_for_display)
                    continue

                interventions = text_enhancer.batch_enhance_interventions(interventions)

                total_attachments = sum(len(iv.get('images', [])) for iv in interventions)
                print(f"📎 {client_name}: {total_attachments} pièces jointes trouvées")

                space_id = config.CLIENT_CHAT_MAPPING[client_name]
                interventions = process_intervention_images_batch(
                    interventions, space_id, chat_client.service, db_manager.client
                )

                total_processed = sum(len(iv.get('notion_images', [])) for iv in interventions)
                print(f"✅ {client_name}: {total_processed} images traitées vers Notion")

                team_members = extract_team_members(messages)
                team_info = {
                    'jardiniers': [member['name'] for member in team_members],
                    'team_description': f"Équipe de {len(team_members)} jardiniers professionnels"
                }

                date_range_str = f"{start_date.strftime('%d/%m/%Y')} - {end_date.strftime('%d/%m/%Y')}"
                report_page_id = page_builder.create_report_page(
                    client_name=client_name,
                    interventions=interventions,
                    team_info=team_info,
                    date_range=date_range_str
                )

                from concurrent.futures import ThreadPoolExecutor, as_completed
                from src.utils.data_extractor import categorize_intervention_type

                def _add_single_intervention(intervention, client_name, db_manager):
                    try:
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
                        return db_manager.add_intervention_to_db(intervention_data)
                    except Exception as e:
                        print(f"Error adding intervention to DB: {e}")
                        return None

                intervention_ids = []
                with ThreadPoolExecutor(max_workers=min(5, len(interventions))) as executor:
                    futures = [
                        executor.submit(_add_single_intervention, iv, client_name, db_manager)
                        for iv in interventions
                    ]
                    for future in as_completed(futures):
                        try:
                            iid = future.result()
                            if iid:
                                intervention_ids.append(iid)
                        except Exception as e:
                            print(f"Error in parallel DB write: {e}")

                if report_page_id and intervention_ids:
                    db_manager.link_interventions_to_report(report_page_id, intervention_ids)

                results.append({
                    'client': client_name,
                    'status': 'success',
                    'message': f'Rapport généré avec {len(interventions)} interventions',
                    'interventions_count': len(interventions)
                })
                st.success(f"✅ {client_name}: Rapport généré avec {len(interventions)} interventions")
                if progress_context:
                    completed_list.append(client_name)
                    save_batch_progress(
                        progress_path, period_start, period_end,
                        total_for_display, completed_list, client_name
                    )

            except Exception as e:
                error_msg = f"Erreur pour {client_name}: {str(e)}"
                st.error(f"❌ {error_msg}")
                results.append({'client': client_name, 'status': 'error', 'message': error_msg})

            progress_bar.progress(current_global / total_for_display)

        if progress_context and len(completed_list) == total_for_display:
            clear_batch_progress(progress_path)

        status_text.text("✅ Génération terminée!")

        with results_container:
            st.header("📋 Résultats de la Génération")
            df_results = pd.DataFrame(results)

            if not df_results.empty:
                st.dataframe(df_results, use_container_width=True)

                col1, col2, col3 = st.columns(3)
                with col1:
                    st.metric("Rapports générés", len([r for r in results if r['status'] == 'success']))
                with col2:
                    st.metric("Avertissements", len([r for r in results if r['status'] == 'warning']))
                with col3:
                    st.metric("Erreurs", len([r for r in results if r['status'] == 'error']))

                if any(r['status'] == 'success' for r in results):
                    st.markdown('<div class="success-message">🎉 Génération des rapports terminée avec succès!</div>', unsafe_allow_html=True)

    except Exception as e:
        st.error(f"❌ Erreur lors de la génération: {str(e)}")
        st.error(f"Détails: {traceback.format_exc()}")


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

        prev_start, prev_end = get_previous_month_range()
        prev_month_label = prev_start.strftime("%B %Y").capitalize()
        if st.button(f"📅 {prev_month_label} (mois complet)"):
            st.session_state.start_date = prev_start
            st.session_state.end_date = prev_end
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

    # ─── Bulk one-click section ───────────────────────────────────────────────
    st.divider()
    prev_start, prev_end = get_previous_month_range()
    prev_month_label = prev_start.strftime("%B %Y").capitalize()

    st.subheader(f"⚡ Génération automatique — {prev_month_label}")
    st.caption(
        f"Génère les rapports pour **tous les sites** sur la période "
        f"**{prev_start.strftime('%d/%m/%Y')} → {prev_end.strftime('%d/%m/%Y')}** en un seul clic."
    )

    if st.button(
        f"🗓️ Générer TOUS les rapports de {prev_month_label}",
        type="primary",
        use_container_width=True,
        key="btn_bulk_prev_month"
    ):
        if not available_clients:
            st.error("❌ Aucun client disponible")
        else:
            progress = load_batch_progress()
            if progress and progress_matches_period(progress, prev_start, prev_end):
                completed_set = set(progress.get("completed_clients", []))
                remaining_clients = [c for c in available_clients if c not in completed_set]
                n_done = len(completed_set)
                last_completed = progress.get("last_completed") or "—"
                if not remaining_clients:
                    clear_batch_progress()
                    st.success(f"✅ Tous les rapports de {prev_month_label} ont déjà été générés ({n_done} sites).")
                else:
                    st.info(
                        f"🔄 Reprise: **{n_done}** déjà traités, **{len(remaining_clients)}** restants. "
                        f"Dernier traité: **{last_completed}**."
                    )
                    progress_context = {
                        "total_count": len(available_clients),
                        "completed_clients": list(completed_set),
                        "period_start": prev_start,
                        "period_end": prev_end,
                        "progress_file_path": None,
                    }
                    run_generation(
                        remaining_clients, prev_start, prev_end,
                        progress_context=progress_context,
                    )
            else:
                st.info(f"🚀 Lancement de la génération pour **{len(available_clients)} sites** — {prev_month_label}")
                progress_context = {
                    "total_count": len(available_clients),
                    "completed_clients": [],
                    "period_start": prev_start,
                    "period_end": prev_end,
                    "progress_file_path": None,
                }
                run_generation(
                    available_clients, prev_start, prev_end,
                    progress_context=progress_context,
                )

    # ─── Manual / custom generation ───────────────────────────────────────────
    st.divider()
    st.header("🚀 Génération Personnalisée")

    if st.button("📊 Générer les rapports pour la sélection", type="secondary", use_container_width=True):
        if not selected_clients:
            st.error("❌ Veuillez sélectionner au moins un client")
            return
        run_generation(selected_clients, start_date, end_date)

if __name__ == "__main__":
    main()
