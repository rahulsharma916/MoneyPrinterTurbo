#!/usr/bin/env python3
"""Fetch read-only YouTube Analytics reports for one explicitly configured channel."""
from __future__ import annotations
import argparse, base64, hashlib, json, os, secrets, sys, threading, urllib.error, urllib.parse, urllib.request, webbrowser
from datetime import date, datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG = Path(__file__).with_name("channel_configs.json")
SCOPES = ("https://www.googleapis.com/auth/youtube.readonly", "https://www.googleapis.com/auth/yt-analytics.readonly")
TOKEN_ROOT = Path.home() / ".config" / "mpt" / "youtube-analytics"
API_ROOT = "https://www.googleapis.com"
USER_AGENT = "MoneyPrinterTurbo-ReadOnly-YouTube-Analytics/1.0"

def parse_date(value: str) -> date:
    try: return date.fromisoformat(value)
    except (TypeError, ValueError) as exc: raise ValueError(f"invalid date {value!r}; use YYYY-MM-DD") from exc

def default_date_range(today: date | None = None) -> tuple[str, str]:
    end = (today or date.today()) - timedelta(days=1)
    return (end - timedelta(days=27)).isoformat(), end.isoformat()

def validate_date_range(start: str, end: str) -> tuple[str, str]:
    first, last = parse_date(start), parse_date(end)
    if first > last: raise ValueError("start date must be on or before end date")
    if last >= date.today(): raise ValueError("end date must be before today; recent Analytics data can be delayed")
    return first.isoformat(), last.isoformat()

def load_channel_config(channel: str, config_path: Path = DEFAULT_CONFIG) -> dict[str, Any]:
    try: config = json.loads(config_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc: raise ValueError(f"cannot read channel configuration: {exc}") from exc
    channels = config.get("channels") if isinstance(config, dict) else None
    profile = channels.get(channel) if isinstance(channels, dict) else None
    if not isinstance(profile, dict): raise ValueError(f"unknown channel: {channel}")
    channel_id, analytics = profile.get("youtube_channel_id"), profile.get("analytics")
    if not isinstance(channel_id, str) or not channel_id.strip(): raise ValueError(f"{channel}: set the verified YouTube channel ID in {config_path}")
    if not isinstance(analytics, dict): raise ValueError(f"{channel}: analytics configuration is missing")
    env_name = analytics.get("oauth_client_secrets_env")
    if not isinstance(env_name, str) or not env_name.startswith("MPT_"): raise ValueError(f"{channel}: invalid OAuth client-secrets environment-variable name")
    return {"channel": channel, "display_name": str(profile.get("display_name") or channel), "channel_id": channel_id.strip(), "client_secrets_env": env_name}

def _read_json(path: Path) -> dict[str, Any]:
    try: value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc: raise ValueError(f"cannot read OAuth JSON file {path}: {exc}") from exc
    if not isinstance(value, dict): raise ValueError(f"OAuth JSON file must contain an object: {path}")
    return value

def _save_token(path: Path, token: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(token, indent=2), encoding="utf-8")
    try: os.chmod(temporary, 0o600)
    except OSError: pass
    temporary.replace(path)
    try: os.chmod(path, 0o600)
    except OSError: pass

def _post_form(url: str, data: dict[str, str]) -> dict[str, Any]:
    request = urllib.request.Request(url, data=urllib.parse.urlencode(data).encode("utf-8"), headers={"Content-Type": "application/x-www-form-urlencoded", "User-Agent": USER_AGENT}, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=30) as response: payload = json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc: raise RuntimeError(f"Google OAuth token request failed: {exc}") from exc
    if not isinstance(payload, dict) or "access_token" not in payload:
        detail = (payload.get("error_description") or payload.get("error")) if isinstance(payload, dict) else "invalid response"
        raise RuntimeError(f"Google OAuth did not return an access token: {detail}")
    payload["obtained_at"] = int(datetime.now(timezone.utc).timestamp())
    return payload

def _authorize(client: dict[str, Any]) -> dict[str, Any]:
    state, verifier = secrets.token_urlsafe(24), secrets.token_urlsafe(48)
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode("ascii")).digest()).rstrip(b"=").decode("ascii")
    received: dict[str, str] = {}
    ready = threading.Event()
    class CallbackHandler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            query = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
            received.update(state=query.get("state", [""])[0], code=query.get("code", [""])[0], error=query.get("error", [""])[0])
            self.send_response(200); self.send_header("Content-Type", "text/html; charset=utf-8"); self.end_headers()
            self.wfile.write(b"<html><body><h2>YouTube Analytics authorization received.</h2><p>Return to the terminal.</p></body></html>")
            ready.set()
        def log_message(self, *_: Any) -> None: return
    server = HTTPServer(("127.0.0.1", 0), CallbackHandler); server.timeout = 180
    redirect_uri = f"http://127.0.0.1:{server.server_port}/"
    params = {"client_id": client["client_id"], "redirect_uri": redirect_uri, "response_type": "code", "scope": " ".join(SCOPES), "access_type": "offline", "prompt": "consent", "state": state, "code_challenge": challenge, "code_challenge_method": "S256"}
    url = client.get("auth_uri", "https://accounts.google.com/o/oauth2/auth") + "?" + urllib.parse.urlencode(params)
    print("Opening Google authorization. Sign in to the intended YouTube channel account.")
    print("If the browser does not open, visit this URL:\n" + url); webbrowser.open(url)
    try: server.handle_request()
    finally: server.server_close()
    if not ready.is_set() or received.get("state") != state: raise RuntimeError("OAuth callback was not received or state validation failed")
    if received.get("error"): raise RuntimeError(f"Google OAuth authorization failed: {received['error']}")
    if not received.get("code"): raise RuntimeError("Google OAuth callback did not contain an authorization code")
    return _post_form(client.get("token_uri", "https://oauth2.googleapis.com/token"), {"code": received["code"], "client_id": client["client_id"], "client_secret": client["client_secret"], "redirect_uri": redirect_uri, "grant_type": "authorization_code", "code_verifier": verifier})

def get_access_token(channel_config: dict[str, Any], reauthorize: bool = False) -> str:
    env_name = channel_config["client_secrets_env"]; client_path = os.environ.get(env_name, "").strip()
    if not client_path: raise ValueError(f"set {env_name} to the local path of your Google OAuth Desktop app JSON")
    client_data = _read_json(Path(client_path).expanduser()); client = client_data.get("installed") or client_data.get("web")
    if not isinstance(client, dict) or not client.get("client_id") or not client.get("client_secret"): raise ValueError("OAuth client JSON must be a Google Desktop app or Web application client")
    token_path = TOKEN_ROOT / f"{channel_config['channel']}.json"; token = {}
    if token_path.exists() and not reauthorize: token = _read_json(token_path)
    now = int(datetime.now(timezone.utc).timestamp())
    if token.get("access_token") and int(token.get("expires_at", 0)) > now + 60: return str(token["access_token"])
    refresh_token = token.get("refresh_token")
    if refresh_token and not reauthorize:
        refreshed = _post_form(client.get("token_uri", "https://oauth2.googleapis.com/token"), {"client_id": client["client_id"], "client_secret": client["client_secret"], "refresh_token": str(refresh_token), "grant_type": "refresh_token"})
        refreshed["refresh_token"] = refresh_token; refreshed["expires_at"] = int(refreshed["obtained_at"]) + int(refreshed.get("expires_in", 3600)); _save_token(token_path, refreshed)
        return str(refreshed["access_token"])
    token = _authorize(client)
    if not token.get("refresh_token") and not refresh_token: raise RuntimeError("Google returned no refresh token. Re-run with --reauthorize and approve offline access.")
    token["refresh_token"] = token.get("refresh_token") or refresh_token; token["expires_at"] = int(token["obtained_at"]) + int(token.get("expires_in", 3600)); _save_token(token_path, token)
    return str(token["access_token"])

def _get_json(url: str, access_token: str) -> dict[str, Any]:
    request = urllib.request.Request(url, headers={"Authorization": f"Bearer {access_token}", "Accept": "application/json", "User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(request, timeout=45) as response: result = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        try: detail = json.loads(body).get("error", {}).get("message", body)
        except (json.JSONDecodeError, AttributeError): detail = body
        raise RuntimeError(f"YouTube API returned HTTP {exc.code}: {detail}") from exc
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc: raise RuntimeError(f"YouTube API request failed: {exc}") from exc
    if not isinstance(result, dict): raise RuntimeError("YouTube API returned an unexpected response")
    return result

def verify_channel(access_token: str, expected_channel_id: str) -> dict[str, str]:
    query = urllib.parse.urlencode({"part": "id,snippet", "mine": "true"})
    response = _get_json(f"{API_ROOT}/youtube/v3/channels?{query}", access_token); items = response.get("items") or []
    if len(items) != 1: raise RuntimeError("Could not identify exactly one YouTube channel for this Google account")
    item = items[0]; actual_id = item.get("id", "")
    if actual_id != expected_channel_id: raise RuntimeError(f"Channel identity mismatch: configured {expected_channel_id}, authenticated {actual_id}. No analytics were fetched.")
    return {"channel_id": actual_id, "title": str(item.get("snippet", {}).get("title") or "")}

def query_report(access_token: str, start: str, end: str, metrics: str, **extra: str) -> dict[str, Any]:
    params = {"ids": "channel==MINE", "startDate": start, "endDate": end, "metrics": metrics, **extra}
    return _get_json(f"{API_ROOT}/youtube/analytics/v2/reports?" + urllib.parse.urlencode(params), access_token)

def rows_as_objects(report: dict[str, Any]) -> list[dict[str, Any]]:
    headers = [item.get("name", "") for item in report.get("columnHeaders", [])]
    return [dict(zip(headers, row)) for row in report.get("rows", [])]

def collect_analytics(access_token: str, start: str, end: str) -> dict[str, Any]:
    daily = query_report(access_token, start, end, "views,engagedViews,estimatedMinutesWatched,averageViewDuration,averageViewPercentage,subscribersGained,subscribersLost,likes,comments,shares", dimensions="day,creatorContentType", sort="day")
    top = query_report(access_token, start, end, "views,estimatedMinutesWatched,averageViewDuration,averageViewPercentage,subscribersGained", dimensions="video", sort="-estimatedMinutesWatched", maxResults="50")
    traffic = query_report(access_token, start, end, "views,estimatedMinutesWatched", dimensions="insightTrafficSourceType", sort="-views", maxResults="25")
    return {"daily": rows_as_objects(daily), "top_videos": rows_as_objects(top), "traffic_sources": rows_as_objects(traffic)}

def build_output(channel: dict[str, Any], identity: dict[str, str], start: str, end: str, reports: dict[str, Any]) -> dict[str, Any]:
    return {"schema_version": 1, "generated_at": datetime.now(timezone.utc).isoformat(), "channel": channel["channel"], "channel_display_name": channel["display_name"], "verified_youtube_channel": identity, "date_range": {"start": start, "end": end}, "scope": "read-only YouTube Analytics; no publishing or channel mutations", "reports": reports, "limitations": ["Thumbnail impressions and click-through rate are not included in these targeted reports; use the YouTube Reporting API reach report for those metrics.", "Audience-retention curves are not included in this initial report.", "YouTube Analytics data can be delayed and may be adjusted by YouTube."]}

def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__); parser.add_argument("--channel", required=True, choices=("devotional", "motivation")); parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--start-date"); parser.add_argument("--end-date"); parser.add_argument("--output", type=Path); parser.add_argument("--reauthorize", action="store_true")
    args = parser.parse_args()
    try:
        channel = load_channel_config(args.channel, args.config); ds, de = default_date_range()
        start, end = validate_date_range(args.start_date or ds, args.end_date or de)
        token = get_access_token(channel, args.reauthorize); identity = verify_channel(token, channel["channel_id"])
        reports = collect_analytics(token, start, end); result = build_output(channel, identity, start, end, reports)
        output = (args.output or ROOT / "storage" / "analytics" / f"{args.channel}_{start}_{end}.json").expanduser().resolve()
        output.parent.mkdir(parents=True, exist_ok=True); output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"Analytics report saved: {output}"); print(f"Verified channel: {identity['title']} ({identity['channel_id']})")
        print(f"Daily rows: {len(reports['daily'])}; top videos: {len(reports['top_videos'])}; traffic sources: {len(reports['traffic_sources'])}")
        return 0
    except (ValueError, RuntimeError, OSError) as exc:
        print(f"Analytics report not generated: {exc}", file=sys.stderr); return 2

if __name__ == "__main__": raise SystemExit(main())
