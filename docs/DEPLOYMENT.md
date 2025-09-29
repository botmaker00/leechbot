## Deployment Instructions through Google Colab (Heroku)

Follow these steps to deploy Aeon-MLTB to Heroku using Google Colab:

### 1. Open the Colab Notebook
- Click on this link to open the deployment notebook: [Deploy to Heroku via Colab](https://colab.research.google.com/github/AeonOrg/Aeon-MLTB/blob/deploy_extended/Deploy_to_Heroku.ipynb)
- Make sure you're signed in to your Google account.

### 2. Fork and Star the Repository
- Before proceeding with the deployment, fork the [Aeon-MLTB repository](https://github.com/AeonOrg/Aeon-MLTB).
- Give the repository a star to show your support.

### 3. Prepare Required Information
Gather the following information before running the notebook:
- **BOT_TOKEN**: Your Telegram bot token from [@BotFather](https://t.me/BotFather).
- **OWNER_ID**: Your Telegram user ID.
- **DATABASE_URL**: MongoDB connection string.
- **TELEGRAM_API**: Telegram API ID from [my.telegram.org](https://my.telegram.org/).
- **TELEGRAM_HASH**: Telegram API hash from [my.telegram.org](https://my.telegram.org/).
- **HEROKU_APP_NAME**: Desired name for your Heroku app.
- **HEROKU_EMAIL**: Email address associated with your Heroku account.
- **HEROKU_API_KEY**: API key from your Heroku account dashboard.

### 4. Run the Colab Notebook
1. Execute each cell in the notebook sequentially by clicking the play button or using `Shift + Enter`.
2. When prompted, enter the required configuration values.
3. Follow the on-screen instructions provided by the notebook.
4. Wait for the deployment process to complete.

### 5. Finalize Setup
- After successful deployment, your bot will be running on Heroku.
- Configure any additional variables in your Heroku dashboard if needed.
- Use the `/botsettings` command to upload sensitive files like `token.pickle` if needed.

---

## Deployment Instructions through Github Workflow (Heroku)

Follow these steps to deploy Aeon-MLTB to Heroku:

### 1. Fork and Star the Repository
- Click the **Fork** button at the top-right corner of this repository.
- Give the repository a star to show your support.

### 2. Navigate to Your Forked Repository
- Access your forked version of this repository.

### 3. Enable GitHub Actions
- Go to the **Settings** tab of your forked repository.
- Enable **Actions** by selecting the appropriate option in the settings.

### 4. Run the Deployment Workflow
1. Open the **Actions** tab.
2. Select the `Deploy to Heroku` workflow from the available list.
3. Click **Run workflow** and select the branch you want to deploy and fill out the required inputs:
   - **BOT_TOKEN**: Your Telegram bot token.
   - **OWNER_ID**: Your Telegram ID.
   - **DATABASE_URL**: MongoDB connection string.
   - **TELEGRAM_API**: Telegram API ID (from [my.telegram.org](https://my.telegram.org/)).
   - **TELEGRAM_HASH**: Telegram API hash (from [my.telegram.org](https://my.telegram.org/)).
   - **HEROKU_APP_NAME**: Name of your Heroku app.
   - **HEROKU_EMAIL**: Email address associated with your Heroku account.
   - **HEROKU_API_KEY**: API key from your Heroku account.
   - **HEROKU_TEAM_NAME** (Optional): Required only if deploying under a Heroku team account.
4. Run the workflow and wait for it to complete.

### 5. Finalize Setup
- After deployment, configure any remaining variables in your Heroku dashboard.
- Use the `/botsettings` command to upload sensitive files like `token.pickle` if needed.

---

## Deployment Instructions (VPS)

Follow these steps to deploy Aeon to VPS:

### 1. Star the Repository
- Give the repository a star to show your support.

### 2. Clone The Repository
- Clone the repository to your VPS.

```
git clone https://github.com/AeonOrg/Aeon-MLTB.git && cd Aeon-MLTB && git checkout extended
```

### 3. Install Requirements

- For Debian based distros

```
sudo apt install python3 python3-pip
```

Install Docker by following the [official Docker docs](https://docs.docker.com/engine/install/debian/)

- For Arch and it's derivatives:

```
sudo pacman -S docker python
```

- Install dependencies for running setup scripts:

```
pip3 install -r dev/requirements-cli.txt
```

### 4. Setting up config file

```
cp config_sample.py config.py
```

Fill up all the required fields.


### 5. Run the bot

#### Using Docker Compose Plugin

- Install docker compose plugin

```
sudo apt install docker-compose-plugin
```

- Build and run Docker image:

```
sudo docker compose up
```

- After editing files with nano, for example (nano start.sh) or git pull you must use --build to edit container files:

```
sudo docker compose up --build
```

- To stop the running container:

```
sudo docker compose stop
```

- To run the container:

```
sudo docker compose start
```

- To get log from already running container (after mounting the folder):

```
sudo docker compose logs --follow
```

#### Using Official Docker Commands

- Build Docker image:

```
sudo docker build . -t aeon-mltb
```

- Run the image:

```
sudo docker run --network host aeon-mltb
```

- To stop the running image:

```
sudo docker ps
```

```
sudo docker stop id
```

### 6. Open Required Ports:

1. Open all required ports using the shell script:

- Give execute permission & Run the script:

```
sudo chmod +x open_ports.sh
```

```
sudo ./open_ports.sh
```

2. Set `BASE_URL_PORT` and `RCLONE_SERVE_PORT` variables to any port you want to use. Default is `80` and `8080`
   respectively.

3. Check the number of processing units of your machine with `nproc` cmd and times it by 4, then
   edit `AsyncIOThreadsCount` in qBittorrent.conf or while bot working from bsetting->qbittorrent settings.

---

## Heroku CLI Deploy Guide (Windows, Linux, Android)

### Overview
This guide provides step-by-step instructions for deploying Aeon-MLTB to Heroku using the command line interface (CLI) across different platforms. This method deploys the **extended** branch directly to Heroku.

### Prerequisites
- Git installed on your system
- Heroku account
- GitHub account
- Basic terminal/command line knowledge

### Platform-Specific Setup

#### Windows
- Download and install Git from [https://git-scm.com/downloads](https://git-scm.com/downloads)
- Use Command Prompt (CMD) or PowerShell for terminal commands

#### Linux
Install Git using your distribution's package manager:
```bash
sudo apt update && sudo apt install git -y  # Ubuntu/Debian
sudo yum install git -y  # CentOS/RHEL
sudo pacman -S git  # Arch Linux
```

#### Android (Termux)
- Install Termux from [F-Droid](https://f-droid.org/packages/com.termux/)
- Update packages and install Git:
```bash
pkg update -y && pkg install git -y
```

### Step-by-Step Deployment Process

#### 1. Fork and Clone Repository

1. **Fork the Repository**
   - Go to [https://github.com/AeonOrg/Aeon-MLTB](https://github.com/AeonOrg/Aeon-MLTB)
   - Click the **Fork** button to create your own copy
   - Star the repository to show support

2. **Clone Your Fork and Switch to deploy_extended Branch**
```bash
git clone https://github.com/YOUR-GITHUB-USERNAME/Aeon-MLTB.git && cd Aeon-MLTB && git checkout deploy_extended
```
Replace `YOUR-GITHUB-USERNAME` with your actual GitHub username.

#### 2. Configure the Bot

1. **Rename Configuration File**
```bash
mv config_sample.py config.py  # Linux/Android
ren config_sample.py config.py  # Windows
```

2. **Fill Required Configurations**
   Edit `config.py` with your preferred text editor and fill in the necessary configurations:
   - `BOT_TOKEN` - Get from [@BotFather](https://t.me/BotFather)
   - `OWNER_ID` - Your Telegram User ID
   - `TELEGRAM_API` - Get from [my.telegram.org](https://my.telegram.org)
   - `TELEGRAM_HASH` - Get from [my.telegram.org](https://my.telegram.org)
   - `DATABASE_URL` - MongoDB connection string
   - Other optional configurations as needed
   - You can also add your pvt files in the like `token.pickle`, `shorteners.txt`, `cookies.txt`, `accounts.zip`, `rclone.conf`, `list_drives.txt`, `cookies.txt`, `.netrc`, `shorteners.txt`, `streamrip_config.toml`, `zotify_credentials.json` in the root directory of the deploy_extended branch but make sure your repo is private in that case.

#### 3. Commit Changes

```bash
git add . -f && git commit -m "deploy: extended branch deployment"
```

#### 4. Install Heroku CLI

**Linux:**
```bash
sudo apt update -y && sudo apt install curl -y && curl https://cli-assets.heroku.com/install-ubuntu.sh | sh
```

**Windows (CMD/PowerShell):**
```cmd
curl https://cli-assets.heroku.com/install-ubuntu.sh | sh
```

**Android (Termux):**
```bash
pkg update -y && pkg upgrade -y && pkg install -y nodejs git && npm install -g heroku
```

#### 5. Login to Heroku

```bash
heroku login
```
- This will open a browser window for authentication
- If it doesn't open automatically, copy and paste the provided URL

#### 6. Create Heroku Application

**For Personal Account:**
```bash
heroku create your-app-name --region us  # US Region
heroku create your-app-name --region eu  # Europe Region
```

**For Team Account:**
```bash
heroku create your-app-name --team your-team-name --region us  # US Region
heroku create your-app-name --team your-team-name --region eu  # Europe Region
```

Replace `your-app-name` with your desired app name and `your-team-name` with your Heroku team name.

#### 7. Configure Git Remote and Set Container Stack

```bash
heroku git:remote -a YOUR-APP-NAME && heroku stack:set container
```
Replace `YOUR-APP-NAME` with the app name you created in step 7.

#### 8. Deploy Extended Branch to Heroku

```bash
git push heroku deploy:main -f
```

This command pushes your local `deploy` branch (which contains the extended branch code) to Heroku's `main` branch for deployment.

#### 9. Post-Deployment Setup

**Upload Important Files**
   After successful deployment, use the bot's settings to upload sensitive files (ignore if you added before in the root directory of the deploy_extended branch):
   - Go to Bot Settings → Private Files
   - Upload files like:
     - `token.pickle` (Google Drive authentication)
     - `shorteners.txt` (URL shortener configurations)
     - `cookies.txt` (Browser cookies for yt-dlp)
     - `accounts.zip` (Service accounts for Google Drive)
     - `rclone.conf` (Rclone configuration)

### Video Guides

- **Android Guide**: [Telegram Link](https://t.me/AeonDiscussion/80629)
- **Linux Guide**: [Telegram Link](https://t.me/AeonDiscussion/80729)

### Updating Your Deployment

To update your deployed bot with the latest changes:

**Sync with upstream extended branch:**
```bash
git checkout extended && git pull && git push origin extended
```

If any major update comes then redeploy is recommended following the same methods from beginning.

### Important Notes

- This method deploys the **extended** branch directly without merging to main
- Keep your fork updated by regularly syncing with the upstream repository
- Use environment variables or the bot's private file upload feature for sensitive data
- The deployment process may take 5-15 minutes depending on your internet connection and Heroku's build time

---

## Aeon-MLTB Docker Image Build Guide

### Usage

1. **Run the Workflow**  
   - Go to the **Actions** tab in your repository.
   - Select **Docker.io** workflow.
   - Click **Run workflow** and provide:
     - **Docker Hub Username**
     - **Docker Hub Password**
     - **Docker Image Name**

2. **Result**  
   Your Docker image will be available at:  
   `docker.io/<username>/<image_name>:latest`.

### Inputs

| Input        | Description                        |
|--------------|------------------------------------|
| `username`   | Your Docker Hub username           |
| `password`   | Your Docker Hub password           |
| `image_name` | Name of the Docker image to build  |

### Notes

- **Platforms**: Builds for `linux/amd64` and `linux/arm64`.
- **Authentication**: Credentials are securely handled via inputs.

---