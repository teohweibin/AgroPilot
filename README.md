# AgroPilot — Autonomous Sales Engineer (CPQ Agent Swarm) 🌾

## Demo mode — no credentials required

The app can be shown safely without connecting to Gemini, Gmail, Salesforce,
DocuSign, Slack, or Tavily. Select **TRY SAMPLE RFQ** for a one-click guided
experience, or paste any RFQ and select **RUN PIPELINE** to see a local
illustrative configuration, audit, and quotation. Demo output is clearly labelled
and the downstream approval action is disabled.

```powershell
cd agropilot
Copy-Item config\.env.example config\.env
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
streamlit run app.py
```

To use live AI output later, set `AGROPILOT_DEMO_MODE=false` and replace the
placeholder values in `config/.env` with real credentials. Keep external actions
disabled until each integration has been tested in its sandbox.

**AgroPilot** is an advanced multi-agent artificial intelligence platform engineered for automated Agricultural Equipment Configuration, Pricing, and Quotation (CPQ).

Built for the **AI Marathon 2026** *(Problem Statement 1: The Autonomous Sales Engineer)*, AgroPilot ingests messy, unformatted, and unstructured inbound dealer or customer Request for Quote (RFQ) emails and orchestrates a stateful multi-agent swarm using **LangGraph** to construct an engineered, conflict-free Bill of Materials (BOM) and verified compliance audits within seconds. 

---

# 🏗️ System Architecture & Workflow

AgroPilot operates as a deterministic state machine managed through a LangGraph workflow. The platform features a 5-stage automated orchestration engine:

## 1️⃣ RFQ Parser (Stage 1)

* Cleans and strips metadata from raw RFQ emails
* Extracts properties, parameters, constraints, and customer requirements
* Converts unstructured text into structured machine-readable data

## 2️⃣ Configurator Agent (Stage 2)

* Engineers a matching Bill of Materials (BOM)
* Cross-references OEM specifications and pricing models
* Generates optimized equipment configurations

## 3️⃣ Critic Agent (Stages 3 & 4)

* Reviews engineering compliance and mechanical compatibility
* Detects hydraulic, engine, or structural conflicts
* Provides correction feedback loops to the Configurator Agent

## 4️⃣ Sentinel Agent (Stage 5)

* Evaluates deal health and financial risk
* Scores gross margin baselines
* Predicts historical conversion probabilities
* Generates intelligent automated up-sell strategies

## 5️⃣ Human-In-The-Loop Approval

* Allows equipment dealers to inspect workflow states
* Supports manual editing and overrides
* Provides analytics dashboards and workflow visibility
* Enables downstream integrations with client ecosystems

---

# 💻 System Requirements

## 🖥️ Supported Operating Systems

* macOS 14+ (Sonoma / Sequoia)
* Ubuntu 22.04 LTS+
* Windows 10 / 11

## 🐍 Python Version

* Python `3.10` or `3.11` (**strict requirement**)

---

# 📦 Dependencies

The following core frameworks are required and managed through `requirements.txt`:

```txt
langgraph>=0.2.0
langchain-google-genai>=1.0.0
langchain-core>=0.2.0
tavily-python>=0.3.0
python-dotenv>=1.0.0
streamlit>=1.35.0
pandas>=2.0.0
```

### Dependency Overview

| Package                  | Purpose                                |
| ------------------------ | -------------------------------------- |
| `langgraph`              | Multi-agent execution orchestration    |
| `langchain-google-genai` | Gemini LLM integration                 |
| `langchain-core`         | Message and state abstraction          |
| `tavily-python`          | Real-time compliance verification      |
| `python-dotenv`          | Secure environment variable management |
| `streamlit`              | Interactive dashboard UI               |
| `pandas`                 | Data processing and visualization      |

---

# 🚀 Installation & Local Setup

Follow the steps below to initialize AgroPilot locally.

---

## Step 1 — Clone the Repository

```bash
git clone <YOUR_PUBLIC_GITHUB_REPOSITORY_LINK>
cd AgroPilot
```

---

## Step 2 — Create a Virtual Environment

### macOS / Linux

```bash
python3 -m venv venv
source venv/bin/activate
```

### Windows (Command Prompt)

```bash
python -m venv venv
.\venv\Scripts\activate
```

### Windows (PowerShell)

```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
```

---

## Step 3 — Install Dependencies

```bash
pip install --upgrade pip
pip install -r requirements.txt
```

---

# ⚙️ Environment Configuration & API Keys

AgroPilot integrates with **6 external APIs** for complete CPQ automation. Each API requires its own credentials.

## Step 1 — Create `.env` File

Create a `.env` file in the `agropilot/` directory:

```bash
cd agropilot
cp .env.example .env
```

Then edit `.env` with your actual API keys (see reference in [.env.example](.env.example)).

---

## Step 2 — Configure Each API

### 1️⃣ **Google Gemini API** (LLM Engine)
**Purpose:** Powers the AI agents' reasoning and decision-making

1. Go to: [Google AI Studio](https://aistudio.google.com/app/apikeys?project=gen-lang-client-0528539577)
2. Click **"Create API Key"**
3. Copy the key and add to `.env`:
   ```env
   GOOGLE_API_KEY=your_gemini_api_key_here
   GEMINI_API_KEY=your_gemini_api_key_here  # Alternative name
   ```

---

### 2️⃣ **Tavily Search API** (Equipment & Compliance Lookup)
**Purpose:** Real-time search for agricultural equipment specs and compliance requirements

1. Go to: [Tavily Home](https://app.tavily.com/home)
2. Sign up and navigate to **API Keys**
3. Copy your API key and add to `.env`:
   ```env
   TAVILY_API_KEY=your_tavily_api_key_here
   ```

---

### 3️⃣ **Google Gmail API** (Quote Delivery)
**Purpose:** Send quotations to dealers via email

**Required OAuth Scopes:**
- `https://www.googleapis.com/auth/gmail.readonly` — Read, list, and parse inbound emails/attachments (for RFQ inbox loading)
- `https://www.googleapis.com/auth/gmail.send` — Send emails with quotes to dealers
- `https://www.googleapis.com/auth/gmail.compose` — Compose and draft emails

**Setup:**
1. Go to: [Google Cloud Console](https://console.cloud.google.com/auth/clients?facet_url=https:%2F%2Fcloud.google.com%2Fcloud-console&project=gen-lang-client-0935180708)
2. Enable **Gmail API**
3. Create **OAuth 2.0 Desktop Client** credentials
4. Download `credential_gmail.json` and save to `agropilot/config`
5. Generate the token (requests all required scopes automatically):
   ```bash
   python config/generate_gmail_token.py
   ```
   This creates `token_gmail.json` with `gmail.readonly`, `gmail.send`, and `gmail.compose` permissions

6. Add to `.env`:
   ```env
   GMAIL_TOKEN_PATH=config/token_gmail.json
   CREDENTIAL_GMAIL_PATH=config/credential_gmail.json
   ```

---

### 4️⃣ **DocuSign API** (E-Signature)
**Purpose:** Send quotes for digital signature

**Required Permissions:**
- `signature` — Send envelope for e-signature
- `impersonation` — Send on behalf of the signer
- Demo/Sandbox permissions for test environment

**Setup:**
1. Go to: [DocuSign Apps & Keys](https://apps-d.docusign.com/admin/authenticate?goTo=appsAndKeys)
2. Create a new **Integration Key**
3. Enable **JWT Bearer Token Flow**
4. Generate and download **RSA Private Key** → save as `docusign_private.pem` in `agropilot/`
5. Add to `.env`:
   ```env
   DOCUSIGN_INTEGRATION_KEY=your_integration_key
   DOCUSIGN_USER_ID=your_user_id
   DOCUSIGN_API_ACCOUNT_ID=your_account_id
   DOCUSIGN_AUTH_SERVER=account-d.docusign.com
   DOCUSIGN_PRIVATE_KEY_PATH=docusign_rsa.pem
   DOCUSIGN_BASE_PATH=https://demo.docusign.net/restapi
   ```

---

### 5️⃣ **Slack API** (Sales Team Notifications)
**Purpose:** Notify sales managers when quotes are ready

**Required Bot Token Scopes:**
- [`app_mentions:read`](https://docs.slack.dev/reference/scopes/app_mentions:read) — View messages that mention the app in conversations
- [`channels:read`](https://docs.slack.dev/reference/scopes/channels:read) — View basic information about public channels
- [`chat:write`](https://docs.slack.dev/reference/scopes/chat:write) — Send messages as the Slack app
- [`chat:write.public`](https://docs.slack.dev/reference/scopes/chat:write.public) — Send messages to channels the app isn't a member of
- [`im:write`](https://docs.slack.dev/reference/scopes/im:write) — Start direct messages with people

**Setup:**
1. Go to: [Slack App Settings](https://app.slack.com/app-settings/T0B7JRYLKU5/A0B7FT2HMCK/oauth)
2. Verify all scopes above are granted under **Bot Token Scopes**
3. Copy **Bot User OAuth Token** (starts with `xoxb-`)
4. Identify **Channel ID** where notifications should post (e.g., `C0B7JRYLKU5`)
5. Add to `.env`:
   ```env
   SLACK_BOT_TOKEN=xoxb-your-bot-token
   SLACK_CHANNEL_ID=C0B7JRYLKU5
   ```

---

### 6️⃣ **Salesforce API** (CRM Integration)
**Purpose:** Log deals and create opportunities in Salesforce

AgroPilot uses **OAuth 2.0 JWT Bearer Token flow** (SOAP login is disabled on your org).

**Required OAuth Scopes:**
- `api` — Manage user data via APIs (create/update records)
- `full` — Full access to the organization
- `refresh_token` — Allow token refresh for long-running sessions

**Required User Profile Permissions:**
- System Administrator or Standard User (with appropriate custom permissions)
- Pre-authorized users via Connected App Plugin Policies

**Setup:**
1. Go to: [Salesforce Connected Apps](https://orgfarm-946eeacba5-dev-ed.develop.my.salesforce-setup.com/lightning/setup/ManageExternalClientApplication/0xIfj0000009EQL/detail)
2. Create **OAuth 2.0 Connected App** with **JWT Bearer Flow** enabled
3. Select OAuth Scopes:
   - ☑️ `api` (Manage user data via APIs)
   - ☑️ `full` (Full access)
   - ☑️ `refresh_token` (Perform requests at any time)
4. Configure **Plugin Policies**: Permitted Users = Admin approved users are pre-authorized
5. Select **Profiles** that can use this app:
   - ☑️ System Administrator
   - ☑️ Standard User
6. Get: **Client ID** from the app details
7. Generate **RSA Private Key** (if not already created):
   - In Salesforce: Setup → Apps → App Manager → your connected app → Edit → Certificates
   - Click **Create Certificate** (or use existing)
   - Download the private key → save as `server_rsa.pem` in `agropilot/`
   - (Optional: The certificate file `server.crt` is not needed for JWT flow)
8. Add to `.env`:
   ```env
   SALESFORCE_CLIENT_ID=your_client_id
   SALESFORCE_USERNAME=your_salesforce_username
   SALESFORCE_LOGIN_URL=https://login.salesforce.com
   SALESFORCE_PRIVATE_KEY_PATH=salesforce_rsa.pem
   ```

**Note:** This uses JWT bearer authentication (not username/password). The private key file (`server_rsa.pem`) is essential and must never be committed to GitHub.

---

## ✅ Verification

Test all APIs are configured correctly:

```bash
cd agropilot
python config/test_api.py
```

This will validate each API connection and display any missing credentials.

---

# 🚀 Running AgroPilot

### Option 1: Interactive Dashboard (Recommended)

```bash
cd agropilot
streamlit run app.py
```

Open: `http://localhost:8501`

### Option 2: Command Line

```bash
cd agropilot
python agent.py
```

---

# 📁 Project Structure

```
agropilot/
├── agent_configuration/
│   ├── agent.py                       # LangGraph multi-agent orchestration
│   └── prompts.py                     # System prompts for all agents
├── config/
│   ├── .env.example                   # Your API keys & credentials (DO NOT COMMIT)
│   ├── .gitignore
│   ├── credential_gmail.example       # Gmail OAuth credentials (DO NOT COMMIT)
│   ├── docusign_private.pem.example   # DocuSign JWT RSA private key (DO NOT COMMIT)
│   ├── generate_gmail_token.py        # Run locally to get gmail token
│   ├── salesforce_rsa.pem.example     # Salesforce JWT RSA private key (DO NOT COMMIT)
│   └── test_api.py                    # API validation script
├── mcp_architecture/
│   ├── mcp_agent.py                   # Post-approval autonomous agent
│   └── mcp_server.py                  # MCP tools (Salesforce, DocuSign, Gmail, Slack, Tavily)
├── parser/
│   ├── gmail_watcher.py
│   └── pipeline_runner.py
├── app.py                             # Streamlit dashboard
├── requirements.txt                   # Python dependencies
├── .gitignore
└── README.md
```

---

# 📝 Setting Up Private Key Files

Three critical files use private keys. Each has an `.example` file you can reference:

### **Salesforce JWT Private Key** (`salesforce_rsa.pem`)
1. View example: [salesforce_rsa.pem.example](agropilot/config/salesforce_rsa.pem.example)
2. Get your actual key from: Salesforce Connected App → Certificates → Download Private Key
3. Save as: `agropilot/config/salesforces_rsa.pem` (your key will look similar to the example, but different)
4. **Never commit** your actual key — it's in `.gitignore`

### **DocuSign Private Key** (`docusign_private.pem`)
1. View example: [docusign_rsa.pem.example](agropilot/config/docusign_rsa.pem.example)
2. Get your actual key from: DocuSign Integration Key → Download Private Key
3. Save as: `agropilot/config/docusign_private.pem` (your key will look similar to the example)
4. **Never commit** your actual key — it's in `.gitignore`

---

# ⚠️ Security Notes

**NEVER commit to GitHub:**
- `.env` — contains all API keys and secrets
- `credential_gmail.json` — Gmail OAuth credentials
- `token_gmail.json` — Gmail OAuth access token
- `docusign_rsae.pem` — DocuSign private key ⚠️ **CRITICAL**
- `salesfoce_rsa.pem` — Salesforce JWT private key ⚠️ **CRITICAL**
- Any API keys, secrets, or authentication tokens

**Safe to commit:**
- `.env.example` — template showing all required variables
- `*.example` files — dummy examples showing file format/structure
- `.gitignore` — protection patterns

These are already configured in `.gitignore`. Double-check before pushing! 🔒

---

# ✨ Key Features

* 🤖 Multi-agent CPQ automation
* 🌾 Agricultural equipment configuration engine
* 📧 Unstructured RFQ parsing
* 🧠 Engineering compliance verification
* 📊 Deal risk and margin analysis
* 🔄 Stateful LangGraph orchestration
* 🖥️ Interactive Streamlit dashboard
* 👨‍💻 Human-in-the-loop validation workflow

---

# 🧩 Tech Stack

| Layer               | Technology |
| ------------------- | ---------- |
| Agent Orchestration | LangGraph  |
| LLM Engine          | Gemini     |
| Backend Framework   | LangChain  |
| Search Verification | Tavily     |
| Dashboard UI        | Streamlit  |
| Data Processing     | Pandas     |

---

# 📌 Project Context

AgroPilot was developed for:

**AI Marathon 2026 — Problem Statement 1: The Autonomous Sales Engineer**

The project focuses on automating complex agricultural equipment sales engineering workflows through intelligent multi-agent systems.

---

# 📄 License

This project is intended for educational, research, and hackathon demonstration purposes.

