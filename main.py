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
from src.utils.notion_progress import (
    get_completed_clients_for_run,
    title_month_year_label,
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
    report_date: datetime | None = None,
):
    """Run the full report generation pipeline for the given clients and date range.
    If progress_context is set (bulk run), counter shows X/total and progress is persisted after each client.

    `report_date` (optional) is forwarded to create_report_page so the report
    TITLE month matches the chosen period rather than today's date (avoids the
    day-15 mismatch on bulk runs). Defaults to "now" inside create_report_page.

    Returns the per-client `results` list (each item:
    {client, status: success|warning|error, message, ...}) so the caller can
    classify outcomes — e.g. distinguish a legitimate "no report" (warning)
    from an abnormal failure (error) that should be re-queued.
    """
    progress_bar = st.progress(0)
    status_text = st.empty()
    results_container = st.container()

    total_for_display = progress_context["total_count"] if progress_context else len(selected_clients)
    completed_list = list(progress_context["completed_clients"]) if progress_context else []
    progress_path = progress_context.get("progress_file_path") if progress_context else None
    period_start = progress_context.get("period_start") if progress_context else start_date
    period_end = progress_context.get("period_end") if progress_context else end_date

    results = []
    try:
        status_text.text("🔄 Initialisation des composants...")

        text_enhancer = TextEnhancer()
        db_manager = NotionDatabaseManager()
        page_builder = ReportPageBuilder()
        chat_client = GoogleChatClient()
        image_handler = ImageHandler(chat_client.service, db_manager.client)

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
                    date_range=date_range_str,
                    report_date=report_date,
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

        return results

    except Exception as e:
        st.error(f"❌ Erreur lors de la génération: {str(e)}")
        st.error(f"Détails: {traceback.format_exc()}")
        return results


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
        # Office team comes from Notion too — failures here shouldn't block report
        # generation since is_office_team_* falls back to OFFICE_TEAM_MEMBERS.
        try:
            config.load_team_members_from_notion()
        except Exception as team_err:
            st.warning(f"⚠️ Équipe non chargée depuis Notion (fallback hardcodé utilisé): {team_err}")
        # Sort alphabetically (case-insensitive) so the UI and bulk order are predictable.
        available_clients = sorted(
            config.CLIENT_CHAT_MAPPING.keys(), key=lambda s: s.lower()
        )
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
    # Source of truth for "what's done" = Rapports DB on Notion (durable across
    # Streamlit Cloud container restarts). We chunk the bulk run into batches
    # of CHUNK_SIZE clients and st.rerun() between chunks so each chunk gets a
    # fresh Python process (clean RAM, fresh websocket buffer).
    st.divider()
    prev_start, prev_end = get_previous_month_range()
    prev_month_label = prev_start.strftime("%B %Y").capitalize()

    st.subheader(f"⚡ Génération automatique — {prev_month_label}")
    st.caption(
        f"Génère les rapports pour **tous les sites** sur la période "
        f"**{prev_start.strftime('%d/%m/%Y')} → {prev_end.strftime('%d/%m/%Y')}**. "
        f"Ordre alphabétique. Si l'app s'arrête, recliquez : Notion sait où vous en êtes."
    )

    # Alphabetical, case-insensitive — predictable order so the team knows what's next.
    sorted_clients = sorted(available_clients, key=lambda s: s.lower())

    # The report TITLE month and the completion-detection label both derive from
    # the BULK PERIOD (last day of the previous month), NOT from datetime.now().
    # This keeps period ⇄ title ⇄ completion fully consistent regardless of which
    # day the run happens (kills the day-15 boundary mismatch).
    report_date_dt = datetime.combine(prev_end, datetime.min.time())

    # ─── Session state ─────────────────────────────────────────────────────────
    # bulk_running   : are we mid auto-loop?
    # bulk_attempts  : {site: how many chunks it was processed in this session}
    #                  — bounds retries so a deterministically-failing site can't
    #                    re-queue forever (the original infinite-loop trap).
    # bulk_done      : sites that GOT a report this session (✅ even before the
    #                  next Notion re-query confirms it).
    # bulk_no_data   : {site: reason} — processed, no report for a NORMAL reason
    #                  (no message / 403 / OFF-filtered / no intervention). ⚠️
    # bulk_error     : {site: last error} — processed but FAILED abnormally. ❌
    #                  Re-queued until MAX_ATTEMPTS, then surfaced for the team.
    if "bulk_running" not in st.session_state:
        st.session_state.bulk_running = False
    if "bulk_attempts" not in st.session_state:
        st.session_state.bulk_attempts = {}
    if "bulk_done" not in st.session_state:
        st.session_state.bulk_done = set()
    if "bulk_no_data" not in st.session_state:
        st.session_state.bulk_no_data = {}
    if "bulk_error" not in st.session_state:
        st.session_state.bulk_error = {}

    MAX_ATTEMPTS = 2  # an abnormal failure is retried at most this many times

    # Query Notion for "already has a report for this month" (durable across
    # container restarts). Match is by Client RELATION (page id) scoped to the
    # period's month label, so INT/EXT variants stay distinct. Fail-open.
    from src.notion.database import NotionDatabaseManager
    try:
        _db_manager = NotionDatabaseManager()
        completed_clients = get_completed_clients_for_run(
            _db_manager, sorted_clients, report_date=report_date_dt
        )
        month_label_for_title = title_month_year_label(report_date_dt)
    except Exception as e:
        st.warning(f"⚠️ Impossible de vérifier les rapports existants sur Notion: {e}")
        completed_clients = set()
        month_label_for_title = prev_month_label

    attempts = st.session_state.bulk_attempts
    bulk_done = st.session_state.bulk_done
    bulk_no_data = st.session_state.bulk_no_data
    bulk_error = st.session_state.bulk_error

    def _has_report(c):
        """✅ — a report exists for this month (verified in Notion, or just created)."""
        return c in completed_clients or c in bulk_done

    def _needs_processing(c):
        """In the queue iff: no report yet, not a known normal no-data site, and
        not yet exhausted its retries. So a site that SHOULD have a report but
        doesn't (e.g. it errored) stays queued until it succeeds or hits the cap."""
        if _has_report(c):
            return False
        if c in bulk_no_data:
            return False
        if attempts.get(c, 0) >= MAX_ATTEMPTS:
            return False  # failed too many times — surfaced as ❌, manual retry only
        return True

    def _icon(c):
        if _has_report(c):
            return "✅"
        if c in bulk_no_data:
            return "⚠️"
        if attempts.get(c, 0) >= MAX_ATTEMPTS:
            return "❌"
        if attempts.get(c, 0) > 0:
            return "🔄"  # errored, will retry
        return "⏸"

    remaining_clients = [c for c in sorted_clients if _needs_processing(c)]
    no_data_sites = [c for c in sorted_clients if c in bulk_no_data and not _has_report(c)]
    failed_sites = [
        c for c in sorted_clients
        if not _has_report(c) and c not in bulk_no_data and attempts.get(c, 0) >= MAX_ATTEMPTS
    ]
    n_reports = sum(1 for c in sorted_clients if _has_report(c))

    # ─── Live checklist — always visible so the team can see status at a glance ─
    _header = (
        f"📋 État: {n_reports}/{len(sorted_clients)} rapports générés "
        f"pour « {month_label_for_title} »"
    )
    if no_data_sites:
        _header += f" · {len(no_data_sites)} sans données"
    if failed_sites:
        _header += f" · {len(failed_sites)} ❌ échec"
    with st.expander(_header, expanded=True):
        if not sorted_clients:
            st.info("Aucun site chargé depuis Notion.")
        else:
            st.caption(
                "**Légende** — "
                "✅ rapport généré pour ce mois · "
                "⚠️ aucun rapport (raison normale : aucun message, exclu par le filtre OFF, aucune intervention) · "
                "❌ échec à investiguer (re-mis en file automatiquement puis signalé) · "
                "🔄 erreur, nouvel essai en cours · "
                "⏸ en attente"
            )
            cols = st.columns(3)
            for i, c in enumerate(sorted_clients):
                cols[i % 3].markdown(f"{_icon(c)} {c}")

    # ─── Bulk button + auto-resume loop ────────────────────────────────────────
    CHUNK_SIZE = 5

    def _reset_session_progress():
        st.session_state.bulk_attempts = {}
        st.session_state.bulk_done = set()
        st.session_state.bulk_no_data = {}
        st.session_state.bulk_error = {}

    if not remaining_clients:
        # Nothing left to process this session.
        if failed_sites:
            st.error(
                f"⚠️ Génération terminée avec {len(failed_sites)} échec(s) à investiguer "
                f"(re-essayés {MAX_ATTEMPTS}× sans succès). {n_reports} rapport(s) généré(s)."
            )
            with st.expander("❌ Sites en échec (à investiguer)", expanded=True):
                for c in failed_sites:
                    st.markdown(f"❌ **{c}** — {bulk_error.get(c, 'erreur inconnue')}")
            if st.button("🔁 Réessayer les sites en échec", key="retry_failed"):
                for c in failed_sites:
                    attempts.pop(c, None)
                    bulk_error.pop(c, None)
                st.session_state.bulk_running = True
                st.rerun()
        elif no_data_sites:
            st.success(
                f"✅ Génération terminée. {n_reports} rapport(s) généré(s). "
                f"{len(no_data_sites)} site(s) sans rapport (raison normale)."
            )
            with st.expander("⚠️ Sites sans rapport (aucune donnée)"):
                for c in no_data_sites:
                    st.markdown(f"⚠️ {c} — {bulk_no_data.get(c, 'aucune donnée')}")
            if st.button("🔁 Réessayer les sites sans données", key="retry_no_data"):
                # New messages may have arrived / a 403 may be fixed.
                for c in no_data_sites:
                    attempts.pop(c, None)
                    bulk_no_data.pop(c, None)
                st.session_state.bulk_running = True
                st.rerun()
        else:
            st.success(
                f"🎉 Tous les rapports de {prev_month_label} sont générés "
                f"({n_reports}/{len(sorted_clients)})."
            )
        try:
            clear_batch_progress()
        except Exception:
            pass
    else:
        button_label = (
            f"🗓️ Générer les {len(remaining_clients)} rapports restants de {prev_month_label}"
        )
        if st.button(
            button_label,
            type="primary",
            use_container_width=True,
            key="btn_bulk_prev_month",
            disabled=st.session_state.bulk_running,
        ):
            # Fresh full pass: re-attempt everything that has no report yet.
            _reset_session_progress()
            st.session_state.bulk_running = True
            st.rerun()

    # When bulk_running is true we process ONE chunk per script run, then rerun.
    if st.session_state.bulk_running and remaining_clients:
        chunk = remaining_clients[:CHUNK_SIZE]
        # Count this attempt for the whole chunk BEFORE processing → guarantees
        # forward progress / termination even if run_generation crashes wholesale.
        for c in chunk:
            attempts[c] = attempts.get(c, 0) + 1

        st.info(
            f"🚀 Génération en cours — chunk de {len(chunk)} site(s). "
            f"État global: {n_reports}/{len(sorted_clients)} rapport(s), "
            f"{len(remaining_clients)} site(s) à traiter."
        )

        progress_context = {
            "total_count": len(sorted_clients),
            "completed_clients": list(completed_clients),
            "period_start": prev_start,
            "period_end": prev_end,
            "progress_file_path": None,
        }
        chunk_results = []
        try:
            chunk_results = run_generation(
                chunk, prev_start, prev_end,
                progress_context=progress_context, report_date=report_date_dt,
            ) or []
        except Exception as e:
            # Hard crash: leave the chunk classified as errored (attempts already
            # counted) so it retries up to the cap rather than halting the loop.
            st.error(f"❌ Erreur sur ce chunk ({', '.join(chunk)}): {e}")

        # Classify each site's outcome so the loop knows whether to re-queue it.
        classified = set()
        for r in chunk_results:
            site = r.get("client")
            status = r.get("status")
            msg = r.get("message", "")
            classified.add(site)
            if status == "success":
                bulk_done.add(site)
                bulk_no_data.pop(site, None)
                bulk_error.pop(site, None)
            elif status == "warning":
                bulk_no_data[site] = msg
                bulk_error.pop(site, None)
            else:  # error → keep for retry (or surface as ❌ once attempts hit cap)
                bulk_error[site] = msg
        # Any chunk site with no result row (wholesale crash) counts as an error.
        for c in chunk:
            if c not in classified and c not in bulk_done and c not in bulk_no_data:
                bulk_error[c] = bulk_error.get(c, "Échec inattendu (aucun résultat retourné)")

        # Recompute what still needs processing AFTER this chunk. Because every
        # chunk increments attempts for its sites, this set strictly shrinks and
        # the loop is guaranteed to terminate (≤ ceil(N×MAX_ATTEMPTS/5) reruns).
        still_remaining = [c for c in sorted_clients if _needs_processing(c)]
        if still_remaining:
            st.info("⏭️ Chunk terminé — redémarrage propre pour le chunk suivant…")
            time.sleep(2)
            st.rerun()
        else:
            st.session_state.bulk_running = False
            st.success("🎉 Génération en lot terminée !")
            try:
                clear_batch_progress()
            except Exception:
                pass

    # Escape hatch if the user wants to stop the auto-loop.
    if st.session_state.bulk_running:
        if st.button("⏹ Arrêter la génération automatique", key="stop_bulk"):
            st.session_state.bulk_running = False
            st.rerun()

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
