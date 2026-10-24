import json
import os
import sys
from datetime import datetime, timedelta
import pytz
import requests

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_FILE = os.path.join(BASE_DIR, "config.json")
TRACKED_SHOWS_FILE = os.path.join(BASE_DIR, "tracked_shows.json")
TRACKED_MOVIES_FILE = os.path.join(BASE_DIR, "tracked_movies.json")
HISTORY_FILE = os.path.join(BASE_DIR, "history.json")


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


def get_week_range(date_obj):
    """Zwraca początek (poniedziałek) i koniec (niedziela) danego tygodnia dla daty."""
    start_week = date_obj - timedelta(days=date_obj.weekday())
    end_week = start_week + timedelta(days=6)
    return start_week, end_week


def run_monitor():
    config = load_json(CONFIG_FILE, {})
    tracked_shows = load_json(TRACKED_SHOWS_FILE, [])
    tracked_movies = load_json(TRACKED_MOVIES_FILE, [])
    history = load_json(HISTORY_FILE, [])

    api_key = config.get("tmdb_api_key", "").strip()
    webhooks = config.get("webhooks", {})
    new_series_wh = webhooks.get("new_series", "")
    returning_wh = webhooks.get("returning_series", "")
    movie_world_wh = webhooks.get("movie_world", "")
    movie_pl_wh = webhooks.get("movie_pl", "")
    pl_auto_wh = webhooks.get("pl_auto_releases", "")

    if not api_key:
        print("Brak klucza TMDB API w config.json!")
        sys.exit(1)

    tz_warsaw = pytz.timezone("Europe/Warsaw")
    today = datetime.now(tz_warsaw).date()

    # Zakres: 2 miesiące wstecz (60 dni) do 4 tygodni w przód (28 dni)
    start_date = today - timedelta(days=60)
    max_check_date = today + timedelta(days=28)

    print(
        f"Uruchomiono sprawdzanie. Zakres: od {start_date} do {max_check_date}"
    )
    alerts_sent = 0

    # ==================== 1. AUTOMATYCZNY SKANER POLSKICH KIN ====================
    if pl_auto_wh:
        print("Skanowanie automatycznych premier kinowych w Polsce...")
        discover_url = "https://api.themoviedb.org/3/discover/movie"

        movies_to_process = []
        for page in range(1, 4):
            params = {
                "api_key": api_key,
                "region": "PL",
                "release_date.gte": start_date.strftime("%Y-%m-%d"),
                "release_date.lte": max_check_date.strftime("%Y-%m-%d"),
                "with_release_type": "3|2",
                "sort_by": "release_date.asc",
                "page": page,
                "language": "pl-PL",
            }
            try:
                res = requests.get(discover_url, params=params, timeout=10)
                data = res.json()
                results = data.get("results", [])
                if not results:
                    break
                for m in results:
                    if m not in movies_to_process:
                        movies_to_process.append(m)
            except Exception as e:
                print(f"Błąd pobierania discover filmów: {e}")
                break

        print(
            f"Znaleziono filmów w zakresie PL w bazie TMDB: {len(movies_to_process)}"
        )

        for movie in movies_to_process:
            movie_id = movie["id"]
            movie_name = movie.get("title") or movie.get("original_title")

            rel_url = (
                f"https://api.themoviedb.org/3/movie/{movie_id}/release_dates"
            )
            pl_date_str = None
            try:
                rel_res = requests.get(
                    rel_url, params={"api_key": api_key}, timeout=10
                ).json()
                for country in rel_res.get("results", []):
                    if country.get("iso_3166_1") == "PL":
                        for rd in country.get("release_dates", []):
                            if rd.get("type") in [2, 3]:
                                pl_date_str = rd.get("release_date", "")[:10]
                                break
                        if pl_date_str:
                            break
            except Exception:
                pass

            if not pl_date_str:
                pl_date_str = movie.get("release_date")

            if not pl_date_str:
                continue

            try:
                pl_date = datetime.strptime(pl_date_str, "%Y-%m-%d").date()
            except ValueError:
                continue

            if not (start_date <= pl_date <= max_check_date):
                continue

            alert_id = f"pl_auto_{movie_id}_{pl_date_str}"
            if alert_id in history:
                continue

            # USUNIĘTO OGRANICZENIE 3 DNI - TERAZ WYŚLIE TEŻ HISTORIĘ Z 2 MIESIĘCY WSTECZ

            overview = movie.get("overview") or "Brak opisu w bazie TMDB."
            if len(overview) > 400:
                overview = overview[:397] + "..."

            poster_path = movie.get("poster_path")
            poster_url = (
                f"https://image.tmdb.org/t/p/w500{poster_path}"
                if poster_path
                else None
            )

            w_start, w_end = get_week_range(pl_date)
            week_label = f"📅 Tydzień: {w_start.strftime('%d.%m.%Y')} – {w_end.strftime('%d.%m.%Y')}"

            dt_release = datetime(
                pl_date.year, pl_date.month, pl_date.day, 18, 0, 0
            )
            dt_release_localized = tz_warsaw.localize(dt_release)
            unix_ts = int(dt_release_localized.timestamp())

            embed_pl_auto = {
                "title": f"🇵🇱 PREMIERA W POLSKIM KINIE: {movie_name}",
                "description": overview,
                "color": 0xE74C3C,
                "fields": [
                    {
                        "name": "📌 Blok tygodniowy",
                        "value": week_label,
                        "inline": False,
                    },
                    {
                        "name": "🎬 Dzień premiery",
                        "value": f"<t:{unix_ts}:D>\n(<t:{unix_ts}:R>)",
                        "inline": True,
                    },
                    {
                        "name": "⭐ Ocena TMDB",
                        "value": f"{movie.get('vote_average', 'N/A')}/10",
                        "inline": True,
                    },
                ],
                "footer": {
                    "text": "Repertuar Kinowy PL • Baza TMDB",
                    "icon_url": "https://www.themoviedb.org/assets/2/v4/logos/v2/blue_square_2-d537fb228cf3ded904ef09b136fe3fec72548ebc1fea3fbbd1ad9e36364db38b.png",
                },
            }
            if poster_url:
                embed_pl_auto["thumbnail"] = {"url": poster_url}

            if send_discord_embed(pl_auto_wh, embed_pl_auto):
                history.append(alert_id)
                alerts_sent += 1
                print(f"Wysłano polską premierę kinową: {movie_name}")

    # ==================== 2. SPRAWDZANIE SERIALI (Ręczna lista) ====================
    print(f"Liczba obserwowanych seriali: {len(tracked_shows)}")
    for show in tracked_shows:
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
            print(f"Nie udało się pobrać danych dla {show_name}: {e}")
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

        if not (start_date <= air_date <= max_check_date):
            continue

        season_num = next_ep.get("season_number", 1)
        episode_num = next_ep.get("episode_number", 1)
        alert_id = f"show_{show_id}_S{season_num:02d}E{episode_num:02d}_{air_date_str}"

        if alert_id in history:
            continue

        if air_date < today - timedelta(days=3):
            history.append(alert_id)
            continue

        is_new_series = season_num == 1 and episode_num == 1
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

        dt_air = datetime(air_date.year, air_date.month, air_date.day, 20, 0, 0)
        dt_air_localized = tz_warsaw.localize(dt_air)
        unix_ts = int(dt_air_localized.timestamp())

        if is_new_series:
            title_prefix = "🟢 NOWY SERIAL - PREMIERA PILOTA"
            color = 0x2ECC71
            target_webhook = new_series_wh
        else:
            if episode_num == 1:
                title_prefix = f"🔵 PREMIERA SEZONU {season_num}"
                color = 0x3498DB
            else:
                title_prefix = "📺 NOWY ODCINEK"
                color = 0x9B59B6
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

        if send_discord_embed(target_webhook, embed):
            history.append(alert_id)
            alerts_sent += 1
            print(f"Wysłano powiadomienie serialowe: {show_name}")

    # ==================== 3. SPRAWDZANIE FILMÓW (Ręczna lista z GUI) ====================
    print(f"Liczba obserwowanych filmów (ręcznych): {len(tracked_movies)}")
    for movie in tracked_movies:
        movie_id = movie["id"]
        movie_name = movie.get("title", f"Film {movie_id}")

        url = f"https://api.themoviedb.org/3/movie/{movie_id}"
        rel_url = f"https://api.themoviedb.org/3/movie/{movie_id}/release_dates"
        try:
            res = requests.get(
                url,
                params={"api_key": api_key, "language": "pl-PL"},
                timeout=10,
            )
            data = res.json()
            rel_res = requests.get(
                rel_url, params={"api_key": api_key}, timeout=10
            ).json()
        except Exception as e:
            print(f"Nie udało się pobrać danych dla filmu {movie_name}: {e}")
            continue

        # Światowa ręczna
        world_date_str = data.get("release_date")
        if world_date_str and movie_world_wh:
            try:
                world_date = datetime.strptime(world_date_str, "%Y-%m-%d").date()
                if start_date <= world_date <= max_check_date:
                    world_alert_id = f"movie_world_{movie_id}_{world_date_str}"
                    if world_alert_id not in history:
                        if world_date < today - timedelta(days=3):
                            history.append(world_alert_id)
                        else:
                            overview = (
                                data.get("overview")
                                or "Brak opisu w bazie TMDB."
                            )
                            if len(overview) > 400:
                                overview = overview[:397] + "..."

                            poster_path = data.get("poster_path")
                            poster_url = (
                                f"https://image.tmdb.org/t/p/w500{poster_path}"
                                if poster_path
                                else None
                            )

                            dt_release = datetime(
                                world_date.year,
                                world_date.month,
                                world_date.day,
                                18,
                                0,
                                0,
                            )
                            dt_release_localized = tz_warsaw.localize(dt_release)
                            unix_ts = int(dt_release_localized.timestamp())

                            embed_world = {
                                "title": f"🌐 PREMIERA ŚWIATOWA: {movie_name}",
                                "description": overview,
                                "color": 0xE67E22,
                                "fields": [
                                    {
                                        "name": "📅 Data premiery",
                                        "value": f"<t:{unix_ts}:D>\n(<t:{unix_ts}:R>)",
                                        "inline": True,
                                    },
                                    {
                                        "name": "⭐ Ocena TMDB",
                                        "value": f"{data.get('vote_average', 'N/A')}/10",
                                        "inline": True,
                                    },
                                ],
                                "footer": {
                                    "text": "Radar Kinowy • Baza TMDB",
                                    "icon_url": "https://www.themoviedb.org/assets/2/v4/logos/v2/blue_square_2-d537fb228cf3ded904ef09b136fe3fec72548ebc1fea3fbbd1ad9e36364db38b.png",
                                },
                            }
                            if poster_url:
                                embed_world["thumbnail"] = {
                                    "url": poster_url
                                }

                            if send_discord_embed(
                                movie_world_wh, embed_world
                            ):
                                history.append(world_alert_id)
                                alerts_sent += 1
                                print(
                                    f"Wysłano powiadomienie (Film - Świat): {movie_name}"
                                )
            except ValueError:
                pass

        # Polska ręczna
        pl_date_str = None
        for country in rel_res.get("results", []):
            if country.get("iso_3166_1") == "PL":
                dates = country.get("release_dates", [])
                if dates:
                    pl_date_str = dates[0].get("release_date", "")[:10]

        if pl_date_str and movie_pl_wh:
            try:
                pl_date = datetime.strptime(pl_date_str, "%Y-%m-%d").date()
                if start_date <= pl_date <= max_check_date:
                    pl_alert_id = f"movie_pl_{movie_id}_{pl_date_str}"
                    if pl_alert_id not in history:
                        if pl_date < today - timedelta(days=3):
                            history.append(pl_alert_id)
                        else:
                            overview = (
                                data.get("overview")
                                or "Brak opisu w bazie TMDB."
                            )
                            if len(overview) > 400:
                                overview = overview[:397] + "..."

                            poster_path = data.get("poster_path")
                            poster_url = (
                                f"https://image.tmdb.org/t/p/w500{poster_path}"
                                if poster_path
                                else None
                            )

                            dt_release = datetime(
                                pl_date.year,
                                pl_date.month,
                                pl_date.day,
                                18,
                                0,
                                0,
                            )
                            dt_release_localized = tz_warsaw.localize(dt_release)
                            unix_ts = int(dt_release_localized.timestamp())

                            embed_pl = {
                                "title": f"🇵🇱 PREMIERA W POLSCE (Ręczna): {movie_name}",
                                "description": overview,
                                "color": 0xE74C3C,
                                "fields": [
                                    {
                                        "name": "📅 Data premiery",
                                        "value": f"<t:{unix_ts}:D>\n(<t:{unix_ts}:R>)",
                                        "inline": True,
                                    },
                                    {
                                        "name": "⭐ Ocena TMDB",
                                        "value": f"{data.get('vote_average', 'N/A')}/10",
                                        "inline": True,
                                    },
                                ],
                                "footer": {
                                    "text": "Radar Kinowy • Baza TMDB",
                                    "icon_url": "https://www.themoviedb.org/assets/2/v4/logos/v2/blue_square_2-d537fb228cf3ded904ef09b136fe3fec72548ebc1fea3fbbd1ad9e36364db38b.png",
                                },
                            }
                            if poster_url:
                                embed_pl["thumbnail"] = {"url": poster_url}

                            if send_discord_embed(movie_pl_wh, embed_pl):
                                history.append(pl_alert_id)
                                alerts_sent += 1
                                print(
                                    f"Wysłano powiadomienie (Film - PL Ręczny): {movie_name}"
                                )
            except ValueError:
                pass

    save_json(HISTORY_FILE, history)
    print(f"Zakończono. Wysłano nowych powiadomień: {alerts_sent}")


if __name__ == "__main__":
    run_monitor()