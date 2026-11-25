GITHUB_REPO = "Arhanpg/ShortsLM-Personal-Features"
GITHUB_BRANCH = "main"
GITHUB_FEATURES_PREFIX = "personal_pilot/features"

from google.colab import userdata
import getpass
import requests

# Never hardcode a personal access token in a notebook.
# Store a NEW fine-grained token in Colab Secrets as GH_TOKEN.
try:
    GH_TOKEN = userdata.get("GH_TOKEN")
except Exception:
    GH_TOKEN = None

if not GH_TOKEN:
    GH_TOKEN = getpass.getpass("New GitHub token (hidden): ").strip()
if not GH_TOKEN:
    raise RuntimeError("Missing GH_TOKEN. Add it to Colab Secrets or enter it at the hidden prompt.")

GH_API = "https://api.github.com"
GH_HEADERS = {
    "Authorization": f"Bearer {GH_TOKEN}",
    "Accept": "application/vnd.github+json",
    "X-GitHub-Api-Version": "2022-11-28",
}

repo_response = requests.get(
    f"{GH_API}/repos/{GITHUB_REPO}", headers=GH_HEADERS, timeout=30
)
if repo_response.status_code == 404:
    raise RuntimeError(
        f"GitHub returned 404 for {GITHUB_REPO}. Create this repository as PRIVATE, "
        "or correct GITHUB_REPO. Also ensure GH_TOKEN has access to it."
    )
if repo_response.status_code == 401:
    raise RuntimeError("GitHub rejected the token (401). Replace GH_TOKEN with a valid token.")
if repo_response.status_code == 403:
    raise RuntimeError(
        "GitHub denied access (403). Check fine-grained token repository access "
        "and Contents read/write permission."
    )
repo_response.raise_for_status()

repo_info = repo_response.json()
if repo_info.get("private") is not True:
    raise RuntimeError(
        "The feature-output repository must be PRIVATE because feature JSON can "
        "contain transcript and OCR text."
    )

branch_response = requests.get(
    f"{GH_API}/repos/{GITHUB_REPO}/branches/{GITHUB_BRANCH}",
    headers=GH_HEADERS, timeout=30
)
if branch_response.status_code == 404:
    raise RuntimeError(
        f"Branch {GITHUB_BRANCH!r} does not exist in {GITHUB_REPO}. "
        "Create it or change GITHUB_BRANCH."
    )
branch_response.raise_for_status()
print("Verified private destination:", GITHUB_REPO, GITHUB_BRANCH)

