# Setup Guide - Gardening Report Automation System

This guide will walk you through setting up the automated gardening intervention report system for MERCI RAYMOND.

## Prerequisites

- Python 3.8 or higher
- A Google account with access to Google Chat
- A Notion account
- An OpenAI or Anthropic API key

## Step 1: Clone and Setup Python Environment

```bash
# Navigate to your project directory
cd "/Users/taddeocarpinelli/Desktop/MERCI RAYMOND/Rapport_2"

# Create virtual environment
python -m venv venv

# Activate virtual environment
# On macOS/Linux:
source venv/bin/activate
# On Windows:
# venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
```

## Step 2: Google Cloud Console Setup

### 2.1 Create Google Cloud Project

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Click "Select a project" → "New Project"
3. Name: "MERCI RAYMOND Report Automation"
4. Click "Create"

### 2.2 Enable Google Chat API

1. In the Google Cloud Console, go to "APIs & Services" → "Library"
2. Search for "Google Chat API"
3. Click on it and press "Enable"

### 2.3 Create OAuth 2.0 Credentials

1. Go to "APIs & Services" → "Credentials"
2. Click "Create Credentials" → "OAuth client ID"
3. If prompted, configure the OAuth consent screen:
   - Choose "External" user type
   - Fill in app name: "MERCI RAYMOND Report System"
   - Add your email as developer contact
   - Add scopes: `https://www.googleapis.com/auth/chat.spaces.readonly` and `https://www.googleapis.com/auth/chat.messages.readonly`
4. For Application type, choose "Desktop application"
5. Name: "Report Automation Client"
6. Click "Create"
7. Download the JSON credentials file
8. Save it as `credentials.json` in your project root

## Step 3: Notion Setup

### 3.1 Create Notion Integration

1. Go to [Notion Integrations](https://www.notion.so/my-integrations)
2. Click "New integration"
3. Name: "MERCI RAYMOND Report Automation"
4. Select your workspace
5. Click "Submit"
6. Copy the "Internal Integration Token" (starts with `secret_`)

### 3.2 Create Notion Databases

Create THREE databases in your Notion workspace:

#### Database 1: "Clients" (Nouveau - Central Hub)
Properties:
- **Nom** (Titre) - Nom du client/site
- **Interventions** (Relation vers Interventions)
- **Rapports** (Relation vers Rapports)
- **  ** (Texte) - Ex: "spaces/AAAAAXFFz5A"
- **Statut** (Sélection: Actif, Inactif)
- **Contact** (Texte) - Personne de contact
- **Adresse** (Texte) - Adresse du site

#### Database 2: "Interventions"
Properties:
- **Titre** (Titre) - Titre généré par l'IA
- **Date** (Date) - Date de l'intervention
- **Client** (Relation vers Clients) - Lien vers le client
- **Description** (Texte enrichi) - Description améliorée par l'IA (1-2 phrases)
- **Commentaire Brut** (Texte enrichi) - Texte original du chat
- **Images** (Fichiers et médias) - Photos associées
- **Responsable** (Texte) - Personne en charge (jardinier)
- **Canal** (Texte) - Nom du canal de chat source
- **Catégorie** (Sélection: Taille, Désherbage, Arrosage, Nettoyage, Plantation, Autre)

#### Database 3: "Rapports"
Properties:
- **Nom** (Titre) - Titre du rapport
- **Client** (Relation vers Clients) - Lien vers le client
- **ID Unique** (Texte) - Identifiant unique du rapport
- **Date de Création** (Date de création - auto) - Date de création automatique
- **URL Page** (URL) - URL de la page publique Notion
- **Statut** (Sélection: Brouillon, Publié, Archivé)
- **Interventions** (Relation vers Interventions) - Interventions liées
- **Date Début** (Date) - Date de début de la période
- **Date Fin** (Date) - Date de fin de la période
- **Période** (Formule) - Calcul automatique: `formatDate(prop("Date de Création"), "MMMM YYYY")`
- **Nombre Interventions** (Rollup depuis Interventions, count) - Nombre d'interventions

### 3.3 Get Database IDs

1. Open each database in Notion
2. Copy the database ID from the URL:
   - URL format: `https://www.notion.so/workspace/DATABASE_ID?v=...`
   - The database ID is the 32-character string before the `?v=`

### 3.4 Share Databases with Integration

1. In each database, click "Share" in the top right
2. Click "Invite" and search for your integration name
3. Give it "Can edit" permissions

## Step 4: AI API Setup

### Option A: OpenAI (Recommended)

1. Go to [OpenAI API Keys](https://platform.openai.com/api-keys)
2. Click "Create new secret key"
3. Name: "MERCI RAYMOND Reports"
4. Copy the API key (starts with `sk-`)

### Option B: Anthropic Claude

1. Go to [Anthropic Console](https://console.anthropic.com/)
2. Navigate to "API Keys"
3. Click "Create Key"
4. Copy the API key (starts with `sk-ant-`)

## Step 5: Environment Configuration

### 5.1 Create .env file

Copy `.env.example` to `.env` and fill in your values:

```bash
cp .env.example .env
```

Edit `.env` with your actual values:

```env
# Google API Configuration
GOOGLE_CREDENTIALS_PATH=credentials.json

# Notion API Configuration
NOTION_API_KEY=secret_your_notion_token_here
NOTION_DATABASE_ID_CLIENTS=your_clients_database_id
NOTION_DATABASE_ID_RAPPORTS=your_rapports_database_id
NOTION_DATABASE_ID_INTERVENTIONS=your_interventions_database_id

# AI API Configuration (choose one)
OPENAI_API_KEY=sk-your_openai_key_here
# ANTHROPIC_API_KEY=sk-ant-your_anthropic_key_here
```

### 5.2 Configure Client-Chat Mapping

The system now loads clients dynamically from the Notion Clients database. You need to:

1. **Add clients to the Clients database in Notion** with their chat space IDs
2. **Use the URL extraction utility** for your Google Chat URLs

Your Google Chat URL format: `https://mail.google.com/chat/u/0/#chat/space/AAAAAXFFz5A`

The system automatically extracts the space ID using the `extract_space_id_from_url()` function in `config.py`.

**To add a client:**
1. Go to your Clients database in Notion
2. Click "New" to create a new client
3. Fill in:
   - **Nom**: Client name (e.g., "Site ABC")
   - **Canal Chat**: Your full Google Chat URL (e.g., `https://mail.google.com/chat/u/0/#chat/space/AAAAAXFFz5A`)
   - **Statut**: "Actif"
   - **Contact**: Contact person name
   - **Adresse**: Site address

The system will automatically extract the space ID from your URL format.

## Step 6: First Run and Authentication

### 6.1 Run the Application

```bash
streamlit run main.py
```

### 6.2 Complete Google OAuth Flow

On first run, the application will:
1. Open your browser for Google OAuth authentication
2. Ask you to sign in and grant permissions
3. Save the authentication token for future use

## Step 7: Test the System

### 7.1 Test with One Client

1. Open the Streamlit interface
2. Select a date range (last 7 days)
3. Select one client
4. Click "Générer les rapports"
5. Check your Notion databases for the generated report

### 7.2 Verify Output

- Check the "Rapports" database for a new entry
- Click on the report page to see the generated content
- Verify images are properly embedded
- Check the "Interventions" database for individual intervention records

## Troubleshooting

### Common Issues

**"Authentication failed"**
- Ensure `credentials.json` is in the project root
- Check that Google Chat API is enabled
- Verify OAuth scopes include chat permissions

**"Notion API error"**
- Verify your integration token is correct
- Check that databases are shared with the integration
- Ensure database IDs are correct (32 characters)

**"OpenAI API error"**
- Verify your API key is correct
- Check you have sufficient credits
- Ensure the model name is correct in config.py

**"No messages found"**
- Verify the space ID is correct
- Check that the date range contains messages
- Ensure you have access to the Google Chat space

### Getting Help

If you encounter issues:
1. Check the console output for error messages
2. Verify all environment variables are set correctly
3. Test each API individually (Google Chat, Notion, OpenAI)
4. Check that all required permissions are granted

## Security Notes

- Never commit `.env` or `credentials.json` to version control
- Keep your API keys secure and rotate them regularly
- Use environment variables for production deployments
- Consider using a secrets management service for production

## Next Steps

Once setup is complete:
1. Test with a small date range and one client
2. Review the generated report quality
3. Adjust AI prompts if needed (in `src/ai_processor/prompts.py`)
4. Scale up to multiple clients and longer date ranges
5. Set up automated scheduling if desired

## Support

For technical support or questions about this setup, refer to:
- [Google Chat API Documentation](https://developers.google.com/chat/api)
- [Notion API Documentation](https://developers.notion.com/)
- [OpenAI API Documentation](https://platform.openai.com/docs)
- [Streamlit Documentation](https://docs.streamlit.io/)
