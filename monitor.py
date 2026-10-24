from datetime import datetime, timedelta
import json
import os
import sys
import pytz
import requests

CONFIG_FILE = "config.json"
TRACKED_FILE = "tracked_shows.json"
HISTORY_FILE = "history.json"


def load_json(filepath, default):
    if not os.path.exists(filepath):
        return default
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print(f"Błąd odczytu {filepath}: {e}")
        return default


def save_json(filepath, data):
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def get_pl_vod_providers(api_key, show_id):
    url = f"https://api.themoviedb.org/3/tv/{show_id}/watch/providers"
    try:
        res = requests.get(url, params={"api_key": api_key}, timeout=10)
        data = res.json()
        pl_providers = (
            data.get("results", {}).get("PL", {}).get("flatrate", [])
        )
        names = [p["provider_name"] for p in pl_providers]
        return ", ".join(names) if names else "Brak danych o VOD w PL"
    except Exception:
        return "Brak danych o VOD"


def send_discord_embed(webhook_url, embed_data):
    if not webhook_url or not webhook_url.startswith("http"):
        print("Brak poprawnego adresu URL webhooka.")
        return False
    payload = {"embeds": [embed_data]}
    try:
        res = requests.post(webhook_url, json=payload, timeout=10)
        return res.status_code in [200, 204]
    except Exception as e:
        print(f"Błąd wysyłania na Discord: {e}")
        return False


def run_monitor():
    config = load_json(CONFIG_FILE, {})
    tracked = load_json(TRACKED_FILE, [])
    history = load_json(HISTORY_FILE, [])

    api_key = config.get("tmdb_api_key", "").strip()
    webhooks = config.get("webhooks", {})
    new_series_wh = webhooks.get("new_series", "")
    returning_wh = webhooks.get("returning_series", "")
    days_ahead = config.get("check_days_ahead", 7)

    if not api_key:
        print("Brak klucza TMDB API w config.json!")
        sys.exit(1)

    if not tracked:
        print("Brak seriali w tracked_shows.json. Zakończono.")
        return

    tz_warsaw = pytz.timezone("Europe/Warsaw")
    today = datetime.now(tz_warsaw).date()
    max_check_date = today + timedelta(days=days_ahead)

    print(
        f"Uruchomiono sprawdzanie premier. Zakres: od {today} do {max_check_date}"
    )
    print(f"Liczba obserwowanych seriali: {len(tracked)}")

    alerts_sent = 0

    for show in tracked:
        show_id = show["id"]
        show_name = show.get("title", f"Serial {show_id}")

        url = f"https://api.themoviedb.org/3/tv/{show_id}"
        try:
            res = requests.get(
                url,
                params={"api_key": api_key, "language": "pl-PL"},
                timeout=10,
            )
            data = res.json()
        except Exception as e:
            print(f"Nie udało się pobrać danych dla {show_name} ({show_id}): {e}")
            continue

        next_ep = data.get("next_episode_to_air")
        if not next_ep:
            continue

        air_date_str = next_ep.get("air_date")
        if not air_date_str:
            continue

        try:
            air_date = datetime.strptime(air_date_str, "%Y-%m-%d").date()
        except ValueError:
            continue

        # Sprawdzamy czy emisja mieści się w zadanym oknie
        if not (today <= air_date <= max_check_date):
            continue

        season_num = next_ep.get("season_number", 1)
        episode_num = next_ep.get("episode_number", 1)
        alert_id = f"{show_id}_S{season_num:02d}E{episode_num:02d}_{air_date_str}"

        if alert_id in history:
            continue

        # Weryfikacja: premiera nowego serialu (S01E01) lub premiera kolejnego sezonu (S02+E01)
        is_new_series = season_num == 1 and episode_num == 1
        is_returning = season_num > 1 and episode_num == 1

        if not (is_new_series or is_returning):
            continue

        # Przygotowanie metadanych do Embedu
        ep_name = next_ep.get("name") or f"Odcinek {episode_num}"
        overview = (
            next_ep.get("overview")
            or data.get("overview")
            or "Brak polskiego opisu fabuły w bazie TMDB."
        )
        if len(overview) > 400:
            overview = overview[:397] + "..."

        poster_path = data.get("poster_path")
        poster_url = (
            f"https://image.tmdb.org/t/p/w500{poster_path}"
            if poster_path
            else None
        )

        networks = [n["name"] for n in data.get("networks", [])] or [
            "Brak danych"
        ]
        network_str = ", ".join(networks[:2])
        vod_pl = get_pl_vod_providers(api_key, show_id)

        # Znacznik czasu Discorda
        dt_air = datetime(air_date.year, air_date.month, air_date.day, 20, 0, 0)
        dt_air_localized = tz_warsaw.localize(dt_air)
        unix_ts = int(dt_air_localized.timestamp())

        if is_new_series:
            title_prefix = "🟢 NOWY SERIAL - PREMIERA PILOTA"
            color = 0x2ECC71  # Zielony
            target_webhook = new_series_wh
        else:
            title_prefix = f"🔵 PREMIERA SEZONU {season_num}"
            color = 0x3498DB  # Niebieski
            target_webhook = returning_wh

        embed = {
            "title": f"{title_prefix}: {show_name}",
            "description": overview,
            "color": color,
            "fields": [
                {
                    "name": "🎬 Epizod",
                    "value": f"Sezon {season_num}, Odcinek {episode_num}\n*„{ep_name}”*",
                    "inline": True,
                },
                {
                    "name": "📅 Data premiery",
                    "value": f"<t:{unix_ts}:D>\n(<t:{unix_ts}:R>)",
                    "inline": True,
                },
                {
                    "name": "📺 Stacja macierzysta",
                    "value": network_str,
                    "inline": True,
                },
                {
                    "name": "🇵🇱 Dostępność VOD (Polska)",
                    "value": vod_pl,
                    "inline": False,
                },
            ],
            "footer": {
                "text": "Radar Premier TV & VOD • Baza TMDB",
                "icon_url": "https://www.themoviedb.org/assets/2/v4/logos/v2/blue_square_2-d537fb228cf3ded904ef09b136fe3fec72548ebc1fea3fbbd1ad9e36364db38b.png",
            },
        }

        if poster_url:
            embed["thumbnail"] = {"url": poster_url}

        # Wysłanie na odpowiedni kanał Discorda
        if send_discord_embed(target_webhook, embed):
            history.append(alert_id)
            alerts_sent += 1
            print(f"Wysłano powiadomienie: {show_name} S{season_num}E{episode_num}")

    save_json(HISTORY_FILE, history)
    print(f"Zakończono. Wysłano nowych powiadomień: {alerts_sent}")


if __name__ == "__main__":
    run_monitor()