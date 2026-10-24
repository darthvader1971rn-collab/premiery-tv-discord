import json
import os
import threading
import tkinter as tk
from tkinter import messagebox, ttk
import requests

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_FILE = os.path.join(BASE_DIR, "config.json")
TRACKED_SHOWS_FILE = os.path.join(BASE_DIR, "tracked_shows.json")
TRACKED_MOVIES_FILE = os.path.join(BASE_DIR, "tracked_movies.json")


def load_json(filepath, default):
    if not os.path.exists(filepath):
        return default
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def save_json(filepath, data):
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


class TVTrackerGUI:

    def __init__(self, root):
        self.root = root
        self.root.title("Radar Premier TV, VOD & Kino • Menedżer Bazy")
        self.root.geometry("1050x700")

        config = load_json(CONFIG_FILE, {})
        self.api_key = config.get("tmdb_api_key", "").strip()

        if not self.api_key:
            messagebox.showerror(
                "Błąd", "Brak klucza TMDB API w pliku config.json!"
            )

        # Główne zakładek (Notebook)
        self.notebook = ttk.Notebook(root)
        self.notebook.pack(fill="both", expand=True, padx=10, pady=10)

        # Ramki zakładek
        self.tab_shows = ttk.Frame(self.notebook)
        self.tab_movies = ttk.Frame(self.notebook)

        self.notebook.add(self.tab_shows, text="📺 Seriale TV")
        self.notebook.add(self.tab_movies, text="🎬 Filmy kinowe")

        self.setup_shows_tab()
        self.setup_movies_tab()

    # ==================== ZAKŁADKA: SERIALE ====================
    def setup_shows_tab(self):
        sub_notebook = ttk.Notebook(self.tab_shows)
        sub_notebook.pack(fill="both", expand=True)

        # Podzakładka 1: Wyszukiwarka seriali
        search_frame = ttk.Frame(sub_notebook)
        sub_notebook.add(search_frame, text="🔍 Szukaj i dodaj do bazy")

        top_frame_s = ttk.Frame(search_frame, padding=10)
        top_frame_s.pack(fill="x")

        ttk.Label(top_frame_s, text="Nazwa serialu:").pack(
            side="left", padx=5
        )
        self.show_query_entry = ttk.Entry(top_frame_s, width=50)
        self.show_query_entry.pack(side="left", padx=5)
        self.show_query_entry.bind("<Return>", lambda e: self.search_shows())

        ttk.Button(
            top_frame_s, text="Szukaj w TMDB", command=self.search_shows
        ).pack(side="left", padx=5)

        columns_s = (
            "id",
            "title",
            "orig_title",
            "year",
            "network",
            "vod_pl",
            "next_air",
        )
        self.tree_shows = ttk.Treeview(
            search_frame, columns=columns_s, show="headings", selectmode="extended"
        )

        headings_s = {
            "id": "ID TMDB",
            "title": "Tytuł PL",
            "orig_title": "Tytuł oryginalny",
            "year": "Rok",
            "network": "Stacja macierzysta",
            "vod_pl": "Dostępność VOD (Polska)",
            "next_air": "Najbliższa emisja",
        }
        widths_s = {
            "id": 80,
            "title": 180,
            "orig_title": 150,
            "year": 60,
            "network": 130,
            "vod_pl": 160,
            "next_air": 150,
        }

        for col, text in headings_s.items():
            self.tree_shows.heading(col, text=text)
            self.tree_shows.column(col, width=widths_s.get(col, 100), anchor="w")

        scrollbar_s = ttk.Scrollbar(
            search_frame, orient="vertical", command=self.tree_shows.yview
        )
        self.tree_shows.configure(yscrollcommand=scrollbar_s.set)

        self.tree_shows.pack(
            side="top", fill="both", expand=True, padx=10, pady=5
        )
        scrollbar_s.pack(side="right", fill="y")

        btn_frame_s = ttk.Frame(search_frame, padding=10)
        btn_frame_s.pack(fill="x")
        ttk.Button(
            btn_frame_s,
            text="+ Dodaj zaznaczone do bazy",
            command=self.add_selected_shows,
        ).pack(side="right", padx=5)

        # Podzakładka 2: Obserwowane seriale
        tracked_frame_s = ttk.Frame(sub_notebook)
        sub_notebook.add(tracked_frame_s, text="📂 Obserwowane seriale")

        self.tree_tracked_shows = ttk.Treeview(
            tracked_frame_s, columns=("id", "title"), show="headings"
        )
        self.tree_tracked_shows.heading("id", text="ID TMDB")
        self.tree_tracked_shows.heading("title", text="Tytuł serialu")
        self.tree_tracked_shows.column("id", width=100)
        self.tree_tracked_shows.column("title", width=600)
        self.tree_tracked_shows.pack(
            side="top", fill="both", expand=True, padx=10, pady=10
        )

        btn_tracked_s = ttk.Frame(tracked_frame_s, padding=10)
        btn_tracked_s.pack(fill="x")
        ttk.Button(
            btn_tracked_s,
            text="🗑 Usuń zaznaczony z bazy",
            command=self.remove_tracked_show,
        ).pack(side="right", padx=5)
        ttk.Button(
            btn_tracked_s, text="Odśwież listę", command=self.load_tracked_shows
        ).pack(side="left", padx=5)

        self.load_tracked_shows()

    # ==================== ZAKŁADKA: FILMY ====================
    def setup_movies_tab(self):
        sub_notebook_m = ttk.Notebook(self.tab_movies)
        sub_notebook_m.pack(fill="both", expand=True)

        # Podzakładka 1: Wyszukiwarka filmów
        search_frame_m = ttk.Frame(sub_notebook_m)
        sub_notebook_m.add(search_frame_m, text="🔍 Szukaj i dodaj filmy")

        top_frame_m = ttk.Frame(search_frame_m, padding=10)
        top_frame_m.pack(fill="x")

        ttk.Label(top_frame_m, text="Tytuł filmu:").pack(side="left", padx=5)
        self.movie_query_entry = ttk.Entry(top_frame_m, width=50)
        self.movie_query_entry.pack(side="left", padx=5)
        self.movie_query_entry.bind("<Return>", lambda e: self.search_movies())

        ttk.Button(
            top_frame_m, text="Szukaj w TMDB", command=self.search_movies
        ).pack(side="left", padx=5)

        columns_m = (
            "id",
            "title",
            "orig_title",
            "year",
            "world_release",
            "pl_release",
        )
        self.tree_movies = ttk.Treeview(
            search_frame_m, columns=columns_m, show="headings", selectmode="extended"
        )

        headings_m = {
            "id": "ID TMDB",
            "title": "Tytuł PL",
            "orig_title": "Tytuł oryginalny",
            "year": "Rok",
            "world_release": "Premiera światowa",
            "pl_release": "Premiera Polska",
        }
        widths_m = {
            "id": 80,
            "title": 200,
            "orig_title": 180,
            "year": 60,
            "world_release": 130,
            "pl_release": 130,
        }

        for col, text in headings_m.items():
            self.tree_movies.heading(col, text=text)
            self.tree_movies.column(col, width=widths_m.get(col, 100), anchor="w")

        scrollbar_m = ttk.Scrollbar(
            search_frame_m, orient="vertical", command=self.tree_movies.yview
        )
        self.tree_movies.configure(yscrollcommand=scrollbar_m.set)

        self.tree_movies.pack(
            side="top", fill="both", expand=True, padx=10, pady=5
        )
        scrollbar_m.pack(side="right", fill="y")

        btn_frame_m = ttk.Frame(search_frame_m, padding=10)
        btn_frame_m.pack(fill="x")
        ttk.Button(
            btn_frame_m,
            text="+ Dodaj zaznaczone filmy do bazy",
            command=self.add_selected_movies,
        ).pack(side="right", padx=5)

        # Podzakładka 2: Obserwowane filmy
        tracked_frame_m = ttk.Frame(sub_notebook_m)
        sub_notebook_m.add(tracked_frame_m, text="📂 Obserwowane filmy")

        self.tree_tracked_movies = ttk.Treeview(
            tracked_frame_m, columns=("id", "title"), show="headings"
        )
        self.tree_tracked_movies.heading("id", text="ID TMDB")
        self.tree_tracked_movies.heading("title", text="Tytuł filmu")
        self.tree_tracked_movies.column("id", width=100)
        self.tree_tracked_movies.column("title", width=600)
        self.tree_tracked_movies.pack(
            side="top", fill="both", expand=True, padx=10, pady=10
        )

        btn_tracked_m = ttk.Frame(tracked_frame_m, padding=10)
        btn_tracked_m.pack(fill="x")
        ttk.Button(
            btn_tracked_m,
            text="🗑 Usuń zaznaczony film",
            command=self.remove_tracked_movie,
        ).pack(side="right", padx=5)
        ttk.Button(
            btn_tracked_m, text="Odśwież listę", command=self.load_tracked_movies
        ).pack(side="left", padx=5)

        self.load_tracked_movies()

    # ==================== LOGIKA SERIALI ====================
    def search_shows(self):
        query = self.show_query_entry.get().strip()
        if not query:
            return
        threading.Thread(
            target=self.execute_show_search, args=(query,), daemon=True
        ).start()

    def execute_show_search(self, query):
        try:
            url = "https://api.themoviedb.org/3/search/tv"
            params = {
                "api_key": self.api_key,
                "query": query,
                "language": "pl-PL",
            }
            res = requests.get(url, params=params, timeout=10)
            data = res.json()
            results = data.get("results", [])[:10]

            detailed = []
            for item in results:
                show_id = item["id"]
                det = requests.get(
                    f"https://api.themoviedb.org/3/tv/{show_id}",
                    params={"api_key": self.api_key, "language": "pl-PL"},
                    timeout=10,
                ).json()
                prov = requests.get(
                    f"https://api.themoviedb.org/3/tv/{show_id}/watch/providers",
                    params={"api_key": self.api_key},
                    timeout=10,
                ).json()

                networks = [n["name"] for n in det.get("networks", [])] or [
                    "Brak"
                ]
                net_str = ", ".join(networks[:2])

                pl_prov = (
                    prov.get("results", {}).get("PL", {}).get("flatrate", [])
                )
                vod_str = (
                    ", ".join([p["provider_name"] for p in pl_prov[:3]])
                    if pl_prov
                    else "Brak w VOD"
                )

                next_ep = det.get("next_episode_to_air")
                if next_ep:
                    next_str = f"S{next_ep.get('season_number', 0):02d}E{next_ep.get('episode_number', 0):02d} ({next_ep.get('air_date', '-')})"
                else:
                    next_str = f"[{det.get('status', 'Zakończony')}]"

                first_air = det.get("first_air_date", "")
                year = first_air[:4] if first_air else "-"

                detailed.append(
                    {
                        "id": show_id,
                        "title": det.get("name") or det.get("original_name"),
                        "orig_title": det.get("original_name"),
                        "year": year,
                        "network": net_str,
                        "vod_pl": vod_str,
                        "next_air": next_str,
                    }
                )

            self.root.after(0, self.populate_show_results, detailed)
        except Exception as e:
            self.root.after(
                0, messagebox.showerror, "Błąd", f"Błąd wyszukiwania: {e}"
            )

    def populate_show_results(self, results):
        for row in self.tree_shows.get_children():
            self.tree_shows.delete(row)
        for item in results:
            self.tree_shows.insert(
                "",
                "end",
                values=(
                    item["id"],
                    item["title"],
                    item["orig_title"],
                    item["year"],
                    item["network"],
                    item["vod_pl"],
                    item["next_air"],
                ),
            )

    def add_selected_shows(self):
        selected = self.tree_shows.selection()
        if not selected:
            return
        tracked = load_json(TRACKED_SHOWS_FILE, [])
        tracked_ids = {s["id"] for s in tracked}
        added = 0

        for row_id in selected:
            vals = self.tree_shows.item(row_id, "values")
            s_id = int(vals[0])
            s_title = vals[1]
            if s_id not in tracked_ids:
                tracked.append({"id": s_id, "title": s_title})
                added += 1

        save_json(TRACKED_SHOWS_FILE, tracked)
        self.load_tracked_shows()
        messagebox.showinfo(
            "Sukces", f"Dodano pomyślnie nowych seriali: {added}"
        )

    def load_tracked_shows(self):
        for row in self.tree_tracked_shows.get_children():
            self.tree_tracked_shows.delete(row)
        tracked = load_json(TRACKED_SHOWS_FILE, [])
        for item in tracked:
            self.tree_tracked_shows.insert(
                "", "end", values=(item["id"], item["title"])
            )

    def remove_tracked_show(self):
        selected = self.tree_tracked_shows.selection()
        if not selected:
            return
        tracked = load_json(TRACKED_SHOWS_FILE, [])
        for row_id in selected:
            vals = self.tree_tracked_shows.item(row_id, "values")
            s_id = int(vals[0])
            tracked = [s for s in tracked if s["id"] != s_id]

        save_json(TRACKED_SHOWS_FILE, tracked)
        self.load_tracked_shows()

    # ==================== LOGIKA FILMÓW ====================
    def search_movies(self):
        query = self.movie_query_entry.get().strip()
        if not query:
            return
        threading.Thread(
            target=self.execute_movie_search, args=(query,), daemon=True
        ).start()

    def execute_movie_search(self, query):
        try:
            url = "https://api.themoviedb.org/3/search/movie"
            params = {
                "api_key": self.api_key,
                "query": query,
                "language": "pl-PL",
            }
            res = requests.get(url, params=params, timeout=10)
            data = res.json()
            results = data.get("results", [])[:10]

            detailed = []
            for item in results:
                movie_id = item["id"]
                det = requests.get(
                    f"https://api.themoviedb.org/3/movie/{movie_id}",
                    params={"api_key": self.api_key, "language": "pl-PL"},
                    timeout=10,
                ).json()
                rel = requests.get(
                    f"https://api.themoviedb.org/3/movie/{movie_id}/release_dates",
                    params={"api_key": self.api_key},
                    timeout=10,
                ).json()

                world_date = det.get("release_date", "-")
                pl_date = "-"

                for country in rel.get("results", []):
                    if country.get("iso_3166_1") == "PL":
                        dates = country.get("release_dates", [])
                        if dates:
                            pl_date = dates[0].get("release_date", "-")[
                                :10
                            ]  # sam format YYYY-MM-DD

                release_date_raw = det.get("release_date", "")
                year = release_date_raw[:4] if release_date_raw else "-"

                detailed.append(
                    {
                        "id": movie_id,
                        "title": det.get("title")
                        or det.get("original_title"),
                        "orig_title": det.get("original_title"),
                        "year": year,
                        "world_release": world_date or "-",
                        "pl_release": pl_date or "-",
                    }
                )

            self.root.after(0, self.populate_movie_results, detailed)
        except Exception as e:
            self.root.after(
                0, messagebox.showerror, "Błąd", f"Błąd wyszukiwania filmów: {e}"
            )

    def populate_movie_results(self, results):
        for row in self.tree_movies.get_children():
            self.tree_movies.delete(row)
        for item in results:
            self.tree_movies.insert(
                "",
                "end",
                values=(
                    item["id"],
                    item["title"],
                    item["orig_title"],
                    item["year"],
                    item["world_release"],
                    item["pl_release"],
                ),
            )

    def add_selected_movies(self):
        selected = self.tree_movies.selection()
        if not selected:
            return
        tracked = load_json(TRACKED_MOVIES_FILE, [])
        tracked_ids = {m["id"] for m in tracked}
        added = 0

        for row_id in selected:
            vals = self.tree_movies.item(row_id, "values")
            m_id = int(vals[0])
            m_title = vals[1]
            if m_id not in tracked_ids:
                tracked.append({"id": m_id, "title": m_title})
                added += 1

        save_json(TRACKED_MOVIES_FILE, tracked)
        self.load_tracked_movies()
        messagebox.showinfo(
            "Sukces", f"Dodano pomyślnie nowych filmów: {added}"
        )

    def load_tracked_movies(self):
        for row in self.tree_tracked_movies.get_children():
            self.tree_tracked_movies.delete(row)
        tracked = load_json(TRACKED_MOVIES_FILE, [])
        for item in tracked:
            self.tree_tracked_movies.insert(
                "", "end", values=(item["id"], item["title"])
            )

    def remove_tracked_movie(self):
        selected = self.tree_tracked_movies.selection()
        if not selected:
            return
        tracked = load_json(TRACKED_MOVIES_FILE, [])
        for row_id in selected:
            vals = self.tree_tracked_movies.item(row_id, "values")
            m_id = int(vals[0])
            tracked = [m for m in tracked if m["id"] != m_id]

        save_json(TRACKED_MOVIES_FILE, tracked)
        self.load_tracked_movies()


if __name__ == "__main__":
    root = tk.Tk()
    app = TVTrackerGUI(root)
    root.mainloop()