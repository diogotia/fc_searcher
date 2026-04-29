#!/usr/bin/env bash
# Facebook Login → short-lived user token with scopes useful for group monitoring.
# Requires: project .env with FACEBOOK_APP_ID, FACEBOOK_APP_SECRET; Meta app must list
# the same redirect URI the Python script prints (default http://127.0.0.1:8765/oauth/facebook-callback).
#
# Override scopes: FACEBOOK_OAUTH_SCOPES=public_profile,email ./scripts/oauth_facebook_user_token_groups.sh
# Names change by API version — confirm in Meta Developer docs for GRAPH_API_VERSION in your .env.

set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

SCOPES="${FACEBOOK_OAUTH_SCOPES:-public_profile,groups_access_member_info}"
exec python3 scripts/oauth_facebook_user_token.py --open-browser --scopes "$SCOPES"
