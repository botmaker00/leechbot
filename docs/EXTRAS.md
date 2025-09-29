### Getting Google OAuth API credential file and token.pickle

**NOTES:**
- Old authentication changed, now we can't use bot or replit to generate token.pickle. You need OS with a local browser. For example Termux.
- Windows users should install python3 and pip. You can find how to install and use them from google or from this telegraph from Wiszky tutorial.
- You can ONLY open the generated link from generate_drive_token.py in a local browser.

1. Visit the [Google Cloud Console](https://console.cloud.google.com/apis/credentials)
2. Go to the OAuth Consent tab, fill it, and save.
3. Go to the Credentials tab and click Create Credentials -> OAuth Client ID
4. Choose Desktop and Create.
5. Publish your OAuth consent screen App to prevent token.pickle from expiring.
6. Use the download button to download your credentials.
7. Move that file to the root of mirrorbot, and rename it to credentials.json
8. Visit [Google API page](https://console.cloud.google.com/apis/library)
9. Search for Google Drive API and enable it
10. Finally, run the script to generate token.pickle file for Google Drive:

```bash
pip3 install google-api-python-client google-auth-httplib2 google-auth-oauthlib
python3 generate_drive_token.py
```

### Generating rclone.conf

1. Install rclone from [Official Site](https://rclone.org/install/)
2. Create new remote(s) using rclone config command.
3. Copy rclone.conf from your system’s config directory into the repo root. For example:

### Upload

RCLONE_PATH is like GDRIVE_ID a default path for mirror. In additional to those variables DEFAULT_UPLOAD to choose the default tool whether it's rclone or google-api-python-client.

If DEFAULT_UPLOAD = 'rc' then you must fill RCLONE_PATH with path as default one or with rcl to select destination path on each new task.

If DEFAULT_UPLOAD = 'gd' then you must fill GDRIVE_ID with folder/TD id.

rclone.conf can be added before deploy like token.pickle to repo folder root or use bsetting to upload it as private file.

If rclone.conf uploaded from usetting or added in rclone/{user_id}.conf then RCLONE_PATH must start with mrcc:.

Whenever you want to write path manually to use user rclone.conf that added from usetting then you must add the mrcc: at the beginning.

So in short, up: has 4 possible values which are: `gd` (Upload to GDRIVE_ID), `rc` (Upload to RCLONE_PATH), `rcl` (Select Rclone Path) and `rclone_path` (remote:path (owner rclone.conf) or `mrcc`:remote:path (user rclone.conf))

### UPSTREAM REPO (Recommended)

UPSTREAM_REPO variable can be used for edit/add any file in repository.

You can add private/public repository link to grab/overwrite all files from it.

You can skip adding the private files like token.pickle or accounts folder before deploying, simply fill UPSTREAM_REPO private one in case you want to grab all files including private files.

If you added private files while deploying and you have added private UPSTREAM_REPO and your private files in this private repository, so your private files will be overwritten from this repository. Also if you are using database for private files, then all files from database will override the private files that added before deploying or from private UPSTREAM_REPO.

If you filled UPSTREAM_REPO with the official repository link, then be careful incase any change in requirements.txt your bot will not start after restart. In this case you need to deploy again with updated code to install the new requirements or simply by changing the UPSTREAM_REPO to you fork link with that old updates.

In case you you filled UPSTREAM_REPO with your fork link be careful also if you fetched the commits from the official repository.

The changes in your UPSTREAM_REPO will take affect only after restart.

### Bittorrent Seed

Using -d argument alone will lead to use global options for aria2c or qbittorrent.

#### QBittorrent

Global options: GlobalMaxRatio and GlobalMaxSeedingMinutes in qbittorrent.conf, -1 means no limit, but you can cancel manually.

NOTE: Don't change MaxRatioAction.

#### Aria2c

Global options: --seed-ratio (0 means no limit) and --seed-time (0 means no seed) in aria-nox-nzb.sh.

### Using Service Accounts for uploading to avoid user rate limit

> For Service Account to work, you must set USE_SERVICE_ACCOUNTS = "True" in config file or environment variables. NOTE: Using Service Accounts is only recommended while uploading to a Team Drive.

#### 1. Generate Service Accounts. [What is Service Account?](https://cloud.google.com/iam/docs/service-accounts)

Let us create only the Service Accounts that we need. Warning: Abuse of this feature is not the aim of this project and we do NOT recommend that you make a lot of projects, just one project and 100 SAs allow you plenty of use, its also possible that over abuse might get your projects banned by Google.

> NOTE: If you have created SAs in past from this script, you can also just re download the keys by running:

```bash
python3 gen_sa_accounts.py --download-keys $PROJECTID
```

> NOTE: 1 Service Account can upload/copy around 750 GB a day, 1 project can make 100 Service Accounts so you can upload 75 TB a day.

> NOTE: All people can copy 2TB/DAY from each file creator (uploader account), so if you got error userRateLimitExceeded that doesn't mean your limit exceeded but file creator limit have been exceeded which is 2TB/DAY.

Two methods to create service accounts:

##### Method 1: Create Service Accounts in existed Project (Recommended Method)

List your projects ids:

```bash
python3 gen_sa_accounts.py --list-projects
```

Enable services automatically by this command:

```bash
python3 gen_sa_accounts.py --enable-services $PROJECTID
```

Create Service Accounts to current project:

```bash
python3 gen_sa_accounts.py --create-sas $PROJECTID
```

Download Service Accounts as accounts folder:

```bash
python3 gen_sa_accounts.py --download-keys $PROJECTID
```

##### Method 2: Create Service Accounts in New Project

```bash
python3 gen_sa_accounts.py --quick-setup 1 --new-only
```

A folder named accounts will be created which will contain keys for the Service Accounts.

#### 2. Add Service Accounts

Two methods to add service accounts:

##### Method 1: Add Them To Google Group then to Team Drive (Recommended)

Mount accounts folder:

```bash
cd accounts
```

Grab emails form all accounts to emails.txt file that would be created in accounts folder

For Windows using PowerShell:

```powershell
$emails = Get-ChildItem .\**.json |Get-Content -Raw |ConvertFrom-Json |Select -ExpandProperty client_email >>emails.txt
```

For Linux:

```bash
grep -oPh '"client_email": "\K[^"]+' *.json > emails.txt
```

Unmount accounts folder:

```bash
cd ..
```

Then add emails from emails.txt to Google Group, after that add this Google Group to your Shared Drive and promote it to manager and delete email.txt file from accounts folder.

##### Method 2: Add Them To Team Drive Directly

Run:

```bash
python3 add_to_team_drive.py -d SharedTeamDriveSrcID
```

### Create Database

1. Go to https://mongodb.com/ and sign-up.
2. Create Shared Cluster.
3. Press on Database under Deployment Header, your created cluster will be there.
4. Press on connect, choose Allow Access From Anywhere and press on Add IP Address without editing the ip, then create user.
5. After creating user press on Choose a connection, then press on Connect your application. Choose Driver *python* and version 3.12 or later.
6. Copy your connection string and replace <password> with the password of your user, then press close.

### Multi Drive List

To use list from multi TD/folder. Run driveid.py in your terminal and follow it. It will generate list_drives.txt file or u can simply create list_drives.txt file in working directory and fill it, check below format:

```
DriveName folderID/tdID or `root` IndexLink(if available)
DriveName folderID/tdID or `root` IndexLink(if available)
```

Example:

```
TD1 root https://example.dev
TD2 0AO1JDB1t3i5jUk9PVA https://example.dev
```

### Yt-dlp and Aria2c Authentication Using .netrc File

For using your premium accounts in yt-dlp or for protected Index Links, create .netrc file according to following format:

Note: Create .netrc and not netrc, this file will be hidden, so view hidden files to edit it after creation.

Format:

```
machine host login username password my_password
```

Using Aria2c you can also use built in feature from bot with or without username. Here example for index link without username.

```
machine example.workers.dev password index_password
```

Where host is the name of extractor (eg. instagram, Twitch). Multiple accounts of different hosts can be added each separated by a new line.

Yt-dlp: Authentication using cookies.txt file. CREATE IT IN INCOGNITO TAB.